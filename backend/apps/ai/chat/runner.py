"""The streaming chat runner: tool-calling loop + SSE emission.

Given a resolved session/config/model and the user's new message, this generator
runs the provider-agnostic tool-calling loop, emitting SSE events as it goes,
and persists every user / assistant / tool message to the DB (committing per
turn for mid-stream durability). It owns the DB session passed in (the streaming
endpoint opens a dedicated AsyncSessionLocal, NOT get_db, so per-turn commits
work — get_db only commits at request end).

SSE event protocol (UTF-8 bytes, ``event: <type>\\ndata: <json>\\n\\n``):
  session    {session_id, session_title}     — sent first, binds the session
  text       {delta}                          — a text fragment
  tool_start {id, name}                       — a tool call begins
  tool_end   {id, name, result, is_error}     — a tool finished
  done       {session_id, session_title}      — normal completion
  error      {message}                        — unrecoverable error
"""

import json
import logging
from typing import Any, AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.ai.chat.messages import (
    AssistantMessage,
    Sampling,
    ToolResultMessage,
    build_anthropic_request,
    build_openai_request,
)
from backend.apps.ai.chat.provider import make_provider
from backend.apps.ai.tools import registry
from backend.apps.model.ai_chat import AiChatSession
from backend.apps.model.ai_model import AiModel
from backend.apps.service import ai_chat_service, note_service
from backend.apps.utils.exceptions import BusinessError

logger = logging.getLogger(__name__)

MAX_ITERS = 8

# Cap how much of the note body is injected as context (chars). Longer notes are
# truncated with a notice so the model still knows it was cut off.
_NOTE_CONTEXT_MAX_CHARS = 12000


async def _build_note_context(
    db: AsyncSession, user_id: int, note_id: int
) -> Optional[str]:
    """Build a system-prompt block describing the note bound to the session.

    Re-fetches the note each turn so edits made while chatting are reflected.
    Returns None if the note is gone (deleted / not owned) — in which case we
    fall back to the plain system prompt rather than failing the turn.
    """
    note = await note_service.get_note(db, user_id, note_id)
    if note is None:
        return None
    title = note.get("note_title") or "无标题"
    tags = note.get("note_tags") or []
    body = note.get("note_content") or ""
    truncated = False
    if len(body) > _NOTE_CONTEXT_MAX_CHARS:
        body = body[:_NOTE_CONTEXT_MAX_CHARS]
        truncated = True
    tag_str = "、".join(tags) if tags else "无"
    lines = [
        "【当前笔记上下文】",
        f"笔记ID：{note_id}",
        f"标题：{title}",
        f"标签：{tag_str}",
        "内容：",
        body or "（当前为空笔记）",
    ]
    if truncated:
        lines.append("（内容较长，已截断，可使用 read_note 工具读取完整内容）")
    lines.append(
        "用户正在编辑上面这篇笔记。所有写作、续写、润色、生成正文等操作都必须"
        f"使用 edit_note 工具修改这篇笔记本身（note_id={note_id}），"
        "禁止用 create_note 新建笔记，除非用户明确要求另存为新笔记。"
    )
    return "\n".join(lines)


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


async def run_chat_stream(
    *,
    db: AsyncSession,
    user_id: int,
    session: AiChatSession,
    config: dict,
    model: AiModel,
    user_text: str,
) -> AsyncIterator[bytes]:
    """Run the chat turn and yield SSE byte chunks.

    ``db`` is owned by the caller (a dedicated session); we commit here at
    durability points. ``session`` is already created/validated by the endpoint.
    """
    session_id = session.session_id

    # 1. Persist the user message + auto-title, then commit so it survives.
    await ai_chat_service.add_message(
        db, session_id=session_id, role="user", content=user_text, iter_index=0
    )
    await ai_chat_service.auto_title_if_needed(db, session, user_text)
    await db.commit()

    # Emit the bound session first (lets the frontend capture a new session_id).
    yield _sse("session", {
        "session_id": str(session_id),
        "session_title": session.session_title,
    })

    try:
        async for chunk in _run_loop(db, user_id, session, config, model, user_text):
            yield chunk
    except Exception as exc:
        logger.exception("Chat stream error: session_id=%s", session_id)
        yield _sse("error", {"message": str(exc) or "对话出错"})
        return

    yield _sse("done", {
        "session_id": str(session_id),
        "session_title": session.session_title,
    })


