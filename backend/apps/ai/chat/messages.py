"""Internal message model + provider request translation (pure, no I/O).

The chat runner works with provider-agnostic internal message dataclasses.
``build_openai_request`` / ``build_anthropic_request`` translate an internal
history into the exact request shape each SDK expects, including system prompt
handling, tool definitions, assistant tool-call turns, and tool results.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    """A tool call the model requested (or that we replay from history)."""

    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class UserMessage:
    content: str


@dataclass
class AssistantMessage:
    content: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


@dataclass
class ToolResultMessage:
    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False


# ── Sampling bundle ──────────────────────────────────────────────────────────


@dataclass
class Sampling:
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: int = 4096
    json_output: bool = False


# ── Tool definition translation ──────────────────────────────────────────────
# Registry metadata gives {"name","description","parameters" (JSON schema)}.


def to_openai_tools(tool_metas: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in tool_metas
    ]


def to_anthropic_tools(tool_metas: list[dict]) -> list[dict]:
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in tool_metas
    ]


# ── History → provider messages ──────────────────────────────────────────────


def _openai_messages(history: list[Any]) -> list[dict]:
    msgs: list[dict] = []
    for m in history:
        if isinstance(m, UserMessage):
            msgs.append({"role": "user", "content": m.content})
        elif isinstance(m, AssistantMessage):
            entry: dict[str, Any] = {"role": "assistant"}
            # OpenAI wants content null (or omitted) when only tool_calls exist.
            entry["content"] = m.content if m.content else None
            if m.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in m.tool_calls
                ]
            msgs.append(entry)
        elif isinstance(m, ToolResultMessage):
            # OpenAI: one tool message per result.
            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": m.content,
                }
            )
    return msgs


def _anthropic_messages(history: list[Any]) -> list[dict]:
    """Translate history to Anthropic message format.

    Anthropic tool results must be grouped into a SINGLE user message (multiple
    ``tool_result`` blocks), and consecutive same-role messages must be merged.
    We walk the history and coalesce tool-result runs into one user message,
    merging adjacent user/assistant text as needed.
    """
    msgs: list[dict] = []
    for m in history:
        if isinstance(m, UserMessage):
            msgs.append({"role": "user", "content": [{"type": "text", "text": m.content}]})
        elif isinstance(m, AssistantMessage):
            blocks: list[dict] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                blocks.append(
                    {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                )
            if not blocks:
                blocks.append({"type": "text", "text": ""})
            msgs.append({"role": "assistant", "content": blocks})
        elif isinstance(m, ToolResultMessage):
            block = {
                "type": "tool_result",
                "tool_use_id": m.tool_call_id,
                "content": m.content,
            }
            if m.is_error:
                block["is_error"] = True
            # Coalesce consecutive tool results into one user message.
            if msgs and msgs[-1]["role"] == "user" and isinstance(msgs[-1]["content"], list) and msgs[-1]["content"] and msgs[-1]["content"][-1].get("type") == "tool_result":
                msgs[-1]["content"].append(block)
            else:
                msgs.append({"role": "user", "content": [block]})
    return msgs


# ── Request builders ─────────────────────────────────────────────────────────


def build_openai_request(
    *,
    model: str,
    system_prompt: Optional[str],
    history: list[Any],
    tool_metas: list[dict],
    sampling: Sampling,
) -> dict:
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(_openai_messages(history))

    req: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": sampling.max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tool_metas:
        req["tools"] = to_openai_tools(tool_metas)
    if sampling.temperature is not None:
        req["temperature"] = sampling.temperature
    if sampling.top_p is not None:
        req["top_p"] = sampling.top_p
    if sampling.json_output:
        # OpenAI plain-JSON mode (no schema available from the 0/1 flag).
        req["response_format"] = {"type": "json_object"}
    return req


def build_anthropic_request(
    *,
    model: str,
    system_prompt: Optional[str],
    history: list[Any],
    tool_metas: list[dict],
    sampling: Sampling,
) -> dict:
    system_text = system_prompt or ""
    # Anthropic has no native plain-JSON mode; nudge via the system prompt.
    if sampling.json_output and "JSON" not in system_text.upper():
        system_text = (system_text + "\n\n").lstrip() + "请以合法的 JSON 格式回复。"

    req: dict[str, Any] = {
        "model": model,
        "messages": _anthropic_messages(history),
        "max_tokens": sampling.max_tokens,
        "stream": True,
    }
    if system_text:
        req["system"] = system_text
    if tool_metas:
        req["tools"] = to_anthropic_tools(tool_metas)
    if sampling.temperature is not None:
        req["temperature"] = sampling.temperature
    if sampling.top_p is not None:
        req["top_p"] = sampling.top_p
    return req
