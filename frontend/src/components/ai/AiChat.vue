<script setup lang="ts">
import { ref, onMounted, nextTick, computed } from 'vue'
import Icon from '@/components/Icon.vue'
import MarkdownView from '@/components/ai/MarkdownView.vue'
import { listAiConfigs, streamChat, listChatSessions, getChatMessages, deleteChatSession } from '@/api/ai'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/api/client'
import type { AiConfig, ChatSession, SnowflakeId } from '@/types'

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
const sessions = ref<ChatSession[]>([])
const currentSessionId = ref<SnowflakeId | null>(null)
const messagesEl = ref<HTMLDivElement | null>(null)

const activeConfig = computed(
  () =>
    configs.value.find((c) => c.is_default && c.is_active) ??
    configs.value.find((c) => c.is_active) ??
    null,
)

onMounted(async () => {
  await Promise.all([loadConfigs(), loadSessions()])
  if (!bubbles.value.length) {
    bubbles.value.push({
      role: 'ai',
      text: '你好！我是 AI 助手。可以搜索/读取/编辑你的笔记，或直接提问。',
      tools: [],
    })
  }
})

async function loadConfigs() {
  try {
    configs.value = await listAiConfigs()
  } catch (err) {
    configs.value = []
    console.warn(extractErrorMessage(err, '加载 AI 配置失败'))
  }
}

