"""Note history business logic: snapshot recording, listing, and rollback.

History rows are full *after-state* snapshots of a note, written on every
create/update/delete/rollback. They are append-only and survive note deletion,
so a soft-deleted note can still be revived by rolling back to one of its
snapshots.

This module is imported lazily by ``note_service`` (to avoid an import cycle),
so importing ``note_service`` at module top here is safe.
"""

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.model.note import Note
from backend.apps.model.note_history import (
    CHANGE_SOURCE_MANUAL,
    CHANGE_TYPE_ROLLBACK,
    NoteHistory,
)
from backend.apps.service import note_service
from backend.apps.utils.exceptions import NotFoundError

logger = logging.getLogger(__name__)


async def record_history(
    db: AsyncSession,
    note: Note,
    change_type: int,
    change_source: int = CHANGE_SOURCE_MANUAL,
    remark: Optional[str] = None,
) -> NoteHistory:
    """Record a full snapshot of ``note``'s current state as a history row.

    Called after the note has been mutated and flushed, so ``note.note_id`` and
    all content fields reflect the after-state. This is the single history-write
    chokepoint used by ``note_service`` and ``rollback_note``.
    """
    history = NoteHistory(
        note_id=note.note_id,
        user_id=note.user_id,
        category_id=note.category_id,
        note_title=note.note_title,
        note_content=note.note_content,
        note_summary=note.note_summary,
        note_tags=list(note.note_tags) if note.note_tags else [],
        note_word_count=note.note_word_count,
        is_pinned=note.is_pinned,
        change_type=change_type,
        change_source=change_source,
        remark=remark,
    )
    db.add(history)
    await db.flush()
    logger.debug(
        "Record history: note_id=%s, change_type=%s, change_source=%s, history_id=%s",
        note.note_id, change_type, change_source, history.history_id,
    )
    return history


async def list_histories(
    db: AsyncSession,
    user_id: int,
    note_id: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """List history snapshots for a note (metadata only — no full content).

    Queries ``note_histories`` directly by ``note_id + user_id`` and never
    touches the ``notes`` table, so history remains visible for soft-deleted
    notes (useful for picking a rollback target).

    Returns ``{items, total, page, page_size}``.
    """
    logger.debug("List histories: note_id=%s, user_id=%s, page=%s", note_id, user_id, page)
    base_query = select(NoteHistory).where(
        NoteHistory.note_id == note_id,
        NoteHistory.user_id == user_id,
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    rows_query = (
        base_query.order_by(NoteHistory.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(rows_query)).scalars().all()

    return {
        "items": [_history_to_summary(h) for h in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_history_detail(
    db: AsyncSession,
    user_id: int,
    note_id: int,
    history_id: int,
) -> Optional[dict]:
    """Return one history snapshot (full content) or None if not found."""
    logger.debug("Get history detail: history_id=%s, note_id=%s, user_id=%s",
                 history_id, note_id, user_id)
    row = (
        await db.execute(
            select(NoteHistory).where(
                NoteHistory.history_id == history_id,
                NoteHistory.note_id == note_id,
                NoteHistory.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return _history_to_detail(row)


async def rollback_note(
    db: AsyncSession,
    user_id: int,
    note_id: int,
    history_id: int,
    remark: Optional[str] = None,
) -> dict:
    """Restore a note to the state captured in a history snapshot.

    Revives soft-deleted notes (``is_deleted=0``) — the note fetch deliberately
    does *not* filter on ``is_deleted``. After restoring, a new ``ROLLBACK``
    history row is recorded (capturing the restored after-state), so the
    rollback itself is undoable by rolling back to the preceding row.
    """
    logger.debug("Rollback note: note_id=%s, history_id=%s, user_id=%s",
                 note_id, history_id, user_id)

    # Fetch the note without the is_deleted==0 guard so deleted notes can be
    # revived.
    note = (
        await db.execute(
            select(Note).where(
                Note.note_id == note_id,
                Note.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if note is None:
        logger.warning("Rollback failed: note_id=%s not found (user_id=%s)", note_id, user_id)
        raise NotFoundError("笔记不存在")

    history = (
        await db.execute(
            select(NoteHistory).where(
                NoteHistory.history_id == history_id,
                NoteHistory.note_id == note_id,
                NoteHistory.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if history is None:
        logger.warning("Rollback failed: history_id=%s not found (note_id=%s)",
                       history_id, note_id)
        raise NotFoundError("历史记录不存在")

    # Restore the snapshot's content fields onto the note and revive it.
    note.category_id = history.category_id
    note.note_title = history.note_title
    note.note_content = history.note_content
    note.note_summary = history.note_summary
    note.note_tags = list(history.note_tags) if history.note_tags else []
    note.note_word_count = history.note_word_count
    note.is_pinned = history.is_pinned
    note.is_deleted = 0
    # search_vector is derived — recompute from the restored title/content.
    note.search_vector = note_service._build_search_vector(note.note_title, note.note_content)

    await db.flush()
    logger.info("Rollback note success: note_id=%s -> history_id=%s (user_id=%s)",
                note_id, history_id, user_id)

    # Record the rollback itself so it can be undone.
    await record_history(
        db, note, CHANGE_TYPE_ROLLBACK, CHANGE_SOURCE_MANUAL, remark
    )

    return note_service._note_to_dict(note)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _history_to_summary(h: NoteHistory) -> dict:
    """Lightweight dict for list views (no full content)."""
    return {
        "history_id": h.history_id,
        "note_id": h.note_id,
        "change_type": h.change_type,
        "change_source": h.change_source,
        "note_word_count": h.note_word_count,
        "remark": h.remark,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }


def _history_to_detail(h: NoteHistory) -> dict:
    """Full snapshot dict (includes content)."""
    return {
        "history_id": h.history_id,
        "note_id": h.note_id,
        "change_type": h.change_type,
        "change_source": h.change_source,
        "remark": h.remark,
        "category_id": h.category_id,
        "note_title": h.note_title,
        "note_content": h.note_content,
        "note_summary": h.note_summary,
        "note_tags": h.note_tags,
        "note_word_count": h.note_word_count,
        "is_pinned": h.is_pinned,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }
