"""Tool base class for the AI tool registry.

A tool is something an AI agent can call. Each tool self-describes (name,
description, JSON-schema ``parameters``) so the metadata can be returned via
the ``/ai-tool`` API and later handed to an LLM as a function/tool definition.
``execute`` performs the action on behalf of a user.

Tools wrap existing services (e.g. note search) — they do not contain new
business logic.
"""

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


class BaseTool(ABC):
    """Abstract tool. Subclasses set the metadata attrs and implement execute."""

    #: Stable tool name — this is what ``ai_configs.tools`` stores.
    name: str = ""
    #: Human/LLM-facing description of what the tool does.
    description: str = ""
    #: JSON Schema describing the parameters the tool accepts.
    parameters: dict[str, Any] = {}

    @abstractmethod
    async def execute(
        self, db: AsyncSession, user_id: int, **params: Any
    ) -> dict[str, Any]:
        """Run the tool for ``user_id`` with the validated ``params``."""
        raise NotImplementedError

    def metadata(self) -> dict[str, Any]:
        """Return the tool's self-description for the /ai-tool API."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


def trim_note(note: dict) -> dict:
    """Trim a note dict to the fields useful for tool results (drop content)."""
    return {
        "note_id": str(note.get("note_id")) if note.get("note_id") is not None else None,
        "note_title": note.get("note_title"),
        "note_summary": note.get("note_summary"),
        "note_tags": note.get("note_tags"),
        "note_word_count": note.get("note_word_count"),
        "updated_at": note.get("updated_at"),
    }
