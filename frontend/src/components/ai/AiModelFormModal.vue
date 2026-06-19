<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import Modal from '@/components/Modal.vue'
import { useToast } from '@/composables/useToast'
import { useAiStore } from '@/stores/ai'
import { extractErrorMessage } from '@/api/client'
import type { AiModel } from '@/types'

const props = defineProps<{
  visible: boolean
  /** Editing an existing model; omit for create. */
  model?: AiModel | null
}>()

const emit = defineEmits<{
  'update:visible': [v: boolean]
}>()

const aiStore = useAiStore()
const toast = useToast()

const API_FORMATS = ['openai', 'anthropic'] as const

const name = ref('')
const apiFormat = ref<(typeof API_FORMATS)[number]>('openai')
const baseUrl = ref('')
const apiKey = ref('')
const model = ref('')
const isMultimodal = ref(0)
const maxTokens = ref(4096)
const remark = ref('')
const extraConfigText = ref('')
const isActive = ref(1)
const submitting = ref(false)

const isEdit = computed(() => !!props.model)

const titleText = computed(() => (isEdit.value ? '编辑模型' : '新建模型'))

function reset() {
  name.value = ''
  apiFormat.value = 'openai'
  baseUrl.value = ''
  apiKey.value = ''
  model.value = ''
  isMultimodal.value = 0
  maxTokens.value = 4096
  remark.value = ''
  extraConfigText.value = ''
  isActive.value = 1
}

watch(
  () => props.visible,
  (v) => {
    if (!v) return
    if (props.model) {
      name.value = props.model.name
      apiFormat.value = (props.model.api_format as (typeof API_FORMATS)[number]) ?? 'openai'
      baseUrl.value = props.model.base_url
      apiKey.value = props.model.api_key
      model.value = props.model.model
      isMultimodal.value = props.model.is_multimodal
      maxTokens.value = props.model.max_tokens
      remark.value = props.model.remark ?? ''
      extraConfigText.value = props.model.extra_config
        ? JSON.stringify(props.model.extra_config, null, 2)
        : ''
      isActive.value = props.model.is_active
    } else {
      reset()
    }
  },
)

function buildExtraConfig(): Record<string, unknown> | null {
  const text = extraConfigText.value.trim()
  if (!text) return null
  try {
    const parsed = JSON.parse(text)
    if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) {
      throw new Error('extra_config 必须是 JSON 对象')
    }
    return parsed as Record<string, unknown>
  } catch (err) {
    throw new Error(err instanceof Error ? `extra_config 解析失败：${err.message}` : 'extra_config 解析失败')
  }
}

async function submit() {
  const trimmedName = name.value.trim()
  const trimmedModel = model.value.trim()
  const trimmedBase = baseUrl.value.trim()
  const trimmedKey = apiKey.value.trim()
  if (!trimmedName || !trimmedModel || !trimmedBase || !trimmedKey) {
    toast.error('请填写名称、模型标识、Base URL 与 API Key')
    return
  }
  if (maxTokens.value < 1) {
    toast.error('max_tokens 必须 ≥ 1')
    return
  }

  let extraConfig: Record<string, unknown> | null
  try {
    extraConfig = buildExtraConfig()
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'extra_config 解析失败')
    return
  }

  submitting.value = true
  try {
    const payload = {
      name: trimmedName,
      api_format: apiFormat.value,
      base_url: trimmedBase,
      api_key: trimmedKey,
      model: trimmedModel,
      is_multimodal: isMultimodal.value,
      max_tokens: maxTokens.value,
      remark: remark.value.trim() || null,
      extra_config: extraConfig,
      is_active: isActive.value,
    }
    if (props.model) {
      await aiStore.editModel(props.model.model_id, payload)
      toast.success('已更新模型')
    } else {
      await aiStore.addModel(payload)
      toast.success('已创建模型')
    }
    emit('update:visible', false)
  } catch (err) {
    toast.error(extractErrorMessage(err, '操作失败'))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Modal v-if="visible" :title="titleText" width="520px" @close="emit('update:visible', false)">
    <div class="form">
      <label class="field">
        <span class="label">名称 <span class="req">*</span></span>
        <input v-model="name" class="input" placeholder="如：DeepSeek 官方" maxlength="100" />
      </label>

      <div class="row">
        <label class="field">
          <span class="label">接口格式 <span class="req">*</span></span>
          <select v-model="apiFormat" class="input">
            <option v-for="f in API_FORMATS" :key="f" :value="f">{{ f }}</option>
          </select>
        </label>
        <label class="field">
          <span class="label">模型标识 <span class="req">*</span></span>
          <input v-model="model" class="input" placeholder="如：deepseek-chat" maxlength="100" />
        </label>
      </div>

      <label class="field">
        <span class="label">Base URL <span class="req">*</span></span>
        <input v-model="baseUrl" class="input" placeholder="https://api.example.com/v1" maxlength="500" />
      </label>

      <label class="field">
        <span class="label">API Key <span class="req">*</span></span>
        <input v-model="apiKey" type="password" class="input" placeholder="sk-..." maxlength="500" />
      </label>

      <div class="row">
        <label class="field">
          <span class="label">最大 Tokens</span>
          <input v-model.number="maxTokens" type="number" min="1" class="input" />
        </label>
        <label class="field">
          <span class="label">多模态</span>
          <select v-model.number="isMultimodal" class="input">
            <option :value="0">否</option>
            <option :value="1">是</option>
          </select>
        </label>
      </div>

      <label class="field">
        <span class="label">备注</span>
        <textarea v-model="remark" class="input textarea" rows="2" maxlength="500"></textarea>
      </label>

      <label class="field">
        <span class="label">额外配置 (JSON，可选)</span>
        <textarea
          v-model="extraConfigText"
          class="input textarea mono"
          rows="3"
          placeholder='{"thinking":{"type":"enabled"}}'
        ></textarea>
      </label>

      <label class="field-inline">
        <input v-model.number="isActive" type="checkbox" class="checkbox" :true-value="1" :false-value="0" />
        <span class="label inline">启用</span>
      </label>
    </div>

    <template #footer>
      <button class="btn btn-ghost" @click="emit('update:visible', false)">取消</button>
      <button class="btn btn-primary" :disabled="submitting" @click="submit">
        {{ isEdit ? '保存' : '创建' }}
      </button>
    </template>
  </Modal>
</template>

<style scoped>
.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.row {
  display: flex;
  gap: 12px;
}
.row .field {
  flex: 1;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-inline {
  display: flex;
  align-items: center;
  gap: 8px;
}
.label {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}
.label.inline {
  margin: 0;
}
.req {
  color: var(--danger);
}
.input {
  height: 36px;
  padding: 0 12px;
  font-size: 14px;
}
.textarea {
  height: auto;
  padding: 8px 12px;
  font-size: 13px;
  resize: vertical;
  line-height: 1.5;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.checkbox {
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
}
</style>
