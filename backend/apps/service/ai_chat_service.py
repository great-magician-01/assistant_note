"""AI chat session/message persistence + config resolution.

Sessions are server-managed and snapshot the config/model/api_format at first
message time. Messages (user/assistant/tool) are appended here by the chat
runner; the runner owns ``commit()`` at durability points, while this service
only ``flush()``es (matching the rest of the service layer — ``get_db`` commits
once per request for the non-streaming endpoints; the streaming endpoint uses
its own session and commits per turn).
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.ai_chat import (
    AiChatMessage,
    AiChatSession,
    ROLE_ASSISTANT,
    ROLE_TOOL,
    ROLE_USER,
)
from backend.apps.model.ai_model import AiModel
from backend.apps.service import ai_config_service
from backend.apps.utils.exceptions import BusinessError, NotFoundError

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "新对话"
# Cap auto-title length (first user message snippet).
_TITLE_LEN = 30


# ── Session CRUD ─────────────────────────────────────────────────────────────


async def create_session(
    db: AsyncSession,
    user_id: int,
    config_id: int,
    model_id: int,
    api_format: str,
    title: str = DEFAULT_TITLE,
    note_id: Optional[int] = None,
) -> AiChatSession:
    logger.debug("Create chat session: user_id=%s, config_id=%s, note_id=%s",
                 user_id, config_id, note_id)
    session = AiChatSession(
        user_id=user_id,
        config_id=config_id,
        model_id=model_id,
        api_format=api_format,
        session_title=title,
        note_id=note_id,
    )
    db.add(session)
    await db.flush()
    logger.info("Create chat session success: session_id=%s, user_id=%s",
                session.session_id, user_id)
    return session


async def get_session(
    db: AsyncSession, session_id: int, user_id: int
) -> AiChatSession:
    """Fetch a session owned by ``user_id`` (not soft-deleted).

    Raises NotFoundError if missing, deleted, or owned by another user.
    """
    result = await db.execute(
        select(AiChatSession).where(
            AiChatSession.session_id == session_id,
            AiChatSession.user_id == user_id,
            AiChatSession.is_deleted == 0,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        logger.warning("Get chat session failed: session_id=%s not found (user_id=%s)",
                       session_id, user_id)
        raise NotFoundError("会话不存在")
    return session


async def list_sessions(
    db: AsyncSession, user_id: int, note_id: Optional[int] = None
) -> list[dict]:
    """List a user's non-deleted sessions, newest first.

    ``note_id`` filters to sessions bound to a specific note (used by the note
    editor's AI drawer to reload a note's existing thread).
    """
    stmt = select(AiChatSession).where(
        AiChatSession.user_id == user_id,
        AiChatSession.is_deleted == 0,
    )
    if note_id is not None:
        stmt = stmt.where(AiChatSession.note_id == note_id)
    stmt = stmt.order_by(AiChatSession.updated_at.desc())
    result = await db.execute(stmt)
    return [_session_to_dict(s) for s in result.scalars().all()]


async def rename_session(
    db: AsyncSession, session_id: int, user_id: int, title: str
) -> AiChatSession:
    session = await get_session(db, session_id, user_id)
    session.session_title = title
    await db.flush()
    return session


async def delete_session(db: AsyncSession, session_id: int, user_id: int) -> None:
    session = await get_session(db, session_id, user_id)
    session.is_deleted = 1
    await db.flush()
    logger.info("Delete chat session: session_id=%s (user_id=%s)", session_id, user_id)


# ── Messages ─────────────────────────────────────────────────────────────────


async def list_messages(
    db: AsyncSession, session_id: int, user_id: int
) -> list[dict]:
    """List a session's messages in chronological order.

    Validates ownership via get_session first.
    """
    await get_session(db, session_id, user_id)
    result = await db.execute(
        select(AiChatMessage)
        .where(AiChatMessage.session_id == session_id)
        .order_by(AiChatMessage.created_at.asc(), AiChatMessage.message_id.asc())
    )
    return [_message_to_dict(m) for m in result.scalars().all()]


async def add_message(
    db: AsyncSession,
    session_id: int,
    role: str,
    content: Optional[str] = None,
    tool_calls: Optional[list[dict]] = None,
    tool_call_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    is_error: int = 0,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    iter_index: int = 0,
) -> AiChatMessage:
    """Append a message row. Caller commits at durability points."""
    msg = AiChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        tool_calls=tool_calls or [],
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        is_error=is_error,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        iter_index=iter_index,
    )
    db.add(msg)
    await db.flush()
    return msg


async def auto_title_if_needed(
    db: AsyncSession, session: AiChatSession, first_user_text: str
) -> None:
    """If the session still has the default title, set it from the first message.

    Only renames on the very first user message (title == DEFAULT_TITLE). Keeps
    whitespace/newlines out of the title.
    """
    if session.session_title != DEFAULT_TITLE:
        return
    snippet = " ".join(first_user_text.split())[:_TITLE_LEN]
    if snippet:
        session.session_title = snippet
        await db.flush()


# ── Config resolution ────────────────────────────────────────────────────────


async def resolve_chat_config(
    db: AsyncSession, config_id: Optional[int]
) -> tuple[dict, AiModel]:
    """Resolve the config + its pool model for a chat request.

    ``config_id`` None → use the global default. Validates the config is active
    and its model exists / is active / not deleted. Raises BusinessError on any
    problem (so the streaming endpoint can surface a 400 before opening the
    stream).
    """
    if config_id is not None:
        config = await ai_config_service.get_ai_config(db, config_id)
    else:
        config = await ai_config_service.get_default_config(db)

    if config is None:
        raise BusinessError("未找到可用的 AI 配置")
    if config.get("is_active") != 1:
        raise BusinessError("该 AI 配置已禁用")

    model_id = config["model_id"]
    result = await db.execute(
        select(AiModel).where(AiModel.model_id == model_id)
    )
    model = result.scalar_one_or_none()
    if model is None or model.is_deleted == 1:
        raise BusinessError("该配置引用的模型不存在")
    if model.is_active != 1:
        raise BusinessError("该配置引用的模型已禁用")

    logger.debug(
        "Resolve chat config: config_id=%s, model_id=%s, api_format=%s",
        config["config_id"], model.model_id, model.api_format,
    )
    return config, model


# ── History → internal messages ──────────────────────────────────────────────
# The internal message dataclasses live in backend.apps.ai.chat.messages; we
# import lazily here to avoid a hard dependency cycle (messages.py is pure and
# has no DB imports, but keeping the import local keeps this service standalone).


def rows_to_history(rows: list[dict]) -> list[Any]:
    """Convert DB message dicts to the internal message list used by providers.

    Returns a list of UserMessage / AssistantMessage / ToolResultMessage
    (from backend.apps.ai.chat.messages), in chronological order.
    """
    from backend.apps.ai.chat.messages import (
        AssistantMessage,
        ToolCall,
        ToolResultMessage,
        UserMessage,
    )

    history: list[Any] = []
    for r in rows:
        role = r["role"]
        if role == ROLE_USER:
            history.append(UserMessage(content=r["content"] or ""))
        elif role == ROLE_ASSISTANT:
            tool_calls = [
                ToolCall(
                    id=tc.get("id") or "",
                    name=tc.get("name") or "",
                    arguments=tc.get("arguments") or {},
                )
                for tc in (r.get("tool_calls") or [])
            ]
            history.append(
                AssistantMessage(
                    content=r.get("content"),
                    tool_calls=tool_calls,
                    prompt_tokens=r.get("prompt_tokens"),
                    completion_tokens=r.get("completion_tokens"),
                )
            )
        elif role == ROLE_TOOL:
            history.append(
                ToolResultMessage(
                    tool_call_id=r.get("tool_call_id") or "",
                    tool_name=r.get("tool_name") or "",
                    content=r.get("content") or "",
                    is_error=bool(r.get("is_error")),
                )
            )
    return history


# ── Dict serializers ─────────────────────────────────────────────────────────


def _session_to_dict(s: AiChatSession) -> dict:
    return {
        "session_id": s.session_id,
        "user_id": s.user_id,
        "config_id": s.config_id,
        "model_id": s.model_id,
        "api_format": s.api_format,
        "session_title": s.session_title,
        "note_id": s.note_id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _message_to_dict(m: AiChatMessage) -> dict:
    return {
        "message_id": m.message_id,
        "session_id": m.session_id,
        "role": m.role,
        "content": m.content,
        "tool_calls": m.tool_calls,
        "tool_call_id": m.tool_call_id,
        "tool_name": m.tool_name,
        "is_error": m.is_error,
        "prompt_tokens": m.prompt_tokens,
        "completion_tokens": m.completion_tokens,
        "iter_index": m.iter_index,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }
