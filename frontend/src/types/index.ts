/**
 * Shared frontend types — mirror the backend Pydantic response models.
 *
 * All `*_id` fields are JSON strings because Snowflake IDs (64-bit) exceed
 * JS Number.MAX_SAFE_INTEGER (2^53). Keep them as strings end-to-end and
 * only coerce to int at the path-param boundary (the backend accepts str
 * path params and converts them).
 */

export type SnowflakeId = string

export interface UserInfo {
  user_id: SnowflakeId
  user_account: string
  user_name: string
  is_active: number
  role_id: SnowflakeId
  role_code: string | null
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  user_id: SnowflakeId
  user_name: string
  user_account: string | null
}

export interface CategoryNode {
  category_id: SnowflakeId
  user_id: SnowflakeId
  category_name: string
  category_icon: string | null
  category_sort: number
  parent_id: SnowflakeId | null
  children: CategoryNode[]
  created_at?: string | null
  updated_at?: string | null
}

export interface Note {
  note_id: SnowflakeId
  user_id: SnowflakeId
  category_id: SnowflakeId | null
  note_title: string
  note_content: string | null
  note_summary: string | null
  note_tags: string[] | null
  is_pinned: number
  note_word_count: number
  created_at?: string | null
  updated_at?: string | null
}

export interface NoteListResponse {
  items: Note[]
  total: number
  page: number
  page_size: number
}

export interface NoteListParams {
  page?: number
  page_size?: number
  category_id?: number | null
  keyword?: string | null
  is_pinned?: number | null
  tag?: string | null
}

/** Lightweight note item nested inside the combined category/note tree.
 *  Mirrors backend NoteTreeItem — no full content, just a short preview. */
export interface NoteTreeItem {
  note_id: SnowflakeId
  category_id: SnowflakeId | null
  note_title: string
  note_summary: string | null
  note_preview: string | null
  note_tags: string[] | null
  is_pinned: number
  note_word_count: number
  created_at?: string | null
  updated_at?: string | null
}

/** Category node in the combined tree — carries sub-categories AND notes. */
export interface CategoryTreeNode {
  category_id: SnowflakeId
  user_id: SnowflakeId
  category_name: string
  category_icon: string | null
  category_sort: number
  parent_id: SnowflakeId | null
  children: CategoryTreeNode[]
  notes: NoteTreeItem[]
  created_at?: string | null
  updated_at?: string | null
}

export interface NoteTreeResponse {
  categories: CategoryTreeNode[]
  uncategorized: NoteTreeItem[]
  total: number
}

export interface NoteTreeParams {
  keyword?: string | null
  tag?: string | null
}

export interface MoveNotesResult {
  moved: number
  total: number
  category_id: SnowflakeId | null
}

/** Change type stored on a history row (mirrors backend constants). */
export const NOTE_HISTORY_CHANGE_TYPE = {
  CREATE: 1,
  UPDATE: 2,
  DELETE: 3,
  ROLLBACK: 4,
} as const

/** Change source stored on a history row (mirrors backend constants). */
export const NOTE_HISTORY_CHANGE_SOURCE = {
  MANUAL: 1,
  AI: 2,
} as const

/** Lightweight history item for list views (no full content). */
export interface NoteHistorySummary {
  history_id: SnowflakeId
  note_id: SnowflakeId
  change_type: number
  change_source: number
  note_word_count: number
  remark: string | null
  created_at: string | null
}

export interface NoteHistoryListResponse {
  items: NoteHistorySummary[]
  total: number
  page: number
  page_size: number
}

/** A single history snapshot with full content. */
export interface NoteHistoryDetail {
  history_id: SnowflakeId
  note_id: SnowflakeId
  change_type: number
  change_source: number
  remark: string | null
  category_id: SnowflakeId | null
  note_title: string
  note_content: string | null
  note_summary: string | null
  note_tags: string[] | null
  note_word_count: number
  is_pinned: number
  created_at: string | null
}

/** Backend error envelope (BusinessError/NotFoundError/ForbiddenError → JSONResponse).
 *  The body is `{ detail: string }`; the trace id travels in the `X-Trace-Id` response header, not the body. */
export interface ApiErrorBody {
  detail: string
}

/** AI model pool entry (mirrors AiModelResponse). */
export interface AiModel {
  model_id: SnowflakeId
  name: string
  api_format: string
  base_url: string
  api_key: string
  model: string
  is_multimodal: number
  max_tokens: number
  remark: string | null
  extra_config: Record<string, unknown> | null
  is_active: number
  created_at?: string | null
  updated_at?: string | null
}

/** AI runtime config (mirrors AiConfigResponse, enriched with model info). */
export interface AiConfig {
  config_id: SnowflakeId
  config_name: string
  model_id: SnowflakeId
  model_name: string | null
  model: string | null
  api_format: string | null
  system_prompt: string | null
  tools: string[] | null
  json_output: number
  temperature: number | null
  top_p: number | null
  max_tokens: number | null
  is_default: number
  is_active: number
  created_at?: string | null
  updated_at?: string | null
}

export interface ChatMessage {
  role: 'user' | 'ai'
  content: string
}

/** A persisted chat session (mirrors ChatSessionResponse). */
export interface ChatSession {
  session_id: SnowflakeId
  user_id: SnowflakeId
  config_id: SnowflakeId
  model_id: SnowflakeId
  api_format: string
  session_title: string
  /** Bound note id (set when the session was started from the note editor's AI drawer). */
  note_id: SnowflakeId | null
  created_at?: string | null
  updated_at?: string | null
}

/** A persisted chat message row (mirrors ChatMessageResponse). */
export interface ChatMessageRow {
  message_id: SnowflakeId
  session_id: SnowflakeId
  role: 'user' | 'assistant' | 'tool'
  content: string | null
  tool_calls: { id: string; name: string; arguments: Record<string, unknown> }[] | null
  tool_call_id: string | null
  tool_name: string | null
  is_error: number
  prompt_tokens: number | null
  completion_tokens: number | null
  iter_index: number
  created_at?: string | null
}

/** Body for the streaming chat endpoint. */
export interface StreamChatBody {
  session_id?: SnowflakeId | null
  message: string
  config_id?: SnowflakeId | null
  /** Bind a new session to this note (note editor's AI drawer). Ignored if session_id is set. */
  note_id?: SnowflakeId | null
}

/** Handlers for the SSE chat stream. */
export interface StreamChatHandlers {
  onSession: (data: { session_id: SnowflakeId; session_title: string }) => void
  onText: (delta: string) => void
  onToolStart: (data: { id: string; name: string }) => void
  onToolEnd: (data: { id: string; name: string; result: string; is_error: boolean }) => void
  onDone: (data: { session_id: SnowflakeId; session_title: string }) => void
  onError: (message: string) => void
}

/** AI tool registry entry (mirrors ToolResponse from GET /v1/ai-tool). */
export interface AiTool {
  name: string
  description: string
  parameters: Record<string, unknown>
}
