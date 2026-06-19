"""AI model runtime config business logic: CRUD over ai_configs.

A config picks one model from the pool and layers runtime parameters on top.
``is_default`` is kept to a single global row: the service clears any existing
default before setting a new one, and a partial unique index (migration 003)
backs this up at the DB level.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.ai_config import AiConfig
from backend.apps.model.ai_model import AiModel
from backend.apps.utils.exceptions import BusinessError, NotFoundError

logger = logging.getLogger(__name__)


async def list_ai_configs(db: AsyncSession) -> list[dict]:
    """Return all non-deleted configs, enriched with their pool model's info."""
    logger.debug("List ai_configs")
    result = await db.execute(
        select(AiConfig)
        .where(AiConfig.is_deleted == 0)
        .order_by(AiConfig.is_default.desc(), AiConfig.config_name.asc())
    )
    configs = result.scalars().all()
    if not configs:
        return []

    # Fetch referenced models (including soft-deleted ones, so a config that
    # points at a since-deleted model still shows what it referenced).
    model_ids = {c.model_id for c in configs}
    model_map = await _model_map(db, model_ids)

    logger.debug("List ai_configs: returned %d configs", len(configs))
    return [_ai_config_to_dict(c, model_map.get(c.model_id)) for c in configs]


async def get_ai_config(db: AsyncSession, config_id: int) -> Optional[dict]:
    """Return a single non-deleted config, enriched with its pool model info.

    Returns None if the config does not exist (or is soft-deleted). Used by the
    create/update handlers so they don't have to re-query the whole table.
    """
    result = await db.execute(
        select(AiConfig).where(
            AiConfig.config_id == config_id,
            AiConfig.is_deleted == 0,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        return None
    model_map = await _model_map(db, {config.model_id})
    return _ai_config_to_dict(config, model_map.get(config.model_id))


async def create_ai_config(db: AsyncSession, fields: dict[str, Any]) -> AiConfig:
    """Create a new runtime config.

    Raises NotFoundError if the referenced model does not exist,
    BusinessError on invalid sampling params.
    """
    model_id = fields["model_id"]
    await _validate_model(db, model_id)
    _validate_sampling(fields)

    is_default = fields.get("is_default", 0)
    if is_default == 1:
        await _clear_other_defaults(db, exclude_id=None)

    logger.debug("Create ai_config: name=%s, model_id=%s", fields.get("config_name"), model_id)
    config = AiConfig(
        config_name=fields["config_name"],
        model_id=model_id,
        system_prompt=fields.get("system_prompt"),
        tools=fields.get("tools") or [],
        json_output=fields.get("json_output", 0),
        temperature=fields.get("temperature"),
        top_p=fields.get("top_p"),
        max_tokens=fields.get("max_tokens"),
        is_default=is_default,
        is_active=fields.get("is_active", 1),
    )
    db.add(config)
    await db.flush()
    logger.info("Create ai_config success: config_id=%s, name=%s", config.config_id, config.config_name)
    return config


async def update_ai_config(
    db: AsyncSession,
    config_id: int,
    fields: dict[str, Any],
) -> AiConfig:
    """Update a config with only the provided fields (exclude_unset pattern).

    Raises NotFoundError if the config (or newly referenced model) does not
    exist, BusinessError on invalid sampling params.
    """
    logger.debug("Update ai_config: config_id=%s, fields=%s", config_id, list(fields.keys()))
    result = await db.execute(
        select(AiConfig).where(
            AiConfig.config_id == config_id,
            AiConfig.is_deleted == 0,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        logger.warning("Update ai_config failed: config_id=%s not found", config_id)
        raise NotFoundError("配置不存在")

    if "model_id" in fields:
        await _validate_model(db, fields["model_id"])
        config.model_id = fields["model_id"]

    _validate_sampling(fields)

    for key in ("config_name", "system_prompt", "tools", "temperature", "top_p", "max_tokens"):
        if key in fields:
            setattr(config, key, fields[key])

    for key in ("json_output", "is_active"):
        if key in fields:
            setattr(config, key, fields[key])

    if "is_default" in fields:
        if fields["is_default"] == 1 and config.is_default != 1:
            await _clear_other_defaults(db, exclude_id=config_id)
        config.is_default = fields["is_default"]

    await db.flush()
    logger.info("Update ai_config success: config_id=%s", config_id)
    return config


async def delete_ai_config(db: AsyncSession, config_id: int) -> None:
    """Soft delete a config."""
    logger.debug("Delete ai_config: config_id=%s", config_id)
    result = await db.execute(
        select(AiConfig).where(
            AiConfig.config_id == config_id,
            AiConfig.is_deleted == 0,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        logger.warning("Delete ai_config failed: config_id=%s not found", config_id)
        raise NotFoundError("配置不存在")

    config.is_deleted = 1
    await db.flush()
    logger.info("Delete ai_config success: config_id=%s", config_id)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _validate_model(db: AsyncSession, model_id: int) -> None:
    """Ensure the referenced pool model exists and is not soft-deleted."""
    result = await db.execute(
        select(AiModel).where(
            AiModel.model_id == model_id,
            AiModel.is_deleted == 0,
        )
    )
    if result.scalar_one_or_none() is None:
        logger.warning("Validate model failed: model_id=%s not found", model_id)
        raise NotFoundError("模型不存在")


async def _model_map(db: AsyncSession, model_ids: set[int]) -> dict[int, AiModel]:
    """Fetch the pool models for ``model_ids`` (incl. soft-deleted) by id."""
    if not model_ids:
        return {}
    result = await db.execute(
        select(AiModel).where(AiModel.model_id.in_(model_ids))
    )
    return {m.model_id: m for m in result.scalars().all()}


def _validate_sampling(fields: dict[str, Any]) -> None:
    """Validate temperature/top_p ranges if present."""
    if "temperature" in fields and fields["temperature"] is not None:
        t = fields["temperature"]
        if t < 0 or t > 2:
            raise BusinessError("temperature 取值范围为 0–2")
    if "top_p" in fields and fields["top_p"] is not None:
        p = fields["top_p"]
        if p < 0 or p > 1:
            raise BusinessError("top_p 取值范围为 0–1")


async def _clear_other_defaults(db: AsyncSession, exclude_id: Optional[int]) -> None:
    """Unset is_default on all other non-deleted configs.

    Backed up by the partial unique index uq_ai_configs_default, but clearing
    here avoids surfacing a DB unique-violation as a 500.
    """
    result = await db.execute(
        select(AiConfig).where(
            AiConfig.is_default == 1,
            AiConfig.is_deleted == 0,
        )
    )
    for cfg in result.scalars().all():
        if exclude_id is None or cfg.config_id != exclude_id:
            cfg.is_default = 0


def _ai_config_to_dict(c: AiConfig, model: Optional[AiModel]) -> dict:
    return {
        "config_id": c.config_id,
        "config_name": c.config_name,
        "model_id": c.model_id,
        "model_name": model.name if model else None,
        "model": model.model if model else None,
        "api_format": model.api_format if model else None,
        "system_prompt": c.system_prompt,
        "tools": c.tools,
        "json_output": c.json_output,
        "temperature": float(c.temperature) if c.temperature is not None else None,
        "top_p": float(c.top_p) if c.top_p is not None else None,
        "max_tokens": c.max_tokens,
        "is_default": c.is_default,
        "is_active": c.is_active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
