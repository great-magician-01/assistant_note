"""Note API endpoints — /v1/note/"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.user import User
from backend.apps.service import note_service
from backend.apps.utils.database import get_db
from backend.apps.utils.exceptions import NotFoundError
from backend.apps.utils.security import get_current_user
from backend.apps.utils.types import OptionalSnowflakeId, SnowflakeId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/note", tags=["Note"])


# ── Request / Response schemas ───────────────────────────────────────────────


class NoteCreateRequest(BaseModel):
    note_title: str = Field(..., min_length=1, max_length=255, description="笔记标题")
    note_content: Optional[str] = Field(None, description="Markdown内容")
    category_id: OptionalSnowflakeId = Field(None, description="所属分类ID")
    note_tags: Optional[list[str]] = Field(None, description="标签列表")
    is_pinned: int = Field(0, description="是否置顶(0-否 1-是)")


class NoteUpdateRequest(BaseModel):
    note_title: Optional[str] = Field(None, min_length=1, max_length=255, description="笔记标题")
    note_content: Optional[str] = Field(None, description="Markdown内容")
    category_id: OptionalSnowflakeId = Field(None, description="所属分类ID")
    note_summary: Optional[str] = Field(None, max_length=500, description="AI生成摘要")
    note_tags: Optional[list[str]] = Field(None, description="标签列表")
    is_pinned: Optional[int] = Field(None, description="是否置顶(0-否 1-是)")


class NoteResponse(BaseModel):
    note_id: SnowflakeId
    user_id: SnowflakeId
    category_id: OptionalSnowflakeId = None
    note_title: str
    note_content: Optional[str] = None
    note_summary: Optional[str] = None
    note_tags: Optional[list] = None
    is_pinned: int
    note_word_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class NoteListResponse(BaseModel):
    items: list[NoteResponse]
    total: int
    page: int
    page_size: int


class MoveNotesRequest(BaseModel):
    note_ids: list[SnowflakeId] = Field(..., min_length=1, description="要移动的笔记ID列表")
    category_id: OptionalSnowflakeId = Field(None, description="目标分类ID(None=移到未分类)")


class MoveNotesResponse(BaseModel):
    moved: int
    total: int
    category_id: OptionalSnowflakeId = None


class NoteTreeItem(BaseModel):
    """Lightweight note used inside the combined category/note tree.

    Excludes ``note_content`` (fetched separately via GET /note/{id}); carries
    a short ``note_preview`` instead so the sidebar tree stays small.
    """

    note_id: SnowflakeId
    category_id: OptionalSnowflakeId = None
    note_title: str
    note_summary: Optional[str] = None
    note_preview: Optional[str] = None
    note_tags: Optional[list] = None
    is_pinned: int
    note_word_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CategoryTreeNode(BaseModel):
    category_id: SnowflakeId
    user_id: SnowflakeId
    category_name: str
    category_icon: Optional[str] = None
    category_sort: int
    parent_id: OptionalSnowflakeId = None
    children: list["CategoryTreeNode"] = []
    notes: list[NoteTreeItem] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class NoteTreeResponse(BaseModel):
    categories: list[CategoryTreeNode]
    uncategorized: list[NoteTreeItem]
    total: int


# Resolve the CategoryTreeNode self-reference now that both classes exist.
CategoryTreeNode.model_rebuild()


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/tree", response_model=NoteTreeResponse, summary="获取笔记树(分类+笔记)")
async def get_note_tree(
    keyword: Optional[str] = Query(None, description="全文搜索关键词"),
    tag: Optional[str] = Query(None, description="标签筛选"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return categories and notes as a single tree for the sidebar.

    Each category node carries its notes (plus sub-categories); notes with no
    (or deleted) category land in ``uncategorized``. Optional ``keyword``/tag
    filters restrict the notes and prune empty category branches.
    """
    logger.debug("GET /note/tree: user_id=%s, keyword=%r, tag=%r", user.user_id, keyword, tag)
    return await note_service.list_notes_tree(
        db=db,
        user_id=user.user_id,
        keyword=keyword,
        tag=tag,
    )


