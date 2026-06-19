"""Note business logic: CRUD, pagination, and full-text search.

Chinese full-text search:
  PostgreSQL's built-in text search parsers do not tokenize Chinese. We solve
  this in the application layer with jieba: title/content are segmented into
  space-separated tokens before being fed to ``to_tsvector('simple', ...)``,
  and the search keyword is segmented the same way before ``plainto_tsquery``.
  This needs no PostgreSQL extension (no zhparser / pg_jieba required).
"""

from typing import Any, Optional
import logging

import jieba
from sqlalchemy import ColumnElement, Select, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.category import Category
from backend.apps.model.note import Note
from backend.apps.model.note_history import (
    CHANGE_SOURCE_MANUAL,
    CHANGE_TYPE_CREATE,
    CHANGE_TYPE_DELETE,
    CHANGE_TYPE_UPDATE,
)
from backend.apps.utils.exceptions import BusinessError, NotFoundError

logger = logging.getLogger(__name__)

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

    The weight literals must be the PostgreSQL internal ``"char"`` type —
    ``setweight(tsvector, "char")`` has no ``varchar`` overload, so passing a
    plain Python ``"A"`` renders as ``$n::VARCHAR`` and raises
    ``function setweight(tsvector, character varying) does not exist``.
    """
    seg_title = _segment(title)
    seg_content = _segment(content)
    # Weight 'A' for title, 'B' for content, cast to "char" literal.
    weight_a = literal_column("'A'::\"char\"")
    weight_b = literal_column("'B'::\"char\"")
    return func.setweight(
        func.to_tsvector(_TS_CONFIG, seg_title), weight_a
    ).op("||")(
        func.setweight(func.to_tsvector(_TS_CONFIG, seg_content), weight_b)
    )


async def list_notes(
    db: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    category_id: Optional[int] = None,
    keyword: Optional[str] = None,
    is_pinned: Optional[int] = None,
    tag: Optional[str] = None,
) -> dict:
    """
    List notes with pagination, optional category/tag filter and full-text search.
    Returns {items, total, page, page_size}.
    """
    logger.debug(
        "List notes: user_id=%s, page=%s, page_size=%s, category_id=%s, keyword=%r, is_pinned=%s, tag=%r",
        user_id, page, page_size, category_id, keyword, is_pinned, tag,
    )
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

    # Tag filter: JSONB containment (note_tags @> '["tag"]'). Uses the GIN
    # index ix_notes_note_tags.
    if tag and tag.strip():
        base_query = base_query.where(Note.note_tags.contains([tag.strip()]))

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

    logger.debug("List notes: user_id=%s, total=%s, returned=%d", user_id, total, len(notes))
    return {
        "items": [_note_to_dict(n) for n in notes],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def list_notes_tree(
    db: AsyncSession,
    user_id: int,
    keyword: Optional[str] = None,
    tag: Optional[str] = None,
) -> dict:
    """Return the user's categories and notes as a single combined tree.

    Categories are assembled into a tree (reusing ``category_service``); each
    category node carries a ``notes`` list of lightweight note dicts (no full
    ``note_content`` — only a short ``note_preview``). Notes whose
    ``category_id`` is missing/deleted land in ``uncategorized``.

    Optional ``keyword`` (jieba full-text) and ``tag`` (JSONB containment)
    filters restrict the notes returned; when either is active, categories
    that end up with no notes (and no note-bearing descendants) are pruned so
    the sidebar only shows relevant branches while searching.

    Returns ``{categories, uncategorized, total}``.
    """
    logger.debug("List notes tree: user_id=%s, keyword=%r, tag=%r", user_id, keyword, tag)
    # Import lazily to avoid a module-load cycle with the service package.
    from backend.apps.service import category_service

    roots, node_map = await category_service.build_category_tree(db, user_id)
    for node in node_map.values():
        node["notes"] = []

    query: Select = select(Note).where(
        Note.user_id == user_id,
        Note.is_deleted == 0,
    )

    # Tag filter: JSONB containment (note_tags @> '["tag"]').
    if tag and tag.strip():
        query = query.where(Note.note_tags.contains([tag.strip()]))

    # Chinese full-text search: segment the keyword the same way as the index.
    if keyword and keyword.strip():
        segmented = _segment(keyword.strip())
        if segmented:
            ts_query = func.plainto_tsquery(_TS_CONFIG, segmented)
            query = query.where(Note.search_vector.op("@@")(ts_query))

    query = query.order_by(Note.is_pinned.desc(), Note.updated_at.desc())
    result = await db.execute(query)
    notes = result.scalars().all()

    uncategorized: list[dict] = []
    for note in notes:
        item = _note_to_tree_dict(note)
        cid = note.category_id
        if cid is not None and cid in node_map:
            node_map[cid]["notes"].append(item)
        else:
            uncategorized.append(item)

    # While filtering, drop category branches that have nothing to show so the
    # tree stays focused. Without a filter we keep every category (even empty
    # ones) so users can still organize into them.
    filtering = bool((keyword and keyword.strip()) or (tag and tag.strip()))
    if filtering:
        roots = _prune_empty_categories(roots)

    logger.debug(
        "List notes tree: user_id=%s, total=%d, uncategorized=%d",
        user_id, len(notes), len(uncategorized),
    )
    return {
        "categories": roots,
        "uncategorized": uncategorized,
        "total": len(notes),
    }


async def get_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
) -> Optional[dict]:
    """Get a single note by ID. Returns None if not found or deleted."""
    logger.debug("Get note: note_id=%s, user_id=%s", note_id, user_id)
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
    *,
    change_source: int = CHANGE_SOURCE_MANUAL,
    remark: Optional[str] = None,
) -> Note:
    """Create a new note and populate its search_vector."""
    logger.debug("Create note: user_id=%s, title=%r, category_id=%s", user_id, note_title, category_id)
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
    await _record_history(db, note, CHANGE_TYPE_CREATE, change_source, remark)
    logger.info("Create note success: note_id=%s, title=%r, user_id=%s",
                note.note_id, note_title, user_id)
    return note


async def update_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
    fields: dict[str, Any],
    *,
    change_source: int = CHANGE_SOURCE_MANUAL,
    remark: Optional[str] = None,
) -> Note:
    """Update a note with only the provided fields.

    ``fields`` contains only keys the client actually sent (built via
    ``model_dump(exclude_unset=True)``), so omitting ``category_id`` leaves
    it unchanged instead of resetting it to NULL.

    Raises NotFoundError if the note does not exist.
    """
    logger.debug("Update note: note_id=%s, fields=%s, user_id=%s", note_id, list(fields.keys()), user_id)
    result = await db.execute(
        select(Note).where(
            Note.note_id == note_id,
            Note.user_id == user_id,
            Note.is_deleted == 0,
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        logger.warning("Update note failed: note_id=%s not found (user_id=%s)", note_id, user_id)
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
    await _record_history(db, note, CHANGE_TYPE_UPDATE, change_source, remark)
    logger.info("Update note success: note_id=%s, user_id=%s", note_id, user_id)
    return note


async def delete_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
    *,
    change_source: int = CHANGE_SOURCE_MANUAL,
    remark: Optional[str] = None,
) -> None:
    """Soft delete a note."""
    logger.debug("Delete note: note_id=%s, user_id=%s", note_id, user_id)
    result = await db.execute(
        select(Note).where(
            Note.note_id == note_id,
            Note.user_id == user_id,
            Note.is_deleted == 0,
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        logger.warning("Delete note failed: note_id=%s not found (user_id=%s)", note_id, user_id)
        raise NotFoundError("笔记不存在")

    # Snapshot the pre-delete state before flipping is_deleted. Soft delete only
    # changes is_deleted, so the snapshotted content fields equal the pre-delete
    # content — this is the row a user rolls back to in order to undo a delete.
    await _record_history(db, note, CHANGE_TYPE_DELETE, change_source, remark)
    note.is_deleted = 1
    await db.flush()
    logger.info("Delete note success: note_id=%s, user_id=%s", note_id, user_id)


async def move_notes(
    db: AsyncSession,
    user_id: int,
    note_ids: list[int],
    category_id: Optional[int],
) -> dict:
    """Move one or more notes to a target category.

    ``category_id=None`` moves them to "uncategorized". Validates that the
    target category exists (and is not deleted) and that every note exists
    and belongs to the user. Returns {moved, total, category_id}.
    """
    logger.debug("Move notes: note_ids=%s, category_id=%s, user_id=%s", note_ids, category_id, user_id)

    if not note_ids:
        raise BusinessError("笔记ID列表不能为空")

    # Validate target category (unless moving to uncategorized)
    if category_id is not None:
        cat_result = await db.execute(
            select(Category).where(
                Category.category_id == category_id,
                Category.user_id == user_id,
                Category.is_deleted == 0,
            )
        )
        if cat_result.scalar_one_or_none() is None:
            logger.warning("Move notes failed: target category_id=%s not found (user_id=%s)",
                           category_id, user_id)
            raise NotFoundError("目标分类不存在")

    # Fetch the notes to move
    result = await db.execute(
        select(Note).where(
            Note.note_id.in_(note_ids),
            Note.user_id == user_id,
            Note.is_deleted == 0,
        )
    )
    notes = result.scalars().all()

    found_ids = {n.note_id for n in notes}
    missing = set(note_ids) - found_ids
    if missing:
        logger.warning("Move notes failed: notes not found/not owned: %s (user_id=%s)",
                       sorted(missing), user_id)
        raise NotFoundError("部分笔记不存在或无权操作")

    moved = 0
    for note in notes:
        if note.category_id != category_id:
            note.category_id = category_id
            moved += 1

    await db.flush()
    logger.info("Move notes success: moved %d/%d to category_id=%s (user_id=%s)",
                moved, len(notes), category_id, user_id)
    return {"moved": moved, "total": len(notes), "category_id": category_id}


async def list_tags(
    db: AsyncSession,
    user_id: int,
) -> list[str]:
    """Return all distinct tags used across the user's non-deleted notes.

    Done in SQL (jsonb_array_elements_text + DISTINCT) so we don't pull every
    note's full tag array into Python.
    """
    logger.debug("List tags: user_id=%s", user_id)
    result = await db.execute(
        select(func.distinct(func.jsonb_array_elements_text(Note.note_tags))).where(
            Note.user_id == user_id,
            Note.is_deleted == 0,
            Note.note_tags.isnot(None),
        )
    )
    return sorted(row[0] for row in result.all())


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _record_history(
    db: AsyncSession,
    note: Note,
    change_type: int,
    change_source: int,
    remark: Optional[str],
) -> None:
    """Write a history snapshot for ``note``.

    Imports ``note_history_service`` lazily to avoid a module-load cycle
    (the same pattern used for ``category_service`` in ``list_notes_tree``).
    """
    from backend.apps.service import note_history_service

    await note_history_service.record_history(db, note, change_type, change_source, remark)


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


# Preview length for the combined tree's lightweight note items. Long enough
# to surface a useful snippet in the sidebar, short enough to keep the payload
# small (the full content is fetched separately via GET /note/{id}).
_PREVIEW_LIMIT = 160


def _preview(content: Optional[str]) -> Optional[str]:
    """Collapse whitespace and truncate note content for sidebar display."""
    if not content:
        return None
    text = " ".join(content.split())
    if len(text) <= _PREVIEW_LIMIT:
        return text
    return text[:_PREVIEW_LIMIT] + "…"


def _note_to_tree_dict(note: Note) -> dict:
    """Lightweight note dict for the combined tree (no full content)."""
    return {
        "note_id": note.note_id,
        "category_id": note.category_id,
        "note_title": note.note_title,
        "note_summary": note.note_summary,
        "note_preview": _preview(note.note_content),
        "note_tags": note.note_tags,
        "is_pinned": note.is_pinned,
        "note_word_count": note.note_word_count,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


def _prune_empty_categories(nodes: list[dict]) -> list[dict]:
    """Drop category nodes with no notes and no note-bearing descendants.

    Mutates each node's ``children`` in place and returns the kept nodes.
    Used only while a search/tag filter is active.
    """
    kept: list[dict] = []
    for node in nodes:
        node["children"] = _prune_empty_categories(node["children"])
        if node["children"] or node["notes"]:
            kept.append(node)
    return kept
