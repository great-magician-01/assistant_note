"""Search notes by tag tool."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.ai.tools.base import BaseTool, trim_note
from backend.apps.service import note_service


class SearchNotesByTagTool(BaseTool):
    """Filter the user's notes by a single tag (JSONB containment)."""

    name = "search_notes_by_tag"
    description = "按标签筛选当前用户的笔记。返回匹配笔记的摘要信息。"
    parameters = {
        "type": "object",
        "properties": {
            "tag": {
                "type": "string",
                "description": "标签名",
            },
            "page": {
                "type": "integer",
                "description": "页码，从 1 开始",
                "default": 1,
            },
            "page_size": {
                "type": "integer",
                "description": "每页数量",
                "default": 10,
            },
        },
        "required": ["tag"],
    }

    async def execute(
        self, db: AsyncSession, user_id: int, **params: Any
    ) -> dict[str, Any]:
        tag = params["tag"]
        page = int(params.get("page") or 1)
        page_size = int(params.get("page_size") or 10)
        result = await note_service.list_notes(
            db=db,
            user_id=user_id,
            page=page,
            page_size=page_size,
            tag=tag,
        )
        return {
            "items": [trim_note(n) for n in result["items"]],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
