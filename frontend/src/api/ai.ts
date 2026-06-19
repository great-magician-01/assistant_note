import { apiGet, apiPost, tokenStorage } from './client'
import type {
  AiConfig,
  AiModel,
  AiTool,
  ChatMessageRow,
  ChatSession,
  SnowflakeId,
  StreamChatBody,
  StreamChatHandlers,
} from '@/types'

/* ── Model pool CRUD (/v1/ai-model) ── */
export function listAiModels() {
  return apiGet<AiModel[]>('/v1/ai-model')
}

export interface AiModelCreatePayload {
  name: string
  api_format: string
  base_url: string
  api_key: string
  model: string
  is_multimodal?: number
  max_tokens?: number
  remark?: string | null
  extra_config?: Record<string, unknown> | null
  is_active?: number
}

/** Update payload — all fields optional (backend uses exclude_unset). */
export type AiModelUpdatePayload = Partial<AiModelCreatePayload>

export function createAiModel(body: AiModelCreatePayload) {
  return apiPost<AiModel>('/v1/ai-model', body)
}

export function updateAiModel(id: SnowflakeId, body: AiModelUpdatePayload) {
  return apiPost<AiModel>(`/v1/ai-model/${id}/update`, body)
}

export function deleteAiModel(id: SnowflakeId) {
  return apiPost<{ message: string }>(`/v1/ai-model/${id}/delete`)
}

/* ── Runtime config CRUD (/v1/ai-config) ── */
export function listAiConfigs() {
  return apiGet<AiConfig[]>('/v1/ai-config')
}

export interface AiConfigCreatePayload {
  config_name: string
  model_id: SnowflakeId
  system_prompt?: string | null
  tools?: string[] | null
  json_output?: number
  temperature?: number | null
  top_p?: number | null
  max_tokens?: number | null
  is_default?: number
  is_active?: number
}

/** Update payload — all fields optional (backend uses exclude_unset). */
export type AiConfigUpdatePayload = Partial<AiConfigCreatePayload>

export function createAiConfig(body: AiConfigCreatePayload) {
  return apiPost<AiConfig>('/v1/ai-config', body)
}

export function updateAiConfig(id: SnowflakeId, body: AiConfigUpdatePayload) {
  return apiPost<AiConfig>(`/v1/ai-config/${id}/update`, body)
}

export function deleteAiConfig(id: SnowflakeId) {
  return apiPost<{ message: string }>(`/v1/ai-config/${id}/delete`)
}

/* ── Tool registry (/v1/ai-tool, admin only) ── */
export function listAiTools() {
  return apiGet<AiTool[]>('/v1/ai-tool')
}

/* ── Inference (SSE streaming) + session management ── */

/**
 * Stream a chat turn over SSE. Uses the native fetch (not axios, which doesn't
 * stream well) with the access token from localStorage. Parses the
 * `event: <type>\ndata: <json>\n\n` framing manually and dispatches to handlers.
 *
 * Resolves when the stream ends (`done`) or rejects on a network error. A
 * non-2xx HTTP response is surfaced via `onError` (with the server's error
 * message when available) and the promise resolves.
 */
export async function streamChat(body: StreamChatBody, handlers: StreamChatHandlers): Promise<void> {
  const token = tokenStorage.getAccess()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  let resp: Response
  try {
    resp = await fetch('/api/v1/ai/chat', {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })
  } catch (err) {
    handlers.onError(err instanceof Error ? err.message : '网络错误')
    return
  }

  if (!resp.ok || !resp.body) {
    // Server returns a normal JSON error (400/404) before streaming.
    let message = `请求失败 (${resp.status})`
    try {
      const data = await resp.json()
      if (typeof data?.detail === 'string') message = data.detail
    } catch {
      /* ignore parse error */
    }
    handlers.onError(message)
    return
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE frames are separated by a blank line.
      let sep: number
      while ((sep = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        parseFrame(frame, handlers)
      }
    }
    // Flush any trailing frame.
    if (buffer.trim()) parseFrame(buffer, handlers)
  } catch (err) {
    handlers.onError(err instanceof Error ? err.message : '读取流失败')
  }
}

function parseFrame(frame: string, handlers: StreamChatHandlers): void {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return
  let data: Record<string, unknown>
  try {
    data = JSON.parse(dataLines.join('\n'))
  } catch {
    return
  }
  switch (event) {
    case 'session':
      handlers.onSession(data as { session_id: SnowflakeId; session_title: string })
      break
    case 'text':
      handlers.onText(String(data.delta ?? ''))
      break
    case 'tool_start':
      handlers.onToolStart(data as { id: string; name: string })
      break
    case 'tool_end':
      handlers.onToolEnd({
        id: String(data.id ?? ''),
        name: String(data.name ?? ''),
        result: String(data.result ?? ''),
        is_error: Boolean(data.is_error),
      })
      break
    case 'done':
      handlers.onDone(data as { session_id: SnowflakeId; session_title: string })
      break
    case 'error':
      handlers.onError(String(data.message ?? '对话出错'))
      break
  }
}

export function listChatSessions(noteId?: SnowflakeId) {
  const query = noteId ? `?note_id=${encodeURIComponent(noteId)}` : ''
  return apiGet<ChatSession[]>(`/v1/ai/chat/sessions${query}`)
}

export function getChatMessages(sessionId: SnowflakeId) {
  return apiGet<ChatMessageRow[]>(`/v1/ai/chat/sessions/${sessionId}/messages`)
}

export function renameChatSession(id: SnowflakeId, title: string) {
  return apiPost<ChatSession>(`/v1/ai/chat/sessions/${id}/update`, { session_title: title })
}

export function deleteChatSession(id: SnowflakeId) {
  return apiPost<{ message: string }>(`/v1/ai/chat/sessions/${id}/delete`)
}
