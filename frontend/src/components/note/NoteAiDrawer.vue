<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue'
import Icon from '@/components/Icon.vue'
import MarkdownView from '@/components/ai/MarkdownView.vue'
import {
  listAiConfigs,
  streamChat,
  listChatSessions,
  getChatMessages,
} from '@/api/ai'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/api/client'
import type { AiConfig, SnowflakeId } from '@/types'

const props = defineProps<{
  visible: boolean
  noteId: SnowflakeId | null
  noteTitle?: string
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'note-changed': []
}>()

const authStore = useAuthStore()
const toast = useToast()

interface ToolChip {
  id: string
  name: string
  result?: string
  isError?: boolean
  pending: boolean
}
interface Bubble {
  role: 'user' | 'ai'
  text: string
  tools: ToolChip[]
}

const bubbles = ref<Bubble[]>([])
const input = ref('')
const sending = ref(false)
const configs = ref<AiConfig[]>([])
const currentSessionId = ref<SnowflakeId | null>(null)
const messagesEl = ref<HTMLDivElement | null>(null)
// Which note's thread is currently loaded, so toggling the drawer off/on for the
// same note doesn't blow away an in-progress conversation.
const loadedNoteId = ref<SnowflakeId | null>(null)

const activeConfig = computed(
  () =>
    configs.value.find((c) => c.is_default && c.is_active) ??
    configs.value.find((c) => c.is_active) ??
    null,
)

const GREETING = '你好！我是这篇笔记的 AI 助手。可以帮你续写、润色、总结，或直接修改这篇笔记。'

function resetToGreeting() {
  currentSessionId.value = null
  bubbles.value = [{ role: 'ai', text: GREETING, tools: [] }]
}

async function ensureConfigs() {
  if (configs.value.length) return
  try {
    configs.value = await listAiConfigs()
  } catch (err) {
    configs.value = []
    console.warn(extractErrorMessage(err, '加载 AI 配置失败'))
  }
}

async function loadForNote(noteId: SnowflakeId) {
  // Prefer the most recent existing thread for this note; else start fresh.
  try {
    const sessions = await listChatSessions(noteId)
    if (sessions.length) {
      await selectSession(sessions[0].session_id)
      return
    }
  } catch (err) {
    console.warn(extractErrorMessage(err, '加载笔记会话失败'))
  }
  resetToGreeting()
}

