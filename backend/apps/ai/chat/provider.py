"""Provider abstraction over OpenAI-format and Anthropic-format model APIs.

Both providers expose ``stream_turn(request) -> AsyncIterator[StreamDelta]``,
yielding normalized deltas so the runner is provider-agnostic. The provider-
specific streaming accumulation (OpenAI delta.tool_calls by index; Anthropic
content_block_start/delta/stop events) lives entirely inside each
``stream_turn``.

Clients are constructed per call from the resolved AiModel (base_url/api_key).
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

import httpx

from backend.apps.model.ai_model import AiModel
from backend.apps.ai.chat.messages import ToolCall
from backend.apps.utils.exceptions import BusinessError

logger = logging.getLogger(__name__)

# Shared HTTP timeouts (seconds). Long read timeout accommodates slow model
# generation; connect stays short so misconfigured base_urls fail fast.
_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)


@dataclass
class ToolCallStub:
    """A tool call whose id+name are known but arguments may still be streaming."""

    id: str
    name: str


@dataclass
class StreamDelta:
    """One normalized chunk emitted by a provider's stream_turn."""

    text: Optional[str] = None
    tool_starts: list[ToolCallStub] = field(default_factory=list)
    tool_done: list[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


class ChatProvider(ABC):
    """Provider-agnostic streaming chat interface."""

    @abstractmethod
    async def stream_turn(self, request: dict) -> AsyncIterator[StreamDelta]:
        """Stream one model turn, yielding normalized deltas."""
        raise NotImplementedError
        # yield is present so the type checker sees an async generator.
        yield StreamDelta()  # pragma: no cover


def make_provider(model: AiModel) -> ChatProvider:
    """Construct the right provider for the model's api_format."""
    if model.api_format == "openai":
        return OpenAIProvider(model)
    if model.api_format == "anthropic":
        return AnthropicProvider(model)
    raise BusinessError(f"不支持的接口格式: {model.api_format}")


# ── OpenAI ───────────────────────────────────────────────────────────────────


class OpenAIProvider(ChatProvider):
    """OpenAI-compatible (DeepSeek, OpenAI, etc.) via the openai SDK."""

    def __init__(self, model: AiModel) -> None:
        from openai import AsyncOpenAI

        self._model = model
        self._client = AsyncOpenAI(
            base_url=model.base_url,
            api_key=model.api_key,
            timeout=_HTTP_TIMEOUT,
        )

    async def stream_turn(self, request: dict) -> AsyncIterator[StreamDelta]:
        # The model id in the request overrides the pool's `model` field, but
        # the caller (runner) sets it from the same model — keep request as-is.
        stream = await self._client.chat.completions.create(**request)

        # Accumulate tool calls by index across delta chunks.
        tool_acc: dict[int, dict[str, Any]] = {}
        seen_starts: set[int] = set()
        finish_reason: Optional[str] = None
        usage = None

        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            delta = getattr(choice, "delta", None)

            if delta is not None:
                # Text fragment.
                text = getattr(delta, "content", None)
                if text:
                    yield StreamDelta(text=text)

                # Tool-call deltas (accumulated by index).
                tcs = getattr(delta, "tool_calls", None) or []
                for tc in tcs:
                    idx = getattr(tc, "index", 0) or 0
                    slot = tool_acc.setdefault(idx, {"id": None, "name": None, "args": ""})
                    fn = getattr(tc, "function", None)
                    if getattr(tc, "id", None):
                        slot["id"] = tc.id
                    if fn is not None:
                        if getattr(fn, "name", None):
                            slot["name"] = fn.name
                        if getattr(fn, "arguments", None):
                            slot["args"] += fn.arguments
                    # Emit tool_start as soon as id+name are known.
                    if idx not in seen_starts and slot["id"] and slot["name"]:
                        seen_starts.add(idx)
                        yield StreamDelta(tool_starts=[ToolCallStub(id=slot["id"], name=slot["name"])])

            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason

        # Finalize tool calls in index order.
        done: list[ToolCall] = []
        for idx in sorted(tool_acc):
            slot = tool_acc[idx]
            args_raw = slot.get("args") or "{}"
            try:
                args = json.loads(args_raw) if args_raw.strip() else {}
            except json.JSONDecodeError:
                logger.warning("OpenAI tool args parse failed (name=%s): %r", slot.get("name"), args_raw)
                args = {}
            if slot.get("id") and slot.get("name"):
                done.append(ToolCall(id=slot["id"], name=slot["name"], arguments=args))
        if done:
            yield StreamDelta(tool_done=done)

        yield StreamDelta(
            finish_reason=finish_reason,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
        )


# ── Anthropic ────────────────────────────────────────────────────────────────


class AnthropicProvider(ChatProvider):
    """Anthropic-format via the anthropic SDK."""

    def __init__(self, model: AiModel) -> None:
        from anthropic import AsyncAnthropic

        self._model = model
        # AsyncAnthropic uses base_url for non-default endpoints.
        self._client = AsyncAnthropic(
            base_url=model.base_url,
            api_key=model.api_key,
            timeout=_HTTP_TIMEOUT,
        )

    async def stream_turn(self, request: dict) -> AsyncIterator[StreamDelta]:
        stream = await self._client.messages.create(**request)

        # Per content-block accumulation, keyed by block index.
        block_acc: dict[int, dict[str, Any]] = {}
        cur_index: Optional[int] = None
        seen_starts: set[int] = set()
        stop_reason: Optional[str] = None
        input_tokens: Optional[int] = None
        output_tokens: Optional[int] = None

        async for event in stream:
            etype = getattr(event, "type", None)

            if etype == "message_start":
                msg = getattr(event, "message", None)
                usage = getattr(msg, "usage", None) if msg else None
                if usage is not None:
                    input_tokens = getattr(usage, "input_tokens", None)

            elif etype == "content_block_start":
                idx = getattr(event, "index", 0)
                block = getattr(event, "content_block", None)
                btype = getattr(block, "type", None) if block else None
                slot = block_acc.setdefault(idx, {"type": btype, "id": None, "name": None, "args": ""})
                cur_index = idx
                if btype == "tool_use" and block is not None:
                    bid = getattr(block, "id", None)
                    bname = getattr(block, "name", None)
                    slot["id"] = bid
                    slot["name"] = bname
                    if bid and bname and idx not in seen_starts:
                        seen_starts.add(idx)
                        yield StreamDelta(tool_starts=[ToolCallStub(id=bid, name=bname)])

            elif etype == "content_block_delta":
                d = getattr(event, "delta", None)
                dtype = getattr(d, "type", None) if d else None
                if dtype == "text_delta" and d is not None:
                    txt = getattr(d, "text", None)
                    if txt:
                        yield StreamDelta(text=txt)
                elif dtype == "input_json_delta" and d is not None and cur_index is not None:
                    partial = getattr(d, "partial_json", None)
                    if partial:
                        block_acc[cur_index]["args"] += partial

            elif etype == "content_block_stop":
                idx = getattr(event, "index", 0)
                slot = block_acc.get(idx)
                if slot and slot.get("type") == "tool_use":
                    args_raw = slot.get("args") or "{}"
                    try:
                        args = json.loads(args_raw) if args_raw.strip() else {}
                    except json.JSONDecodeError:
                        logger.warning("Anthropic tool args parse failed (name=%s): %r", slot.get("name"), args_raw)
                        args = {}
                    if slot.get("id") and slot.get("name"):
                        yield StreamDelta(
                            tool_done=[ToolCall(id=slot["id"], name=slot["name"], arguments=args)]
                        )

            elif etype == "message_delta":
                d = getattr(event, "delta", None)
                if d is not None:
                    sr = getattr(d, "stop_reason", None)
                    if sr:
                        stop_reason = sr
                u = getattr(event, "usage", None)
                if u is not None:
                    ot = getattr(u, "output_tokens", None)
                    if ot is not None:
                        output_tokens = ot

            elif etype == "message_stop":
                break

        yield StreamDelta(
            finish_reason=stop_reason,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
