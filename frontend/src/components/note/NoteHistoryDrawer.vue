<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import dayjs from 'dayjs'
import Modal from '@/components/Modal.vue'
import Icon from '@/components/Icon.vue'
import { useToast } from '@/composables/useToast'
import { listNoteHistories, getNoteHistory, rollbackNote } from '@/api/note'
import { computeDiff } from '@/utils/diff'
import {
  NOTE_HISTORY_CHANGE_TYPE,
  NOTE_HISTORY_CHANGE_SOURCE,
  type NoteHistoryDetail,
  type NoteHistorySummary,
} from '@/types'

const props = defineProps<{
  visible: boolean
  noteId: string | null
  currentContent?: string | null
  currentTitle?: string | null
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

// ── Diff mode ─────────────────────────────────────────────────────────────────
const mode = ref<'preview' | 'diff'>('preview')
const diffVersionA = ref<string>('current')
const diffVersionB = ref<string>('latest')
/** Cache: key = 'current' | history_id → NoteHistoryDetail */
const detailCache = ref<Record<string, NoteHistoryDetail>>({})

const CHANGE_TYPE_LABEL: Record<number, string> = {
  [NOTE_HISTORY_CHANGE_TYPE.CREATE]: '创建',
  [NOTE_HISTORY_CHANGE_TYPE.UPDATE]: '编辑',
  [NOTE_HISTORY_CHANGE_TYPE.DELETE]: '删除',
  [NOTE_HISTORY_CHANGE_TYPE.ROLLBACK]: '回滚',
}

const CHANGE_SOURCE_LABEL: Record<number, string> = {
  [NOTE_HISTORY_CHANGE_SOURCE.MANUAL]: '用户',
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

/** Load a detail into cache (and set as selected for preview). */
async function selectHistory(h: NoteHistorySummary) {
  if (!props.noteId) return
  detailLoading.value = true
  selectedHistory.value = null
  try {
    const detail = await getNoteHistory(props.noteId, h.history_id)
    detailCache.value[h.history_id] = detail
    selectedHistory.value = detail
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

// ── Diff helpers ──────────────────────────────────────────────────────────────

/** Ensure a history detail is cached. Returns null for 'current'. */
async function ensureCached(historyId: string): Promise<NoteHistoryDetail | null> {
  if (historyId === 'current') return null
  if (detailCache.value[historyId]) return detailCache.value[historyId]
  if (!props.noteId) return null
  try {
    const detail = await getNoteHistory(props.noteId, historyId)
    detailCache.value[historyId] = detail
    return detail
  } catch {
    return null
  }
}

/** Resolve a version id to its text content. */
function versionContent(id: string): string {
  if (id === 'current') return props.currentContent ?? ''
  if (id === 'latest') return ''
  const detail = detailCache.value[id]
  return detail?.note_content ?? ''
}

/** Resolve a version id to its title. */
function versionTitle(id: string): string {
  if (id === 'current') return props.currentTitle ?? '无标题'
  if (id === 'latest') return ''
  const detail = detailCache.value[id]
  return detail?.note_title ?? ''
}

const diffVersionOptions = computed(() => {
  const options: { value: string; label: string }[] = [
    { value: 'current', label: `当前版本 · ${props.currentTitle || '无标题'}` },
  ]
  for (const h of histories.value) {
    const cached = detailCache.value[h.history_id]
    const time = formatTime(cached?.created_at ?? h.created_at)
    const type = CHANGE_TYPE_LABEL[h.change_type] ?? '变更'
    options.push({ value: h.history_id, label: `${time} · ${type}` })
  }
  return options
})

const diffLines = computed(() => {
  const a = versionContent(diffVersionA.value)
  const b = versionContent(diffVersionB.value)
  return computeDiff(a, b)
})

const latestHistoryId = computed(() => {
  return histories.value.length > 0 ? histories.value[0].history_id : null
})

/** Switch to diff mode and ensure both sides are loaded. */
async function switchToDiff() {
  mode.value = 'diff'
  // Default: latest history vs current
  if (diffVersionA.value === 'current' && diffVersionB.value === 'latest' && latestHistoryId.value) {
    diffVersionA.value = latestHistoryId.value
    diffVersionB.value = 'current'
  }
  // Ensure selected versions are cached
  await Promise.all([ensureCached(diffVersionA.value), ensureCached(diffVersionB.value)])
}

// Reset + load whenever the drawer opens (or the note changes while open).
watch(
  () => [props.visible, props.noteId] as const,
  async ([visible]) => {
    if (visible) {
      histories.value = []
      total.value = 0
      page.value = 1
      selectedHistory.value = null
      detailCache.value = {}
      mode.value = 'preview'
      diffVersionA.value = 'current'
      diffVersionB.value = 'latest'
      await loadHistories()
      // Preload the latest history for default diff
      if (histories.value.length > 0) {
        await ensureCached(histories.value[0].history_id)
      }
    }
  },
  { immediate: true },
)
</script>

<template>
  <Modal v-if="visible" title="历史记录" width="900px" @close="close">
    <div class="history-wrap flex flex-col md:flex-row gap-4 h-[80vh] md:h-[70vh] min-h-0">
      <!-- Left: list -->
      <div class="history-list w-full md:w-[260px] md:flex-shrink-0 max-h-[30vh] md:max-h-none overflow-y-auto">
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
                {{ CHANGE_SOURCE_LABEL[h.change_source] ?? '用户' }}
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

      <!-- Right: detail / diff -->
      <div class="history-detail">
        <!-- Mode tabs -->
        <div class="detail-tabs">
          <button class="tab-btn" :class="{ active: mode === 'preview' }" @click="mode = 'preview'">预览</button>
          <button class="tab-btn" :class="{ active: mode === 'diff' }" @click="switchToDiff">对比</button>
        </div>

        <!-- Preview mode -->
        <template v-if="mode === 'preview'">
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
        </template>

        <!-- Diff mode -->
        <template v-else>
          <div class="diff-selectors">
            <div class="diff-select-group">
              <label class="diff-label">版本 A</label>
              <select v-model="diffVersionA" class="diff-select">
                <option
                  v-for="opt in diffVersionOptions"
                  :key="opt.value"
                  :value="opt.value"
                  :disabled="opt.value === diffVersionB"
                >
                  {{ opt.label }}
                </option>
              </select>
              <span class="diff-ver-title">{{ versionTitle(diffVersionA) }}</span>
            </div>
            <div class="diff-vs">vs</div>
            <div class="diff-select-group">
              <label class="diff-label">版本 B</label>
              <select v-model="diffVersionB" class="diff-select">
                <option
                  v-for="opt in diffVersionOptions"
                  :key="opt.value"
                  :value="opt.value"
                  :disabled="opt.value === diffVersionA"
                >
                  {{ opt.label }}
                </option>
              </select>
              <span class="diff-ver-title">{{ versionTitle(diffVersionB) }}</span>
            </div>
          </div>
          <div class="diff-output">
            <div v-if="diffVersionA === diffVersionB" class="history-empty">请选择两个不同的版本进行对比</div>
            <div v-else-if="!diffLines.length" class="history-empty">两个版本内容相同</div>
            <div
              v-for="(line, idx) in diffLines"
              :key="idx"
              class="diff-line"
              :class="`diff-${line.type}`"
            >
              <span class="diff-ln diff-ln-a">{{ line.lineA ?? '' }}</span>
              <span class="diff-ln diff-ln-b">{{ line.lineB ?? '' }}</span>
              <span class="diff-prefix">{{ line.type === 'added' ? '+' : line.type === 'removed' ? '-' : ' ' }}</span>
              <span class="diff-text">{{ line.content }}</span>
            </div>
          </div>
        </template>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.history-list {
  border: 1px solid var(--border);
  border-radius: var(--radius);
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

/* ── Mode tabs ────────────────────────────────────────────────────────────── */
.detail-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.tab-btn {
  flex: 1;
  padding: 10px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}
.tab-btn:hover {
  color: var(--text-primary);
}
.tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

/* ── Preview mode ─────────────────────────────────────────────────────────── */
.detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
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
  flex-shrink: 0;
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
  flex-shrink: 0;
}

/* ── Diff mode ────────────────────────────────────────────────────────────── */
.diff-selectors {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.diff-select-group {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.diff-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.diff-select {
  width: 100%;
  padding: 6px 8px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-main);
  color: var(--text-primary);
  outline: none;
}
.diff-select:focus {
  border-color: var(--accent);
}
.diff-ver-title {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.diff-vs {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-tertiary);
  padding-top: 22px;
  flex-shrink: 0;
}
.diff-output {
  flex: 1;
  overflow-y: auto;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  line-height: 1.55;
}
.diff-line {
  display: flex;
  padding: 0 8px;
  min-height: 1.55em;
}
.diff-line.diff-added {
  background: rgba(22, 163, 74, 0.12);
}
.diff-line.diff-removed {
  background: rgba(220, 38, 38, 0.10);
}
.diff-line.diff-unchanged {
  color: var(--text-secondary);
}
.diff-ln {
  width: 40px;
  flex-shrink: 0;
  text-align: right;
  padding-right: 8px;
  color: var(--text-tertiary);
  user-select: none;
}
.diff-ln-a {
  /* line numbers for version A */
}
.diff-ln-b {
  /* line numbers for version B */
}
.diff-prefix {
  width: 16px;
  flex-shrink: 0;
  text-align: center;
  user-select: none;
  font-weight: 700;
}
.diff-added .diff-prefix {
  color: #16a34a;
}
.diff-removed .diff-prefix {
  color: #dc2626;
}
.diff-text {
  white-space: pre;
  word-break: break-all;
}

/* ── Shared ───────────────────────────────────────────────────────────────── */
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