async function loadSessions() {
  try {
    sessions.value = await listChatSessions()
  } catch (err) {
    sessions.value = []
    console.warn(extractErrorMessage(err, '加载会话列表失败'))
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

async function selectSession(id: SnowflakeId) {
  if (sending.value) return
  currentSessionId.value = id
  bubbles.value = []
  try {
    const rows = await getChatMessages(id)
    // Reconstruct bubbles: assistant text + following tool rows become one AI bubble.
    for (const row of rows) {
      if (row.role === 'user') {
        bubbles.value.push({ role: 'user', text: row.content ?? '', tools: [] })
      } else if (row.role === 'assistant') {
        bubbles.value.push({
          role: 'ai',
          text: row.content ?? '',
          tools: [],
        })
      } else if (row.role === 'tool') {
        // Attach tool result to the last AI bubble.
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
    if (!bubbles.value.length) {
      bubbles.value.push({ role: 'ai', text: '（空会话）', tools: [] })
    }
    await scrollToBottom()
  } catch (err) {
    toast.error(extractErrorMessage(err, '加载会话失败'))
  }
}

function newChat() {
  if (sending.value) return
  currentSessionId.value = null
  bubbles.value = [
    { role: 'ai', text: '开始新的对话吧。', tools: [] },
  ]
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return

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

  // Track tool chips by id so tool_end updates the matching tool_start chip.
  const toolIndex = new Map<string, ToolChip>()

  try {
    await streamChat(
      {
        session_id: currentSessionId.value,
        message: text,
        config_id: activeConfig.value.config_id,
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
        },
        onDone: () => {
          // Refresh session list so the new/updated session shows with its title.
          void loadSessions()
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

async function removeSession(id: SnowflakeId) {
  if (!window.confirm('删除该会话？')) return
  try {
    await deleteChatSession(id)
    sessions.value = sessions.value.filter((s) => s.session_id !== id)
    if (currentSessionId.value === id) newChat()
    toast.success('已删除')
  } catch (err) {
    toast.error(extractErrorMessage(err, '删除失败'))
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
  <div class="chat-view">
    <div class="chat-sidebar">
      <button class="new-chat-btn" @click="newChat">
        <Icon name="plus" :size="16" />
        <span>新对话</span>
      </button>
      <div class="session-list">
        <div v-if="!sessions.length" class="session-empty">暂无历史会话</div>
        <div
          v-for="s in sessions"
          :key="s.session_id"
          class="session-item"
          :class="{ active: currentSessionId === s.session_id }"
          @click="selectSession(s.session_id)"
        >
          <Icon name="chat" :size="14" class="session-icon" />
          <span class="session-title">{{ s.session_title || '新对话' }}</span>
          <button class="session-del" title="删除" @click.stop="removeSession(s.session_id)">
            <Icon name="trash" :size="13" />
          </button>
        </div>
      </div>
    </div>

    <div class="chat-main">
      <div class="chat-header">
        <div class="chat-header-icon">
          <Icon name="robot" :size="20" />
        </div>
        <div class="chat-header-info">
          <div class="chat-header-title">AI 助手</div>
          <div class="chat-header-status">
            <template v-if="activeConfig">
              {{ activeConfig.config_name }} · {{ activeConfig.model || '未知模型' }}
            </template>
            <template v-else>未配置可用模型</template>
          </div>
        </div>
      </div>

      <div ref="messagesEl" class="chat-messages">
        <div
          v-for="(msg, i) in bubbles"
          :key="i"
          class="chat-message"
          :class="msg.role"
        >
          <div class="chat-avatar">
            {{ msg.role === 'user' ? authStore.avatarChar : 'AI' }}
          </div>
          <div class="chat-content">
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
              class="chat-bubble"
              :content="msg.text"
              :plain="msg.role === 'user'"
              :streaming="sending && i === bubbles.length - 1 && msg.role === 'ai'"
            />
            <div v-else-if="sending && i === bubbles.length - 1" class="chat-bubble typing">思考中…</div>
          </div>
        </div>
      </div>

      <div class="chat-input-area">
        <textarea
          v-model="input"
          class="chat-textarea"
          placeholder="向 AI 提问…（Ctrl+Enter 发送）"
          @keydown="onKeydown"
        />
        <button class="chat-send-btn" :disabled="!input.trim() || sending" @click="send">
          <Icon name="send" :size="18" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-view {
  flex: 1;
  display: flex;
  background: var(--bg-main);
  min-width: 0;
}
.chat-sidebar {
  width: 220px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 12px;
  gap: 10px;
  overflow: hidden;
}
.new-chat-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
}
.new-chat-btn:hover {
  background: var(--accent-hover);
}
.session-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.session-empty {
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 12px 8px;
  text-align: center;
}
.session-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
}
.session-item:hover {
  background: var(--bg-hover);
}
.session-item.active {
  background: var(--accent-light);
  color: var(--text-primary);
}
.session-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}
.session-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-del {
  opacity: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}
.session-item:hover .session-del {
  opacity: 1;
}
.session-del:hover {
  background: var(--bg-input);
  color: #dc2626;
}
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
}
.chat-header-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--accent-light);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent);
  flex-shrink: 0;
}
.chat-header-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.chat-header-status {
  font-size: 12px;
  color: var(--text-tertiary);
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.chat-message {
  display: flex;
  gap: 12px;
  max-width: 85%;
}
.chat-message.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.chat-message.ai {
  align-self: flex-start;
}
.chat-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
}
.chat-message.user .chat-avatar {
  background: linear-gradient(135deg, var(--accent), #6366f1);
  color: #fff;
}
.chat-message.ai .chat-avatar {
  background: var(--accent-light);
  color: var(--accent);
}
.chat-content {
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
.chat-bubble {
  padding: 12px 16px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.65;
  color: var(--text-secondary);
}
.chat-message.user .chat-bubble {
  background: var(--accent);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.chat-message.ai .chat-bubble {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}
.typing {
  color: var(--text-tertiary);
  font-style: italic;
}
.chat-input-area {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 14px 20px 18px;
  border-top: 1px solid var(--border);
  background: var(--bg-main);
}
.chat-textarea {
  flex: 1;
  min-height: 44px;
  max-height: 140px;
  resize: none;
  padding: 10px 14px;
  font-size: 14px;
  line-height: 1.5;
}
.chat-send-btn {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s, opacity 0.2s;
  flex-shrink: 0;
}
.chat-send-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}
.chat-send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
