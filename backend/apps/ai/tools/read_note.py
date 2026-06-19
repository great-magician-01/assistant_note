"""Read a single note's full content (including body) by ID.

Unlike ``search_notes`` (which trims content), this returns the complete note
so an AI can read it before editing. Read-only — does not record history.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.ai.tools.base import BaseTool
from backend.apps.service import note_service


class ReadNoteTool(BaseTool):
    """Read the full content of one note owned by the user."""

    name = "read_note"
    description = "读取指定笔记的完整内容（含标题、正文Markdown、摘要、标签等）。用于在编辑前获取笔记上下文。"
    parameters = {
        "type": "object",
        "properties": {
            "note_id": {
                "type": "string",
                "description": "笔记ID（字符串形式的雪花ID）",
            },
        },
        "required": ["note_id"],
    }

    async def execute(
        self, db: AsyncSession, user_id: int, **params: Any
    ) -> dict[str, Any]:
        note_id = int(params["note_id"])
        note = await note_service.get_note(db, user_id, note_id)
        if note is None:
            return {"found": False, "message": "笔记不存在或无权访问"}
        # Return the full note (content included) so the AI can read it.
        return {**note, "found": True}
