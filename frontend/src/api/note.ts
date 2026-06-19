import { apiGet, apiPost } from './client'
import type {
  Note,
  NoteHistoryDetail,
  NoteHistoryListResponse,
  NoteTreeParams,
  NoteTreeResponse,
  SnowflakeId,
  MoveNotesResult,
} from '@/types'

export function listNoteTree(params: NoteTreeParams = {}) {
  return apiGet<NoteTreeResponse>('/v1/note/tree', { params })
}

export function listTags() {
  return apiGet<string[]>('/v1/note/tags')
}

export function getNote(id: SnowflakeId) {
  return apiGet<Note>(`/v1/note/${id}`)
}

export interface NoteCreatePayload {
  note_title: string
  note_content?: string | null
  category_id?: SnowflakeId | null
  note_tags?: string[] | null
  is_pinned?: number
}

export interface NoteUpdatePayload {
  note_title?: string
  note_content?: string | null
  category_id?: SnowflakeId | null
  note_summary?: string | null
  note_tags?: string[] | null
  is_pinned?: number
}

export function createNote(body: NoteCreatePayload) {
  return apiPost<Note>('/v1/note', body)
}

export function updateNote(id: SnowflakeId, body: NoteUpdatePayload) {
  return apiPost<Note>(`/v1/note/${id}/update`, body)
}

export function deleteNote(id: SnowflakeId) {
  return apiPost<{ message: string }>(`/v1/note/${id}/delete`)
}

export function moveNotes(note_ids: SnowflakeId[], category_id: SnowflakeId | null) {
  return apiPost<MoveNotesResult>('/v1/note/move', { note_ids, category_id })
}

// ── Note history ─────────────────────────────────────────────────────────────

export interface NoteHistoryListParams {
  page?: number
  page_size?: number
}

export function listNoteHistories(noteId: SnowflakeId, params: NoteHistoryListParams = {}) {
  return apiGet<NoteHistoryListResponse>(`/v1/note/${noteId}/histories`, { params })
}

export function getNoteHistory(noteId: SnowflakeId, historyId: SnowflakeId) {
  return apiGet<NoteHistoryDetail>(`/v1/note/${noteId}/histories/${historyId}`)
}

export function rollbackNote(noteId: SnowflakeId, historyId: SnowflakeId, remark?: string | null) {
  return apiPost<Note>(`/v1/note/${noteId}/rollback`, { history_id: historyId, remark: remark ?? null })
}