async def _run_loop(
    db: AsyncSession,
    user_id: int,
    session: AiChatSession,
    config: dict,
    model: AiModel,
    user_text: str,
) -> AsyncIterator[bytes]:
    session_id = session.session_id

    # 2. Load full history (incl. the just-saved user message).
    rows = await ai_chat_service.list_messages(db, session_id, user_id)
    history = ai_chat_service.rows_to_history(rows)

    # 3. Resolve enabled tools from the registry.
    config_tools = config.get("tools") or []
    tool_metas: list[dict] = []
    for name in config_tools:
        tool = registry.get_tool(name)
        if tool is not None:
            tool_metas.append(tool.metadata())
        else:
            logger.warning("Chat tool %r not registered; skipping", name)

    # 4. Build sampling bundle.
    sampling = Sampling(
        temperature=config.get("temperature"),
        top_p=config.get("top_p"),
        max_tokens=config.get("max_tokens") or model.max_tokens or 4096,
        json_output=bool(config.get("json_output")),
    )
    system_prompt = config.get("system_prompt")

    # If the session is bound to a note, prepend the note's content as context
    # so the model knows which note it's helping with. Re-fetched each turn.
    if session.note_id:
        note_ctx = await _build_note_context(db, user_id, session.note_id)
        if note_ctx:
            system_prompt = (
                f"{note_ctx}\n\n{system_prompt}" if system_prompt else note_ctx
            )

    provider = make_provider(model)

    # 5. Tool-calling loop.
    for iter_index in range(1, MAX_ITERS + 1):
        if model.api_format == "anthropic":
            request = build_anthropic_request(
                model=model.model,
                system_prompt=system_prompt,
                history=history,
                tool_metas=tool_metas,
                sampling=sampling,
            )
        else:
            request = build_openai_request(
                model=model.model,
                system_prompt=system_prompt,
                history=history,
                tool_metas=tool_metas,
                sampling=sampling,
            )

        assistant_text = ""
        tool_calls: list[Any] = []
        finish_reason: Optional[str] = None
        prompt_tokens: Optional[int] = None
        completion_tokens: Optional[int] = None

        async for delta in provider.stream_turn(request):
            if delta.text:
                assistant_text += delta.text
                yield _sse("text", {"delta": delta.text})
            for stub in delta.tool_starts:
                yield _sse("tool_start", {"id": stub.id, "name": stub.name})
            if delta.tool_done:
                tool_calls.extend(delta.tool_done)
            if delta.finish_reason is not None:
                finish_reason = delta.finish_reason
            if delta.prompt_tokens is not None:
                prompt_tokens = delta.prompt_tokens
            if delta.completion_tokens is not None:
                completion_tokens = delta.completion_tokens

        # Persist this assistant turn.
        tc_dicts = [
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
            for tc in tool_calls
        ]
        await ai_chat_service.add_message(
            db,
            session_id=session_id,
            role="assistant",
            content=assistant_text or None,
            tool_calls=tc_dicts,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            iter_index=iter_index,
        )
        await db.commit()

        # Append to in-memory history for the next iteration.
        history.append(
            AssistantMessage(
                content=assistant_text or None,
                tool_calls=tool_calls,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        )

        # No tool calls → turn complete.
        is_tool_finish = finish_reason in ("tool_calls", "tool_use")
        if not tool_calls or not is_tool_finish:
            return

        # Execute each tool call, persist results, append to history.
        for tc in tool_calls:
            result_str, is_error = await _execute_tool(
                db, user_id, tc.name, tc.arguments, config_tools
            )
            yield _sse("tool_end", {
                "id": tc.id,
                "name": tc.name,
                "result": result_str,
                "is_error": is_error,
            })
            await ai_chat_service.add_message(
                db,
                session_id=session_id,
                role="tool",
                content=result_str,
                tool_call_id=tc.id,
                tool_name=tc.name,
                is_error=1 if is_error else 0,
                iter_index=iter_index,
            )
            await db.commit()
            history.append(
                ToolResultMessage(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    content=result_str,
                    is_error=is_error,
                )
            )

    # Loop exhausted without a final answer.
    yield _sse("text", {"delta": "\n\n（已达到最大工具调用次数，停止。）"})


async def _execute_tool(
    db: AsyncSession,
    user_id: int,
    name: str,
    arguments: dict,
    config_tools: list,
) -> tuple[str, bool]:
    """Execute one tool call. Returns (result_string, is_error).

    Never raises — failures are returned as error tool results so the model can
    react and the stream continues.
    """
    if name not in config_tools:
        return f"工具 {name} 未启用或不存在", True
    tool = registry.get_tool(name)
    if tool is None:
        return f"工具 {name} 未启用或不存在", True
    try:
        result = await tool.execute(db, user_id, **arguments)
        return json.dumps(result, ensure_ascii=False, default=str), False
    except BusinessError as e:
        logger.warning("Tool %s business error: %s", name, e.message)
        return f"工具执行失败: {e.message}", True
    except Exception as e:  # noqa: BLE001 — tool errors must not kill the stream
        logger.exception("Tool %s raised", name)
        return f"工具执行异常: {e}", True