@router.get("", response_model=NoteListResponse, summary="获取笔记列表")
async def list_notes(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    category_id: Optional[int] = Query(None, description="分类ID筛选"),
    keyword: Optional[str] = Query(None, description="全文搜索关键词"),
    is_pinned: Optional[int] = Query(None, description="是否置顶筛选"),
    tag: Optional[str] = Query(None, description="标签筛选"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.debug("GET /note: user_id=%s, page=%s, page_size=%s, category_id=%s, keyword=%r, is_pinned=%s, tag=%r",
                 user.user_id, page, page_size, category_id, keyword, is_pinned, tag)
    return await note_service.list_notes(
        db=db,
        user_id=user.user_id,
        page=page,
        page_size=page_size,
        category_id=category_id,
        keyword=keyword,
        is_pinned=is_pinned,
        tag=tag,
    )


@router.get("/tags", response_model=list[str], summary="获取所有标签")
async def list_tags(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all distinct tags used across the current user's notes."""
    logger.debug("GET /note/tags: user_id=%s", user.user_id)
    return await note_service.list_tags(db, user.user_id)


@router.post("/move", response_model=MoveNotesResponse, summary="移动笔记到指定分类")
async def move_notes(
    body: MoveNotesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Move one or more notes to a target category (single note = list of one).
    Pass category_id=null to move them to uncategorized.
    """
    note_ids = [int(nid) for nid in body.note_ids]
    category_id = int(body.category_id) if body.category_id is not None else None
    logger.debug("POST /note/move: user_id=%s, note_ids=%s, category_id=%s",
                 user.user_id, note_ids, category_id)
    return await note_service.move_notes(
        db=db,
        user_id=user.user_id,
        note_ids=note_ids,
        category_id=category_id,
    )


@router.get("/{note_id}", response_model=NoteResponse, summary="获取笔记详情")
async def get_note(
    note_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    nid = int(note_id)
    logger.debug("GET /note/%s: user_id=%s", nid, user.user_id)
    result = await note_service.get_note(db, user.user_id, nid)
    if result is None:
        raise NotFoundError("笔记不存在")
    return result


@router.post("", response_model=NoteResponse, summary="创建笔记")
async def create_note(
    body: NoteCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    category_id = int(body.category_id) if body.category_id is not None else None
    logger.debug("POST /note: user_id=%s, title=%r, category_id=%s", user.user_id, body.note_title, category_id)
    note = await note_service.create_note(
        db=db,
        user_id=user.user_id,
        note_title=body.note_title,
        note_content=body.note_content,
        category_id=category_id,
        note_tags=body.note_tags,
        is_pinned=body.is_pinned,
    )
    return note_service._note_to_dict(note)


@router.post("/{note_id}/update", response_model=NoteResponse, summary="更新笔记")
async def update_note(
    note_id: str,
    body: NoteUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # exclude_unset: only pass fields the client actually sent, so omitting
    # category_id leaves it unchanged instead of resetting it to NULL.
    fields = body.model_dump(exclude_unset=True)
    if "category_id" in fields and fields["category_id"] is not None:
        fields["category_id"] = int(fields["category_id"])
    nid = int(note_id)
    logger.debug("PUT /note/%s: user_id=%s, fields=%s", nid, user.user_id, list(fields.keys()))
    note = await note_service.update_note(
        db=db,
        user_id=user.user_id,
        note_id=nid,
        fields=fields,
    )
    return note_service._note_to_dict(note)


@router.post("/{note_id}/delete", summary="删除笔记")
async def delete_note(
    note_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    nid = int(note_id)
    logger.debug("DELETE /note/%s: user_id=%s", nid, user.user_id)
    await note_service.delete_note(db, user.user_id, nid)
    return {"message": "删除成功"}
