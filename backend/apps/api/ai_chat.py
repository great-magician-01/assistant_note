"""AI chat API endpoints — /v1/ai/chat/

Streaming chat (SSE) + session management. All endpoints require auth.

The streaming endpoint resolves config/model/session and validates them BEFORE
opening the stream (so a missing/disabled config surfaces as a normal 400/404
JSON error, not a mid-stream failure). The stream itself runs on a dedicated
AsyncSessionLocal session owned by the generator (not get_db), because the
runner commits per turn for mid-stream durability and get_db only commits at
request end.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.ai.chat.runner import run_chat_stream
from backend.apps.model.user import User
from backend.apps.service import ai_chat_service
from backend.apps.utils.database import AsyncSessionLocal, get_db
from backend.apps.utils.security import get_current_user
from backend.apps.utils.types import OptionalSnowflakeId, SnowflakeId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/ai/chat", tags=["AiChat"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering (nginx etc.)
}


# ── Request / Response schemas ───────────────────────────────────────────────


class ChatRequest(BaseModel):
    session_id: OptionalSnowflakeId = Field(None, description="会话ID(空=新建会话)")
    message: str = Field(..., min_length=1, description="用户消息")
    config_id: OptionalSnowflakeId = Field(None, description="使用的AI配置ID(空=用默认)")
    note_id: OptionalSnowflakeId = Field(
        None,
        description="绑定的笔记ID(空=普通对话;笔记AI助手侧边栏传入,新建会话时绑定)",
    )


class ChatSessionResponse(BaseModel):
    session_id: SnowflakeId
    user_id: SnowflakeId
    config_id: SnowflakeId
    model_id: SnowflakeId
    api_format: str
    session_title: str
    note_id: Optional[SnowflakeId] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ChatMessageResponse(BaseModel):
    message_id: SnowflakeId
    session_id: SnowflakeId
    role: str
    content: Optional[str] = None
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    is_error: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    iter_index: int
    created_at: Optional[str] = None


class ChatSessionUpdateRequest(BaseModel):
    session_title: str = Field(..., min_length=1, max_length=200, description="新标题")


# ── Streaming chat ───────────────────────────────────────────────────────────


@router.post("", summary="AI 对话(SSE 流式)")
async def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message and stream the AI reply (with tool calls) over SSE.

    If ``session_id`` is omitted a new session is created. Config/model are
    resolved and validated before streaming; errors return as normal JSON
    (400/404), not inside the stream.
    """
    config_id = int(body.config_id) if body.config_id is not None else None
    config, model = await ai_chat_service.resolve_chat_config(db, config_id)

    # Get-or-create the session on the request-scoped db (validated before stream).
    if body.session_id is not None:
        session = await ai_chat_service.get_session(db, int(body.session_id), user.user_id)
    else:
        note_id = int(body.note_id) if body.note_id is not None else None
        session = await ai_chat_service.create_session(
            db,
            user_id=user.user_id,
            config_id=config["config_id"],
            model_id=model.model_id,
            api_format=model.api_format,
            note_id=note_id,
        )
    await db.commit()
    # Detach the snapshot fields we need; the request db closes once we return.
    session_id = session.session_id
    session_title = session.session_title

    config_snapshot = {
        "config_id": config["config_id"],
        "system_prompt": config.get("system_prompt"),
        "tools": config.get("tools") or [],
        "json_output": config.get("json_output"),
        "temperature": config.get("temperature"),
        "top_p": config.get("top_p"),
        "max_tokens": config.get("max_tokens"),
    }
    # Re-fetch a fresh session object inside the generator's own db below.
    user_id = user.user_id
    user_text = body.message
    model_snapshot = model

    async def generate():
        # Dedicated session for the streaming loop (per-turn commits).
        async with AsyncSessionLocal() as stream_db:
            stream_session = await ai_chat_service.get_session(stream_db, session_id, user_id)
            async for chunk in run_chat_stream(
                db=stream_db,
                user_id=user_id,
                session=stream_session,
                config=config_snapshot,
                model=model_snapshot,
                user_text=user_text,
            ):
                yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ── Session management ───────────────────────────────────────────────────────


@router.get("/sessions", response_model=list[ChatSessionResponse], summary="获取对话会话列表")
async def list_sessions(
    note_id: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    nid = int(note_id) if note_id is not None else None
    return await ai_chat_service.list_sessions(db, user.user_id, note_id=nid)


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ChatMessageResponse],
    summary="获取会话历史消息",
)
async def list_messages(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sid = int(session_id)
    return await ai_chat_service.list_messages(db, sid, user.user_id)


@router.post(
    "/sessions/{session_id}/update",
    response_model=ChatSessionResponse,
    summary="重命名会话",
)
async def update_session(
    session_id: str,
    body: ChatSessionUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sid = int(session_id)
    session = await ai_chat_service.rename_session(db, sid, user.user_id, body.session_title)
    return ai_chat_service._session_to_dict(session)


@router.post("/sessions/{session_id}/delete", summary="删除会话")
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sid = int(session_id)
    await ai_chat_service.delete_session(db, sid, user.user_id)
    return {"message": "删除成功"}
