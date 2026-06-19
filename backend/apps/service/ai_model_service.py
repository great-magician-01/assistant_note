"""AI model pool business logic: CRUD over the global model pool."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.ai_config import AiConfig
from backend.apps.model.ai_model import AiModel
from backend.apps.utils.exceptions import BusinessError, NotFoundError

logger = logging.getLogger(__name__)

# Allowed API wire formats. Stored in ai_models.api_format.
_VALID_API_FORMATS = {"openai", "anthropic"}


async def list_ai_models(db: AsyncSession) -> list[dict]:
    """Return all non-deleted models in the pool (ordered by name)."""
    logger.debug("List ai_models")
    result = await db.execute(
        select(AiModel)
        .where(AiModel.is_deleted == 0)
        .order_by(AiModel.name.asc(), AiModel.model_id.asc())
    )
    models = result.scalars().all()
    logger.debug("List ai_models: returned %d models", len(models))
    return [_ai_model_to_dict(m) for m in models]


async def create_ai_model(db: AsyncSession, fields: dict[str, Any]) -> AiModel:
    """Create a new model pool entry.

    Raises BusinessError on invalid api_format.
    """
    api_format = fields.get("api_format")
    if api_format not in _VALID_API_FORMATS:
        logger.warning("Create ai_model failed: invalid api_format=%r", api_format)
        raise BusinessError(f"接口格式无效，仅支持 {sorted(_VALID_API_FORMATS)}")

    logger.debug("Create ai_model: name=%s, model=%s", fields.get("name"), fields.get("model"))
    model = AiModel(
        name=fields["name"],
        api_format=api_format,
        base_url=fields["base_url"],
        api_key=fields["api_key"],
        model=fields["model"],
        is_multimodal=fields.get("is_multimodal", 0),
        max_tokens=fields.get("max_tokens", 4096),
        remark=fields.get("remark"),
        extra_config=fields.get("extra_config") or {},
        is_active=fields.get("is_active", 1),
    )
    db.add(model)
    await db.flush()
    logger.info("Create ai_model success: model_id=%s, name=%s", model.model_id, model.name)
    return model


async def update_ai_model(
    db: AsyncSession,
    model_id: int,
    fields: dict[str, Any],
) -> AiModel:
    """Update a model with only the provided fields (exclude_unset pattern).

    Raises NotFoundError if the model does not exist,
    BusinessError on invalid api_format.
    """
    logger.debug("Update ai_model: model_id=%s, fields=%s", model_id, list(fields.keys()))
    result = await db.execute(
        select(AiModel).where(
            AiModel.model_id == model_id,
            AiModel.is_deleted == 0,
        )
    )
    model = result.scalar_one_or_none()
    if model is None:
        logger.warning("Update ai_model failed: model_id=%s not found", model_id)
        raise NotFoundError("模型不存在")

    if "api_format" in fields:
        if fields["api_format"] not in _VALID_API_FORMATS:
            logger.warning("Update ai_model failed: invalid api_format=%r", fields["api_format"])
            raise BusinessError(f"接口格式无效，仅支持 {sorted(_VALID_API_FORMATS)}")
        model.api_format = fields["api_format"]

    for key in ("name", "base_url", "api_key", "model", "remark", "extra_config"):
        if key in fields:
            setattr(model, key, fields[key])

    for key in ("is_multimodal", "max_tokens", "is_active"):
        if key in fields:
            setattr(model, key, fields[key])

    await db.flush()
    logger.info("Update ai_model success: model_id=%s", model_id)
    return model


async def delete_ai_model(db: AsyncSession, model_id: int) -> None:
    """Soft delete a model.

    Refuses if any non-deleted ai_configs still reference it — those configs
    would point at a soft-deleted model. The user must delete/retarget them
    first.
    """
    logger.debug("Delete ai_model: model_id=%s", model_id)
    result = await db.execute(
        select(AiModel).where(
            AiModel.model_id == model_id,
            AiModel.is_deleted == 0,
        )
    )
    model = result.scalar_one_or_none()
    if model is None:
        logger.warning("Delete ai_model failed: model_id=%s not found", model_id)
        raise NotFoundError("模型不存在")

    # Guard: block deletion while configs still reference this model.
    ref_result = await db.execute(
        select(AiConfig.config_id).where(
            AiConfig.model_id == model_id,
            AiConfig.is_deleted == 0,
        )
    )
    if ref_result.first() is not None:
        logger.warning("Delete ai_model blocked: configs reference model_id=%s", model_id)
        raise BusinessError("模型被配置引用，请先删除或更换相关配置")

    model.is_deleted = 1
    await db.flush()
    logger.info("Delete ai_model success: model_id=%s", model_id)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _ai_model_to_dict(m: AiModel) -> dict:
    return {
        "model_id": m.model_id,
        "name": m.name,
        "api_format": m.api_format,
        "base_url": m.base_url,
        "api_key": m.api_key,
        "model": m.model,
        "is_multimodal": m.is_multimodal,
        "max_tokens": m.max_tokens,
        "remark": m.remark,
        "extra_config": m.extra_config,
        "is_active": m.is_active,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }
