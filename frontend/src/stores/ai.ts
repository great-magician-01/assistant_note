import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  listAiModels,
  listAiConfigs,
  listAiTools,
  createAiModel,
  updateAiModel,
  deleteAiModel,
  createAiConfig,
  updateAiConfig,
  deleteAiConfig,
  type AiModelCreatePayload,
  type AiModelUpdatePayload,
  type AiConfigCreatePayload,
  type AiConfigUpdatePayload,
} from '@/api/ai'
import type { AiConfig, AiModel, AiTool, SnowflakeId } from '@/types'

/**
 * Admin-facing AI management store — holds the model pool, runtime configs,
 * and tool registry. All write operations (create/update/delete) are admin-only
 * on the backend; this store assumes the caller has already gated by role.
 */
export const useAiStore = defineStore('ai', () => {
  const models = ref<AiModel[]>([])
  const configs = ref<AiConfig[]>([])
  const tools = ref<AiTool[]>([])

  const modelsLoading = ref(false)
  const configsLoading = ref(false)
  const toolsLoading = ref(false)

  async function fetchModels() {
    modelsLoading.value = true
    try {
      models.value = await listAiModels()
    } finally {
      modelsLoading.value = false
    }
  }

  async function fetchConfigs() {
    configsLoading.value = true
    try {
      configs.value = await listAiConfigs()
    } finally {
      configsLoading.value = false
    }
  }

  async function fetchTools() {
    toolsLoading.value = true
    try {
      tools.value = await listAiTools()
    } finally {
      toolsLoading.value = false
    }
  }

  /** Load everything the settings page needs. */
  async function fetchAll() {
    await Promise.all([fetchModels(), fetchConfigs(), fetchTools()])
  }

  async function addModel(body: AiModelCreatePayload) {
    await createAiModel(body)
    await fetchModels()
  }

  async function editModel(id: SnowflakeId, body: AiModelUpdatePayload) {
    await updateAiModel(id, body)
    await fetchModels()
    // Config list carries denormalized model fields — refresh so names update.
    await fetchConfigs()
  }

  async function removeModel(id: SnowflakeId) {
    await deleteAiModel(id)
    await fetchModels()
  }

  async function addConfig(body: AiConfigCreatePayload) {
    await createAiConfig(body)
    await fetchConfigs()
  }

  async function editConfig(id: SnowflakeId, body: AiConfigUpdatePayload) {
    await updateAiConfig(id, body)
    await fetchConfigs()
  }

  async function removeConfig(id: SnowflakeId) {
    await deleteAiConfig(id)
    await fetchConfigs()
  }

  return {
    models,
    configs,
    tools,
    modelsLoading,
    configsLoading,
    toolsLoading,
    fetchModels,
    fetchConfigs,
    fetchTools,
    fetchAll,
    addModel,
    editModel,
    removeModel,
    addConfig,
    editConfig,
    removeConfig,
  }
})
