import { apiGet, apiPost } from './client'
import type { AiConfig, AiModel, ChatMessage, SnowflakeId } from '@/types'

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

export function createAiModel(body: AiModelCreatePayload) {
  return apiPost<AiModel>('/v1/ai-model', body)
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
  json_output?: number
  temperature?: number | null
  top_p?: number | null
  max_tokens?: number | null
  is_default?: number
  is_active?: number
}

export function createAiConfig(body: AiConfigCreatePayload) {
  return apiPost<AiConfig>('/v1/ai-config', body)
}

export function deleteAiConfig(id: SnowflakeId) {
  return apiPost<{ message: string }>(`/v1/ai-config/${id}/delete`)
}

/* ── Inference ──
 * NOTE: The backend exposes model-pool/config CRUD but no chat-completion
 * endpoint yet. We attempt POST /v1/ai/chat and gracefully surface that the
 * inference service is unavailable.
 */
export function chatWithAi(messages: ChatMessage[], configId?: SnowflakeId) {
  return apiPost<{ reply: string }>('/v1/ai/chat', { messages, config_id: configId ?? null })
}
