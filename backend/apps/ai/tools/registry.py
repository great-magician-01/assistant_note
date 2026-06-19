"""Tool registry — holds all available tools, looked up by name.

``ai_configs.tools`` stores tool names; the registry maps those names back to
the tool implementations. Add a new tool by subclassing BaseTool and appending
an instance to ``_TOOLS`` below.
"""

from typing import Optional

from backend.apps.ai.tools.base import BaseTool
from backend.apps.ai.tools.create_note import CreateNoteTool
from backend.apps.ai.tools.edit_note import EditNoteTool
from backend.apps.ai.tools.read_note import ReadNoteTool
from backend.apps.ai.tools.search_notes import SearchNotesTool
from backend.apps.ai.tools.search_notes_by_tag import SearchNotesByTagTool

# Ordered list of every available tool. Order is preserved in the /ai-tool API.
_TOOLS: list[BaseTool] = [
    SearchNotesTool(),
    SearchNotesByTagTool(),
    ReadNoteTool(),
    EditNoteTool(),
    CreateNoteTool(),
]

_BY_NAME: dict[str, BaseTool] = {t.name: t for t in _TOOLS}


def list_tools() -> list[BaseTool]:
    """Return all registered tools (in registration order)."""
    return list(_TOOLS)


def list_tool_metadata() -> list[dict]:
    """Return self-describing metadata for every tool (for the /ai-tool API)."""
    return [t.metadata() for t in _TOOLS]


def get_tool(name: str) -> Optional[BaseTool]:
    """Look up a tool by name, or None if unknown."""
    return _BY_NAME.get(name)
