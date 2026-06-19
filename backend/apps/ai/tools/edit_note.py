"""Edit a note's title/content/summary/tags (partial update).

Only the fields actually passed are changed (omitted fields are left alone,
mirroring the API's ``exclude_unset`` semantics). Each edit records a history
snapshot tagged ``change_source=AI``, so AI edits are rollback-able just like
human edits.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.ai.tools.base import BaseTool, trim_note
from backend.apps.model.note_history import CHANGE_SOURCE_AI
from backend.apps.service import note_service
from backend.apps.utils.exceptions import NotFoundError


class EditNoteTool(BaseTool):
    """Edit an existing note owned by the user (partial update)."""

    name = "edit_note"
    description = (
        "编辑指定笔记的内容，可修改标题、正文(Markdown)、摘要、标签。"
        "仅传入需要修改的字段，省略的字段保持不变。每次编辑会记录到笔记历史，可回滚。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "note_id": {
                "type": "string",
                "description": "笔记ID（字符串形式的雪花ID）",
            },
            "note_title": {
                "type": "string",
                "description": "新的笔记标题（不传则不变）",
            },
            "note_content": {
                "type": "string",
                "description": "新的笔记正文(Markdown)（不传则不变）",
            },
            "note_summary": {
                "type": "string",
                "description": "新的笔记摘要（不传则不变）",
            },
            "note_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "新的标签数组（不传则不变）",
            },
        },
        "required": ["note_id"],
    }

    async def execute(
        self, db: AsyncSession, user_id: int, **params: Any
    ) -> dict[str, Any]:
        note_id = int(params["note_id"])

        # Collect only the fields actually provided so omitted ones are not
        # reset (mirrors exclude_unset semantics).
        fields: dict[str, Any] = {}
        for key in ("note_title", "note_content", "note_summary", "note_tags"):
            if key in params:
                fields[key] = params[key]

        if not fields:
            return {"updated": False, "message": "没有需要更新的字段"}

        try:
            note = await note_service.update_note(
                db=db,
                user_id=user_id,
                note_id=note_id,
                fields=fields,
                change_source=CHANGE_SOURCE_AI,
            )
        except NotFoundError:
            return {"updated": False, "message": "笔记不存在或无权访问"}

        return {"updated": True, "note": trim_note(note_service._note_to_dict(note))}
