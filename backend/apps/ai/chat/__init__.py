"""Internal message model + provider request translation (pure, no I/O).

The chat runner works with provider-agnostic internal message dataclasses.
``build_openai_request`` / ``build_anthropic_request`` translate an internal
history into the exact request shape each SDK expects, including system prompt
handling, tool definitions, assistant tool-call turns, and tool results.
"""
