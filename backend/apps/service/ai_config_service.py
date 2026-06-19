"""AI model runtime config business logic: CRUD over ai_configs.

A config picks one model from the pool and layers runtime parameters on top.
``is_default`` is kept to a single global row: the service clears any existing
default before setting a new one, and a partial unique index (migration 003)
backs this up at the DB level.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.ai.tools.registry import list_tools
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
    model_ids = {c.model_id for c in configs if c.model_id is not None}
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
    model_map = await _model_map(db, {config.model_id} if config.model_id is not None else set())
    return _ai_config_to_dict(config, model_map.get(config.model_id))


async def get_default_config(db: AsyncSession) -> Optional[dict]:
    """Return the global default active config (enriched), or None if none set.

    Used by the chat endpoint when the caller omits ``config_id``. Backed by the
    partial unique index ``uq_ai_configs_default`` (at most one default row).
    """
    result = await db.execute(
        select(AiConfig).where(
            AiConfig.is_default == 1,
            AiConfig.is_active == 1,
            AiConfig.is_deleted == 0,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        return None
    model_ids = {config.model_id} if config.model_id is not None else set()
    model_map = await _model_map(db, model_ids)
    return _ai_config_to_dict(config, model_map.get(config.model_id))


# ── Default config bootstrap ──────────────────────────────────────────────────

# Fixed config_id so repeated startup doesn't create duplicate rows.
DEFAULT_CONFIG_ID = 1

DEFAULT_SYSTEM_PROMPT = """\
你是「智能笔记」应用内置的 AI 助手，服务于当前登录用户。你可以帮用户搜索、阅读、整理和修改笔记，也可以新建笔记。

## 可用工具
- **search_notes(keyword)**: 按关键词全文搜索笔记（匹配标题和正文），返回摘要列表，不含正文。
- **search_notes_by_tag(tag)**: 按标签筛选笔记，返回摘要列表。
- **read_note(note_id)**: 读取指定笔记的完整内容（标题、正文 Markdown、摘要、标签）。修改笔记前必须先调用此工具确认当前内容。
- **edit_note(note_id, fields...)**: 部分修改笔记，可改标题（note_title）、正文（note_content, Markdown）、摘要（note_summary）、标签（note_tags）。只传需要修改的字段，省略的字段保持不变。传正文时必须传完整的 Markdown 全文，不要只传片段。
- **create_note(note_title, fields...)**: 新建笔记，可指定标题、正文（note_content, Markdown）、分类（category_id）、标签（note_tags）。

## 工作流程
1. **修改笔记**: 先用 search_notes 找到目标 → 用 read_note 读取完整内容 → 确认后再用 edit_note 修改。
2. **新建笔记**: 从用户意图中提炼标题和正文，用 create_note 创建。
3. **不确定性**: 当用户意图不明确（指代不明、信息不足）时，先向用户确认，不要猜测后擅自操作。
4. **批量操作**: 一次回复中可以连续调用多个工具（如先搜索→读取→再编辑）。

## 注意事项
- 所有 note_id / category_id 都是字符串形式的雪花ID，从工具返回后原样传入即可。
- 没有删除笔记的功能（设计如此），如需"删除"某内容可清空正文或标记标签。
- 工具返回错误时（如笔记不存在），如实告知用户并给出建议，不要假装成功。
- 完成操作后用简短中文告知结果，无需复述整段正文（除非用户要求）。\
"""


async def ensure_default_config(
    db: AsyncSession, *, model_id: int | None = None, max_tokens: int | None = None
) -> None:
    """Ensure the default AI config row (config_id=1) exists.

    Called when the first model is added to the pool.  Uses a fixed
    ``config_id`` so repeated calls are idempotent.  If the config already
    exists its model/settings are left untouched — only the tool list is
    refreshed so newly registered tools become available.

    Parameters:
        model_id:  Pool model to bind (used only on first creation).
        max_tokens:  Max tokens for the config (derived from the model).
    """
    result = await db.execute(
        select(AiConfig).where(AiConfig.config_id == DEFAULT_CONFIG_ID)
    )
    config = result.scalar_one_or_none()

    all_tool_names = [t.name for t in list_tools()]

    if config is None:
        if model_id is None:
            logger.warning("Default AI config not created: no model_id provided")
            return
        logger.info("Creating default AI config bound to model_id=%s", model_id)
        # Clear any other default before claiming the single default slot, so we
        # don't trip the partial unique index uq_ai_configs_default (→ 500). The
        # check-then-insert above is also non-atomic; guard the flush against a
        # concurrent insert with the same fixed config_id and re-query on clash.
        await _clear_other_defaults(db, exclude_id=DEFAULT_CONFIG_ID)
        config = AiConfig(
            config_id=DEFAULT_CONFIG_ID,
            config_name="默认助手",
            model_id=model_id,
            max_tokens=max_tokens,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            tools=all_tool_names,
            is_default=1,
            is_active=1,
        )
        db.add(config)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            logger.warning("Default AI config raced with another caller; re-querying")
            return await ensure_default_config(db, model_id=model_id, max_tokens=max_tokens)
        logger.info("Default AI config created: config_id=%s, model_id=%s, tools=%d",
                     config.config_id, model_id, len(all_tool_names))
        return

    # Config already exists — resurrect if soft-deleted/disabled and refresh
    # tools.  Never overwrite model_id / system_prompt / sampling params —
    # those belong to the admin.  Exception: a placeholder default config
    # (model_id=None, created when the model pool was empty) gets bound to the
    # first model added, realizing the migration 008 "bind later" intent.
    updated = False

    if config.is_deleted != 0:
        config.is_deleted = 0
        updated = True
        logger.info("Default AI config was soft-deleted; restoring")

    if config.is_active != 1:
        config.is_active = 1
        updated = True
        logger.info("Default AI config re-activated")

    if config.model_id is None and model_id is not None:
        config.model_id = model_id
        if config.max_tokens is None and max_tokens is not None:
            config.max_tokens = max_tokens
        updated = True
        logger.info("Default AI config placeholder bound to model_id=%s", model_id)

    existing_tools: set[str] = set(config.tools or [])
    new_tools = [t for t in all_tool_names if t not in existing_tools]
    if new_tools:
        config.tools = list(existing_tools | set(all_tool_names))
        updated = True
        logger.info("Default AI config tools refreshed: added %s", new_tools)

    if updated:
        await db.flush()
        logger.info("Default AI config repaired: config_id=%s", config.config_id)
    else:
        logger.debug("Default AI config already healthy (config_id=%s)", config.config_id)


async def create_ai_config(db: AsyncSession, fields: dict[str, Any]) -> AiConfig:
    """Create a new runtime config.

    Raises NotFoundError if the referenced model does not exist,
    BusinessError on invalid sampling params.
    """
    model_id = fields.get("model_id")
    if model_id is not None:
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
        if fields["model_id"] is not None:
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
