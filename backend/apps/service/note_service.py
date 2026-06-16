"""Note business logic: CRUD, pagination, and full-text search.

Chinese full-text search:
  PostgreSQL's built-in text search parsers do not tokenize Chinese. We solve
  this in the application layer with jieba: title/content are segmented into
  space-separated tokens before being fed to ``to_tsvector('simple', ...)``,
  and the search keyword is segmented the same way before ``plainto_tsquery``.
  This needs no PostgreSQL extension (no zhparser / pg_jieba required).
"""

from typing import Any, Optional

import jieba
from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.note import Note
from backend.apps.utils.exceptions import NotFoundError

# Text search configuration. 'simple' does no language-specific stemming and
# just lowercases tokens — exactly what we want for pre-segmented Chinese.
_TS_CONFIG = "simple"


# ── Full-text search helpers ─────────────────────────────────────────────────


def _segment(text: Optional[str]) -> str:
    """Segment text into space-separated tokens using jieba.

    Works for mixed Chinese/English text. Returns '' for empty input.
    """
    if not text:
        return ""
    return " ".join(jieba.cut_for_search(text))


def _build_search_vector(title: Optional[str], content: Optional[str]) -> ColumnElement:
    """Build a weighted tsvector SQL expression from segmented title + content.

    Title gets weight 'A' (higher relevance), content gets weight 'B'.
    """
    seg_title = _segment(title)
    seg_content = _segment(content)
    return func.setweight(
        func.to_tsvector(_TS_CONFIG, seg_title), "A"
    ).op("||")(
        func.setweight(func.to_tsvector(_TS_CONFIG, seg_content), "B")
    )


async def list_notes(
    db: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    category_id: Optional[int] = None,
    keyword: Optional[str] = None,
    is_pinned: Optional[int] = None,
) -> dict:
    """
    List notes with pagination, optional category filter and full-text search.
    Returns {items, total, page, page_size}.
    """
    base_query: Select = select(Note).where(
        Note.user_id == user_id,
        Note.is_deleted == 0,
    )

    # Category filter
    if category_id is not None:
        base_query = base_query.where(Note.category_id == category_id)

    # Pinned filter
    if is_pinned is not None:
        base_query = base_query.where(Note.is_pinned == is_pinned)

    # Chinese full-text search: segment the keyword the same way as the index
    if keyword and keyword.strip():
        segmented = _segment(keyword.strip())
        if segmented:
            ts_query = func.plainto_tsquery(_TS_CONFIG, segmented)
            base_query = base_query.where(Note.search_vector.op("@@")(ts_query))

    # Count total
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Order: pinned first, then by updated_at desc
    order_query = base_query.order_by(
        Note.is_pinned.desc(),
        Note.updated_at.desc(),
    )

    # Paginate
    offset = (page - 1) * page_size
    result = await db.execute(order_query.offset(offset).limit(page_size))
    notes = result.scalars().all()

    return {
        "items": [_note_to_dict(n) for n in notes],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
) -> Optional[dict]:
    """Get a single note by ID. Returns None if not found or deleted."""
    result = await db.execute(
        select(Note).where(
            Note.note_id == note_id,
            Note.user_id == user_id,
            Note.is_deleted == 0,
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        return None
    return _note_to_dict(note)


async def create_note(
    db: AsyncSession,
    user_id: int,
    note_title: str,
    note_content: Optional[str] = None,
    category_id: Optional[int] = None,
    note_tags: Optional[list[str]] = None,
    is_pinned: int = 0,
) -> Note:
    """Create a new note and populate its search_vector."""
    word_count = len(note_content) if note_content else 0
    note = Note(
        user_id=user_id,
        category_id=category_id,
        note_title=note_title,
        note_content=note_content,
        note_tags=note_tags or [],
        is_pinned=is_pinned,
        note_word_count=word_count,
        search_vector=_build_search_vector(note_title, note_content),
    )
    db.add(note)
    await db.flush()
    return note


async def update_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
    fields: dict[str, Any],
) -> Note:
    """Update a note with only the provided fields.

    ``fields`` contains only keys the client actually sent (built via
    ``model_dump(exclude_unset=True)``), so omitting ``category_id`` leaves
    it unchanged instead of resetting it to NULL.

    Raises NotFoundError if the note does not exist.
    """
    result = await db.execute(
        select(Note).where(
            Note.note_id == note_id,
            Note.user_id == user_id,
            Note.is_deleted == 0,
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise NotFoundError("笔记不存在")

    if "note_title" in fields:
        note.note_title = fields["note_title"]

    if "note_content" in fields:
        content = fields["note_content"]
        note.note_content = content
        note.note_word_count = len(content) if content else 0

    if "category_id" in fields:
        note.category_id = fields["category_id"]

    if "note_summary" in fields:
        note.note_summary = fields["note_summary"]

    if "note_tags" in fields:
        note.note_tags = fields["note_tags"]

    if "is_pinned" in fields:
        note.is_pinned = fields["is_pinned"]

    # Recompute search_vector if title or content changed
    if "note_title" in fields or "note_content" in fields:
        note.search_vector = _build_search_vector(note.note_title, note.note_content)

    await db.flush()
    return note


async def delete_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
) -> None:
    """Soft delete a note."""
    result = await db.execute(
        select(Note).where(
            Note.note_id == note_id,
            Note.user_id == user_id,
            Note.is_deleted == 0,
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise NotFoundError("笔记不存在")

    note.is_deleted = 1
    await db.flush()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _note_to_dict(note: Note) -> dict:
    return {
        "note_id": note.note_id,
        "user_id": note.user_id,
        "category_id": note.category_id,
        "note_title": note.note_title,
        "note_content": note.note_content,
        "note_summary": note.note_summary,
        "note_tags": note.note_tags,
        "is_pinned": note.is_pinned,
        "note_word_count": note.note_word_count,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }
