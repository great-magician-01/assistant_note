"""Full-text note search tool."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.ai.tools.base import BaseTool, trim_note
from backend.apps.service import note_service


class SearchNotesTool(BaseTool):
    """Full-text search across the user's notes (jieba + tsvector)."""

    name = "search_notes"
    description = "全文搜索当前用户的笔记（按关键词匹配标题与内容）。返回匹配笔记的摘要信息。"
    parameters = {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "搜索关键词",
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
        "required": ["keyword"],
    }

    async def execute(
        self, db: AsyncSession, user_id: int, **params: Any
    ) -> dict[str, Any]:
        keyword = params["keyword"]
        page = int(params.get("page") or 1)
        page_size = int(params.get("page_size") or 10)
        result = await note_service.list_notes(
            db=db,
            user_id=user_id,
            page=page,
            page_size=page_size,
            keyword=keyword,
        )
        return {
            "items": [trim_note(n) for n in result["items"]],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
        }
