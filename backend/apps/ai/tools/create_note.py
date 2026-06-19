"""Create a new note for the current user.

The created note is recorded as a history snapshot tagged
``change_source=AI``. No delete tool is provided by design.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.ai.tools.base import BaseTool, trim_note
from backend.apps.model.note_history import CHANGE_SOURCE_AI
from backend.apps.service import note_service


class CreateNoteTool(BaseTool):
    """Create a new note owned by the current user."""

    name = "create_note"
    description = "为当前用户新建一篇笔记。可指定标题、正文(Markdown)、分类、标签。"
    parameters = {
        "type": "object",
        "properties": {
            "note_title": {
                "type": "string",
                "description": "笔记标题",
            },
            "note_content": {
                "type": "string",
                "description": "笔记正文(Markdown)",
            },
            "category_id": {
                "type": "string",
                "description": "所属分类ID（字符串形式的雪花ID，不传则为未分类）",
            },
            "note_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "标签数组",
            },
        },
        "required": ["note_title"],
    }

    async def execute(
        self, db: AsyncSession, user_id: int, **params: Any
    ) -> dict[str, Any]:
        category_id_raw = params.get("category_id")
        category_id = int(category_id_raw) if category_id_raw is not None else None

        note = await note_service.create_note(
            db=db,
            user_id=user_id,
            note_title=params["note_title"],
            note_content=params.get("note_content"),
            category_id=category_id,
            note_tags=params.get("note_tags"),
            change_source=CHANGE_SOURCE_AI,
        )
        return {"created": True, "note": trim_note(note_service._note_to_dict(note))}
