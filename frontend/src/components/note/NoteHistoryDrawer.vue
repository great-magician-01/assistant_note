<script setup lang="ts">
import { ref, watch } from 'vue'
import dayjs from 'dayjs'
import Modal from '@/components/Modal.vue'
import Icon from '@/components/Icon.vue'
import { useToast } from '@/composables/useToast'
import { listNoteHistories, getNoteHistory, rollbackNote } from '@/api/note'
import {
  NOTE_HISTORY_CHANGE_TYPE,
  NOTE_HISTORY_CHANGE_SOURCE,
  type NoteHistoryDetail,
  type NoteHistorySummary,
} from '@/types'

const props = defineProps<{
  visible: boolean
  noteId: string | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'rolled-back': []
}>()

const toast = useToast()

const histories = ref<NoteHistorySummary[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const selectedHistory = ref<NoteHistoryDetail | null>(null)
const detailLoading = ref(false)
const rollingBack = ref(false)

const CHANGE_TYPE_LABEL: Record<number, string> = {
  [NOTE_HISTORY_CHANGE_TYPE.CREATE]: '创建',
  [NOTE_HISTORY_CHANGE_TYPE.UPDATE]: '编辑',
  [NOTE_HISTORY_CHANGE_TYPE.DELETE]: '删除',
  [NOTE_HISTORY_CHANGE_TYPE.ROLLBACK]: '回滚',
}

const CHANGE_SOURCE_LABEL: Record<number, string> = {
  [NOTE_HISTORY_CHANGE_SOURCE.MANUAL]: '人为',
  [NOTE_HISTORY_CHANGE_SOURCE.AI]: 'AI',
}

function close() {
  emit('update:visible', false)
}

function formatTime(iso: string | null): string {
  if (!iso) return ''
  const d = dayjs(iso)
  return d.isValid() ? d.format('MM-DD HH:mm:ss') : ''
}

async function loadHistories() {
  if (!props.noteId) return
  loading.value = true
  try {
    const res = await listNoteHistories(props.noteId, { page: page.value, page_size: pageSize })
    histories.value = res.items
    total.value = res.total
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载历史失败')
  } finally {
    loading.value = false
  }
}

async function selectHistory(h: NoteHistorySummary) {
  if (!props.noteId) return
  detailLoading.value = true
  selectedHistory.value = null
  try {
    selectedHistory.value = await getNoteHistory(props.noteId, h.history_id)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载详情失败')
  } finally {
    detailLoading.value = false
  }
}

async function confirmRollback() {
  const detail = selectedHistory.value
  if (!detail || !props.noteId) return
  if (!window.confirm(`确定回滚到 ${formatTime(detail.created_at)} 的版本？当前内容将被覆盖（仍可在历史中找回）。`)) return
  rollingBack.value = true
  try {
    await rollbackNote(props.noteId, detail.history_id)
    toast.success('已回滚到选定版本')
    emit('rolled-back')
    close()
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '回滚失败')
  } finally {
    rollingBack.value = false
  }
}

const hasMore = () => total.value > histories.value.length

async function loadMore() {
  page.value += 1
  const prev = histories.value
  await loadHistories()
  histories.value = [...prev, ...histories.value]
}

// Reset + load whenever the drawer opens (or the note changes while open).
watch(
  () => [props.visible, props.noteId] as const,
  ([visible]) => {
    if (visible) {
      histories.value = []
      total.value = 0
      page.value = 1
      selectedHistory.value = null
      void loadHistories()
    }
  },
  { immediate: true },
)
</script>

