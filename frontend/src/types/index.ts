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
  tools: unknown[] | null
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
