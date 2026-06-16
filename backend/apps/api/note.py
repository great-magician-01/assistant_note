"""Note API endpoints — /note/v1/"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.user import User
from backend.apps.service import note_service
from backend.apps.utils.database import get_db
from backend.apps.utils.exceptions import NotFoundError
from backend.apps.utils.security import get_current_user

router = APIRouter(prefix="/note/v1", tags=["Note"])


# ── Request / Response schemas ───────────────────────────────────────────────


class NoteCreateRequest(BaseModel):
    note_title: str = Field(..., min_length=1, max_length=255, description="笔记标题")
    note_content: Optional[str] = Field(None, description="Markdown内容")
    category_id: Optional[int] = Field(None, description="所属分类ID")
    note_tags: Optional[list[str]] = Field(None, description="标签列表")
    is_pinned: int = Field(0, description="是否置顶(0-否 1-是)")


class NoteUpdateRequest(BaseModel):
    note_title: Optional[str] = Field(None, min_length=1, max_length=255, description="笔记标题")
    note_content: Optional[str] = Field(None, description="Markdown内容")
    category_id: Optional[int] = Field(None, description="所属分类ID")
    note_summary: Optional[str] = Field(None, max_length=500, description="AI生成摘要")
    note_tags: Optional[list[str]] = Field(None, description="标签列表")
    is_pinned: Optional[int] = Field(None, description="是否置顶(0-否 1-是)")


class NoteResponse(BaseModel):
    note_id: int
    user_id: int
    category_id: Optional[int] = None
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


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=NoteListResponse, summary="获取笔记列表")
async def list_notes(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    category_id: Optional[int] = Query(None, description="分类ID筛选"),
    keyword: Optional[str] = Query(None, description="全文搜索关键词"),
    is_pinned: Optional[int] = Query(None, description="是否置顶筛选"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await note_service.list_notes(
        db=db,
        user_id=user.user_id,
        page=page,
        page_size=page_size,
        category_id=category_id,
        keyword=keyword,
        is_pinned=is_pinned,
    )


@router.get("/{note_id}", response_model=NoteResponse, summary="获取笔记详情")
async def get_note(
    note_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await note_service.get_note(db, user.user_id, note_id)
    if result is None:
        raise NotFoundError("笔记不存在")
    return result


@router.post("", response_model=NoteResponse, summary="创建笔记")
async def create_note(
    body: NoteCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    note = await note_service.create_note(
        db=db,
        user_id=user.user_id,
        note_title=body.note_title,
        note_content=body.note_content,
        category_id=body.category_id,
        note_tags=body.note_tags,
        is_pinned=body.is_pinned,
    )
    return note_service._note_to_dict(note)


@router.put("/{note_id}", response_model=NoteResponse, summary="更新笔记")
async def update_note(
    note_id: int,
    body: NoteUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # exclude_unset: only pass fields the client actually sent, so omitting
    # category_id leaves it unchanged instead of resetting it to NULL.
    fields = body.model_dump(exclude_unset=True)
    note = await note_service.update_note(
        db=db,
        user_id=user.user_id,
        note_id=note_id,
        fields=fields,
    )
    return note_service._note_to_dict(note)


@router.delete("/{note_id}", summary="删除笔记")
async def delete_note(
    note_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await note_service.delete_note(db, user.user_id, note_id)
    return {"message": "删除成功"}
