<script setup lang="ts">
import { ref, watch } from 'vue'
import Modal from '@/components/Modal.vue'
import { useToast } from '@/composables/useToast'
import { useCategoryStore } from '@/stores/category'
import type { CategoryNode, SnowflakeId } from '@/types'

const props = defineProps<{
  visible: boolean
  /** Editing an existing node; omit for create. */
  node?: CategoryNode | null
  /** Parent when creating a sub-category. */
  parent?: CategoryNode | null
}>()

const emit = defineEmits<{
  'update:visible': [v: boolean]
  saved: []
}>()

const categoryStore = useCategoryStore()
const toast = useToast()

const name = ref('')
const icon = ref('folder')
const submitting = ref(false)

const isEdit = () => !!props.node

const titleText = () => {
  if (props.node) return '重命名分类'
  if (props.parent) return `在「${props.parent.category_name}」下新建子分类`
  return '新建分类'
}

watch(
  () => props.visible,
  (v) => {
    if (!v) return
    name.value = props.node?.category_name ?? ''
    icon.value = props.node?.category_icon || 'folder'
  },
)

const ICON_OPTIONS = [
  'folder',
  'file-text',
  'book',
  'book-open',
  'code',
  'calendar',
  'tag',
  'inbox',
]

async function submit() {
  const trimmed = name.value.trim()
  if (!trimmed) {
    toast.error('请输入分类名称')
    return
  }
  submitting.value = true
  try {
    if (props.node) {
      await categoryStore.safeUpdate(props.node.category_id, {
        category_name: trimmed,
        category_icon: icon.value,
      })
      toast.success('已更新')
    } else {
      const parentId: SnowflakeId | null = props.parent?.category_id ?? null
      await categoryStore.safeCreate({
        category_name: trimmed,
        category_icon: icon.value,
        parent_id: parentId,
      })
      toast.success('已创建')
    }
    emit('saved')
    emit('update:visible', false)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '操作失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Modal
    v-if="visible"
    :title="titleText()"
    width="380px"
    @close="emit('update:visible', false)"
  >
    <div class="form">
      <label class="field">
        <span class="label">名称</span>
        <input
          v-model="name"
          class="input"
          placeholder="分类名称"
          maxlength="100"
          @keydown.enter="submit"
        />
      </label>
      <label class="field">
        <span class="label">图标</span>
        <div class="icon-picker">
          <button
            v-for="opt in ICON_OPTIONS"
            :key="opt"
            type="button"
            class="icon-opt"
            :class="{ active: icon === opt }"
            @click="icon = opt"
          >
            {{ opt }}
          </button>
        </div>
      </label>
    </div>
    <template #footer>
      <button class="btn btn-ghost" @click="emit('update:visible', false)">取消</button>
      <button class="btn btn-primary" :disabled="submitting" @click="submit">
        {{ isEdit() ? '保存' : '创建' }}
      </button>
    </template>
  </Modal>
</template>

<style scoped>
.form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.label {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}
.input {
  height: 36px;
  padding: 0 12px;
  font-size: 14px;
}
.icon-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.icon-opt {
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-input);
  color: var(--text-secondary);
  transition: all 0.15s;
}
.icon-opt:hover {
  background: var(--bg-hover);
}
.icon-opt.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
</style>
