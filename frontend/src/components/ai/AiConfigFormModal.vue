<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import Modal from '@/components/Modal.vue'
import { useToast } from '@/composables/useToast'
import { useAiStore } from '@/stores/ai'
import { extractErrorMessage } from '@/api/client'
import type { AiConfig, SnowflakeId } from '@/types'

const props = defineProps<{
  visible: boolean
  /** Editing an existing config; omit for create. */
  config?: AiConfig | null
}>()

const emit = defineEmits<{
  'update:visible': [v: boolean]
}>()

const aiStore = useAiStore()
const toast = useToast()

const configName = ref('')
const modelId = ref<SnowflakeId | ''>('')
const systemPrompt = ref('')
const selectedTools = ref<string[]>([])
const jsonOutput = ref(0)
const temperature = ref<number | null>(null)
const topP = ref<number | null>(null)
const maxTokens = ref<number | null>(null)
const isDefault = ref(0)
const isActive = ref(1)
const submitting = ref(false)

const isEdit = computed(() => !!props.config)
const titleText = computed(() => (isEdit.value ? '编辑配置' : '新建配置'))

// Available models — only active ones are pickable, but include the config's
// current model even if it was deactivated so edits don't silently drop it.
const availableModels = computed(() => {
  const list = aiStore.models.filter((m) => m.is_active === 1)
  if (props.config) {
    const current = aiStore.models.find((m) => m.model_id === props.config!.model_id)
    if (current && !list.includes(current)) list.push(current)
  }
  return list
})

const availableTools = computed(() => aiStore.tools)

watch(
  () => props.visible,
  (v) => {
    if (!v) return
    if (props.config) {
      configName.value = props.config.config_name
      modelId.value = props.config.model_id
      systemPrompt.value = props.config.system_prompt ?? ''
      selectedTools.value = (props.config.tools ?? []) as string[]
      jsonOutput.value = props.config.json_output
      temperature.value = props.config.temperature
      topP.value = props.config.top_p
      maxTokens.value = props.config.max_tokens
      isDefault.value = props.config.is_default
      isActive.value = props.config.is_active
    } else {
      configName.value = ''
      modelId.value = availableModels.value[0]?.model_id ?? ''
      systemPrompt.value = ''
      selectedTools.value = []
      jsonOutput.value = 0
      temperature.value = null
      topP.value = null
      maxTokens.value = null
      isDefault.value = 0
      isActive.value = 1
    }
  },
)

function toggleTool(name: string) {
  const i = selectedTools.value.indexOf(name)
  if (i >= 0) selectedTools.value.splice(i, 1)
  else selectedTools.value.push(name)
}

function clampNumber(v: number | null, min: number, max: number): number | null {
  if (v === null || Number.isNaN(v)) return null
  return Math.min(max, Math.max(min, v))
}

async function submit() {
  const trimmedName = configName.value.trim()
  if (!trimmedName) {
    toast.error('请输入配置名称')
    return
  }
  if (!modelId.value) {
    toast.error('请选择模型')
    return
  }
  const temp = clampNumber(temperature.value, 0, 2)
  const tp = clampNumber(topP.value, 0, 1)
  const mt = maxTokens.value === null || maxTokens.value === 0 ? null : maxTokens.value
  if (mt !== null && mt < 1) {
    toast.error('max_tokens 必须 ≥ 1')
    return
  }

  submitting.value = true
  try {
    const payload = {
      config_name: trimmedName,
      model_id: modelId.value as SnowflakeId,
      system_prompt: systemPrompt.value.trim() || null,
      tools: selectedTools.value,
      json_output: jsonOutput.value,
      temperature: temp,
      top_p: tp,
      max_tokens: mt,
      is_default: isDefault.value,
      is_active: isActive.value,
    }
    if (props.config) {
      await aiStore.editConfig(props.config.config_id, payload)
      toast.success('已更新配置')
    } else {
      await aiStore.addConfig(payload)
      toast.success('已创建配置')
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
  <Modal v-if="visible" :title="titleText" width="560px" @close="emit('update:visible', false)">
    <div class="form">
      <div class="row">
        <label class="field">
          <span class="label">配置名称 <span class="req">*</span></span>
          <input v-model="configName" class="input" placeholder="如：默认对话" maxlength="100" />
        </label>
        <label class="field">
          <span class="label">模型 <span class="req">*</span></span>
          <select v-model="modelId" class="input">
            <option value="" disabled>选择模型</option>
            <option v-for="m in availableModels" :key="m.model_id" :value="m.model_id">
              {{ m.name }} ({{ m.model }})
            </option>
          </select>
        </label>
      </div>

      <label class="field">
        <span class="label">系统提示词</span>
        <textarea v-model="systemPrompt" class="input textarea" rows="3" placeholder="你是一个笔记助手…"></textarea>
      </label>

      <div class="field">
        <span class="label">工具</span>
        <div v-if="availableTools.length" class="tool-grid">
          <label
            v-for="t in availableTools"
            :key="t.name"
            class="tool-opt"
            :class="{ active: selectedTools.includes(t.name) }"
            :title="t.description"
          >
            <input
              type="checkbox"
              class="checkbox"
              :checked="selectedTools.includes(t.name)"
              @change="toggleTool(t.name)"
            />
            <span class="tool-name">{{ t.name }}</span>
          </label>
        </div>
        <div v-else class="hint">暂无可用工具</div>
      </div>

      <div class="row">
        <label class="field">
          <span class="label">Temperature (0-2)</span>
          <input v-model.number="temperature" type="number" min="0" max="2" step="0.1" class="input" placeholder="默认" />
        </label>
        <label class="field">
          <span class="label">Top P (0-1)</span>
          <input v-model.number="topP" type="number" min="0" max="1" step="0.05" class="input" placeholder="默认" />
        </label>
        <label class="field">
          <span class="label">Max Tokens</span>
          <input v-model.number="maxTokens" type="number" min="1" class="input" placeholder="跟随模型" />
        </label>
      </div>

      <div class="toggles">
        <label class="field-inline">
          <input v-model.number="jsonOutput" type="checkbox" class="checkbox" :true-value="1" :false-value="0" />
          <span class="label inline">JSON 输出</span>
        </label>
        <label class="field-inline">
          <input v-model.number="isDefault" type="checkbox" class="checkbox" :true-value="1" :false-value="0" />
          <span class="label inline">设为默认</span>
        </label>
        <label class="field-inline">
          <input v-model.number="isActive" type="checkbox" class="checkbox" :true-value="1" :false-value="0" />
          <span class="label inline">启用</span>
        </label>
      </div>
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
.hint {
  font-size: 12px;
  color: var(--text-tertiary);
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
.tool-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.tool-opt {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-input);
  cursor: pointer;
  transition: all 0.15s;
}
.tool-opt:hover {
  background: var(--bg-hover);
}
.tool-opt.active {
  background: var(--accent);
  border-color: var(--accent);
}
.tool-opt.active .tool-name {
  color: #fff;
}
.tool-name {
  font-size: 12px;
  color: var(--text-secondary);
}
.checkbox {
  width: 15px;
  height: 15px;
  accent-color: var(--accent);
}
.toggles {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}
</style>