<template>
  <Modal v-if="visible" title="历史记录" width="860px" @close="close">
    <div class="history-wrap">
      <!-- Left: list -->
      <div class="history-list">
        <div v-if="loading && !histories.length" class="history-empty">加载中…</div>
        <div v-else-if="!histories.length" class="history-empty">暂无历史记录</div>
        <ul v-else class="history-items">
          <li
            v-for="h in histories"
            :key="h.history_id"
            class="history-item"
            :class="{ active: selectedHistory?.history_id === h.history_id }"
            @click="selectHistory(h)"
          >
            <div class="hi-top">
              <span class="hi-badge" :class="`type-${h.change_type}`">{{ CHANGE_TYPE_LABEL[h.change_type] ?? '变更' }}</span>
              <span class="hi-source" :class="{ ai: h.change_source === NOTE_HISTORY_CHANGE_SOURCE.AI }">
                {{ CHANGE_SOURCE_LABEL[h.change_source] ?? '人为' }}
              </span>
            </div>
            <div class="hi-time">{{ formatTime(h.created_at) }}</div>
            <div v-if="h.remark" class="hi-remark">{{ h.remark }}</div>
            <div class="hi-words">{{ h.note_word_count }} 字</div>
          </li>
        </ul>
        <button v-if="hasMore()" class="load-more-btn" :disabled="loading" @click="loadMore">
          {{ loading ? '加载中…' : '加载更多' }}
        </button>
      </div>

      <!-- Right: detail preview -->
      <div class="history-detail">
        <div v-if="detailLoading" class="history-empty">加载中…</div>
        <div v-else-if="!selectedHistory" class="history-empty">
          <Icon name="clock" :size="36" />
          <p>选择左侧的一条记录查看完整内容</p>
        </div>
        <template v-else>
          <div class="detail-head">
            <h3 class="detail-title">{{ selectedHistory.note_title || '无标题' }}</h3>
            <span class="hi-badge" :class="`type-${selectedHistory.change_type}`">
              {{ CHANGE_TYPE_LABEL[selectedHistory.change_type] ?? '变更' }}
            </span>
          </div>
          <div class="detail-meta">
            <span>{{ formatTime(selectedHistory.created_at) }}</span>
            <span>{{ selectedHistory.note_word_count }} 字</span>
            <span v-if="selectedHistory.note_tags?.length" class="detail-tags">
              <span v-for="t in selectedHistory.note_tags" :key="t" class="tag-chip">{{ t }}</span>
            </span>
          </div>
          <pre class="detail-content">{{ selectedHistory.note_content || '（空笔记）' }}</pre>
          <div class="detail-footer">
            <button class="btn-primary" :disabled="rollingBack" @click="confirmRollback">
              {{ rollingBack ? '回滚中…' : '回滚到此版本' }}
            </button>
          </div>
        </template>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.history-wrap {
  display: flex;
  gap: 16px;
  min-height: 420px;
  max-height: 70vh;
}
.history-list {
  width: 280px;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow-y: auto;
  background: var(--bg-input);
}
.history-items {
  list-style: none;
  margin: 0;
  padding: 6px;
}
.history-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.history-item:hover {
  background: var(--bg-hover);
}
.history-item.active {
  background: var(--accent-light);
}
.hi-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.hi-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--bg-hover);
  color: var(--text-secondary);
}
.hi-badge.type-1 { color: #16a34a; background: rgba(22, 163, 74, 0.12); }
.hi-badge.type-2 { color: #2563eb; background: rgba(37, 99, 235, 0.12); }
.hi-badge.type-3 { color: #dc2626; background: rgba(220, 38, 38, 0.12); }
.hi-badge.type-4 { color: var(--accent); background: var(--accent-light); }
.hi-source {
  font-size: 11px;
  color: var(--text-tertiary);
}
.hi-source.ai {
  color: var(--accent);
  font-weight: 600;
}
.hi-time {
  font-size: 12px;
  color: var(--text-secondary);
}
.hi-remark {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hi-words {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}
.load-more-btn {
  display: block;
  width: calc(100% - 12px);
  margin: 6px;
  padding: 6px;
  font-size: 12px;
  color: var(--accent);
  background: transparent;
  border: 1px dashed var(--border);
  border-radius: 6px;
}
.load-more-btn:hover:not(:disabled) {
  background: var(--bg-hover);
}
.history-detail {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  background: var(--bg-input);
  overflow: hidden;
}
.history-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-tertiary);
  font-size: 13px;
  padding: 24px;
  text-align: center;
}
.history-empty svg {
  opacity: 0.4;
}
.detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}
.detail-title {
  flex: 1;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  word-break: break-word;
}
.detail-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 16px;
  font-size: 12px;
  color: var(--text-tertiary);
  flex-wrap: wrap;
}
.detail-tags {
  display: inline-flex;
  gap: 4px;
  flex-wrap: wrap;
}
.tag-chip {
  font-size: 11px;
  color: var(--text-accent);
  background: var(--accent-light);
  padding: 2px 8px;
  border-radius: 10px;
}
.detail-content {
  flex: 1;
  margin: 0;
  padding: 16px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-y: auto;
}
.detail-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
}
.btn-primary {
  padding: 7px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  background: var(--accent);
  color: #fff;
  transition: background 0.2s;
}
.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
}
.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