async function selectSession(id: SnowflakeId) {
  currentSessionId.value = id
  bubbles.value = []
  try {
    const rows = await getChatMessages(id)
    for (const row of rows) {
      if (row.role === 'user') {
        bubbles.value.push({ role: 'user', text: row.content ?? '', tools: [] })
      } else if (row.role === 'assistant') {
        bubbles.value.push({ role: 'ai', text: row.content ?? '', tools: [] })
      } else if (row.role === 'tool') {
        const last = bubbles.value[bubbles.value.length - 1]
        const target = last && last.role === 'ai' ? last : null
        const chip: ToolChip = {
          id: row.tool_call_id ?? '',
          name: row.tool_name ?? '',
          result: row.content ?? '',
          isError: row.is_error === 1,
          pending: false,
        }
        if (target) target.tools.push(chip)
        else bubbles.value.push({ role: 'ai', text: '', tools: [chip] })
      }
    }
    if (!bubbles.value.length) bubbles.value.push({ role: 'ai', text: '（空会话）', tools: [] })
    await scrollToBottom()
  } catch (err) {
    toast.error(extractErrorMessage(err, '加载会话失败'))
    resetToGreeting()
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

// (Re)load whenever the drawer opens for a different note. Reopening the same
// note keeps the live conversation intact.
watch(
  () => [props.visible, props.noteId] as const,
  async ([visible, noteId]) => {
    if (!visible || !noteId) return
    await ensureConfigs()
    if (loadedNoteId.value !== noteId) {
      loadedNoteId.value = noteId
      await loadForNote(noteId)
    }
  },
  { immediate: true },
)

function newChat() {
  if (sending.value) return
  resetToGreeting()
}

function close() {
  emit('update:visible', false)
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  if (!props.noteId) return
  if (!activeConfig.value) {
    toast.info('未检测到可用的 AI 配置，请先在设置中添加模型与配置')
    return
  }

  bubbles.value.push({ role: 'user', text, tools: [] })
  input.value = ''
  sending.value = true
  const aiBubble: Bubble = { role: 'ai', text: '', tools: [] }
  bubbles.value.push(aiBubble)
  await scrollToBottom()

  const toolIndex = new Map<string, ToolChip>()
  // Whether the AI mutated a note during this turn — if so, reload the editor's
  // note after the turn so the user sees the in-place edit.
  let noteMutated = false

  try {
    await streamChat(
      {
        session_id: currentSessionId.value,
        message: text,
        config_id: activeConfig.value.config_id,
        note_id: currentSessionId.value ? null : props.noteId,
      },
      {
        onSession: (data) => {
          currentSessionId.value = data.session_id
        },
        onText: (delta) => {
          aiBubble.text += delta
          void scrollToBottom()
        },
        onToolStart: (data) => {
          const chip: ToolChip = { id: data.id, name: data.name, pending: true }
          toolIndex.set(data.id, chip)
          aiBubble.tools.push(chip)
        },
        onToolEnd: (data) => {
          const chip = toolIndex.get(data.id)
          if (chip) {
            chip.result = data.result
            chip.isError = data.is_error
            chip.pending = false
          } else {
            aiBubble.tools.push({
              id: data.id,
              name: data.name,
              result: data.result,
              isError: data.is_error,
              pending: false,
            })
          }
          if (data.name === 'edit_note' || data.name === 'create_note') {
            noteMutated = true
          }
        },
        onDone: () => {
          // Mark this note's thread as loaded so reopening stays on it.
          loadedNoteId.value = props.noteId
          if (noteMutated) emit('note-changed')
        },
        onError: (message) => {
          if (!aiBubble.text) aiBubble.text = '（对话出错）'
          toast.error(message)
        },
      },
    )
  } catch (err) {
    toast.error(extractErrorMessage(err, '对话失败'))
  } finally {
    sending.value = false
    await scrollToBottom()
  }
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault()
    void send()
  }
}
</script>

<template>
  <aside class="note-ai-drawer" :class="{ open: visible }">
    <header class="drawer-header">
      <div class="drawer-title-wrap">
        <div class="drawer-title-icon"><Icon name="robot" :size="16" /></div>
        <div class="drawer-title-text">
          <div class="drawer-title">笔记 AI 助手</div>
          <div class="drawer-sub" :title="noteTitle || ''">{{ noteTitle || '当前笔记' }}</div>
        </div>
      </div>
      <div class="drawer-actions">
        <button class="icon-btn" title="新对话" :disabled="sending" @click="newChat">
          <Icon name="plus" :size="16" />
        </button>
        <button class="icon-btn" title="收起" @click="close">
          <span class="close-x">×</span>
        </button>
      </div>
    </header>

    <div ref="messagesEl" class="drawer-messages">
      <div v-for="(msg, i) in bubbles" :key="i" class="msg" :class="msg.role">
        <div class="msg-avatar">{{ msg.role === 'user' ? authStore.avatarChar : 'AI' }}</div>
        <div class="msg-content">
          <div v-if="msg.tools.length" class="tool-chips">
            <div
              v-for="(t, j) in msg.tools"
              :key="j"
              class="tool-chip"
              :class="{ error: t.isError, pending: t.pending }"
            >
              <Icon name="tool" :size="12" />
              <span class="tool-name">{{ t.name }}</span>
              <span v-if="t.pending" class="tool-status">执行中…</span>
              <span v-else-if="t.isError" class="tool-status">失败</span>
              <span v-else class="tool-status">完成</span>
            </div>
          </div>
          <MarkdownView
            v-if="msg.text"
            class="msg-bubble"
            :content="msg.text"
            :plain="msg.role === 'user'"
            :streaming="sending && i === bubbles.length - 1 && msg.role === 'ai'"
          />
          <div v-else-if="sending && i === bubbles.length - 1" class="msg-bubble typing">思考中…</div>
        </div>
      </div>
    </div>

    <div class="drawer-input-area">
      <textarea
        v-model="input"
        class="drawer-textarea"
        placeholder="针对这篇笔记提问…（Ctrl+Enter 发送）"
        @keydown="onKeydown"
      />
      <button class="drawer-send-btn" :disabled="!input.trim() || sending" @click="send">
        <Icon name="send" :size="18" />
      </button>
    </div>
  </aside>
</template>

<style scoped>
.note-ai-drawer {
  width: 0;
  overflow: hidden;
  background: var(--bg-main);
  border-left: 1px solid transparent;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.25s ease, border-color 0.25s ease;
}
.note-ai-drawer.open {
  width: 420px;
  border-left-color: var(--border);
}
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  gap: 8px;
}
.drawer-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.drawer-title-icon {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--accent-light);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent);
  flex-shrink: 0;
}
.drawer-title-text {
  min-width: 0;
}
.drawer-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.drawer-sub {
  font-size: 12px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 240px;
}
.drawer-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.icon-btn {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  color: var(--text-tertiary);
  transition: all 0.15s;
}
.icon-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.close-x {
  font-size: 20px;
  line-height: 1;
}
.drawer-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.msg {
  display: flex;
  gap: 10px;
  max-width: 92%;
}
.msg.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.msg.ai {
  align-self: flex-start;
}
.msg-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
}
.msg.user .msg-avatar {
  background: linear-gradient(135deg, var(--accent), #6366f1);
  color: #fff;
}
.msg.ai .msg-avatar {
  background: var(--accent-light);
  color: var(--accent);
}
.msg-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.tool-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tool-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border-radius: 12px;
  font-size: 11px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}
.tool-chip.pending {
  color: var(--accent);
  border-color: var(--accent);
}
.tool-chip.error {
  color: #dc2626;
  border-color: rgba(220, 38, 38, 0.4);
}
.tool-name {
  font-weight: 600;
}
.tool-status {
  color: var(--text-tertiary);
}
.msg-bubble {
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-secondary);
}
.msg.user .msg-bubble {
  background: var(--accent);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.msg.ai .msg-bubble {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}
.typing {
  color: var(--text-tertiary);
  font-style: italic;
}
.drawer-input-area {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding: 12px 14px 14px;
  border-top: 1px solid var(--border);
  background: var(--bg-main);
}
.drawer-textarea {
  flex: 1;
  min-height: 42px;
  max-height: 120px;
  resize: none;
  padding: 9px 12px;
  font-size: 13px;
  line-height: 1.5;
}
.drawer-send-btn {
  width: 38px;
  height: 38px;
  border-radius: 9px;
  background: var(--accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s, opacity 0.2s;
  flex-shrink: 0;
}
.drawer-send-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}
.drawer-send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
