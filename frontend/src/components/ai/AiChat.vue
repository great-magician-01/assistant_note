<script setup lang="ts">
import { ref, onMounted, nextTick, computed, watch } from 'vue'
import Icon from '@/components/Icon.vue'
import MarkdownView from '@/components/ai/MarkdownView.vue'
import { listAiConfigs, streamChat, getChatMessages } from '@/api/ai'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/api/client'
import type { AiConfig, SnowflakeId } from '@/types'

const authStore = useAuthStore()
const chatStore = useChatStore()
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
const configs = ref<AiConfig[]>([])
const messagesEl = ref<HTMLDivElement | null>(null)

const activeConfig = computed(
  () =>
    configs.value.find((c) => c.is_default && c.is_active) ??
    configs.value.find((c) => c.is_active) ??
    null,
)

onMounted(async () => {
  await Promise.all([loadConfigs(), chatStore.loadSessions()])
  if (!bubbles.value.length && !chatStore.currentSessionId) {
    bubbles.value.push({
      role: 'ai',
      text: '你好！我是 AI 助手。可以搜索/读取/编辑你的笔记，或直接提问。',
      tools: [],
    })
  }
})

// React to session selection or new-chat triggered from the sidebar.
watch(() => chatStore.currentSessionId, async (id) => {
  if (chatStore.sending) return  // Ignore onSession updates during streaming
  if (id !== null) {
    await loadSessionMessages(id)
  } else {
    bubbles.value = [{ role: 'ai', text: '开始新的对话吧。', tools: [] }]
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

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

// Monotonic token so a slow message fetch from an older session can't
// overwrite the bubbles of the session the user has since switched to.
let loadToken = 0

async function loadSessionMessages(id: SnowflakeId) {
  const token = ++loadToken
  bubbles.value = []
  try {
    const rows = await getChatMessages(id)
    if (token !== loadToken) return  // a newer switch superseded this fetch
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
    if (token !== loadToken) return
    if (!bubbles.value.length) {
      bubbles.value.push({ role: 'ai', text: '（空会话）', tools: [] })
    }
    await scrollToBottom()
  } catch (err) {
    if (token !== loadToken) return
    toast.error(extractErrorMessage(err, '加载会话失败'))
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || chatStore.sending) return

  if (!activeConfig.value) {
    toast.info('未检测到可用的 AI 配置，请先在设置中添加模型与配置')
    return
  }

  bubbles.value.push({ role: 'user', text, tools: [] })
  input.value = ''
  chatStore.sending = true
  // Push the ai bubble and immediately grab the reactive proxy from the
  // array — the local variable must reference the proxy for mutations in
  // onText / onToolStart / onToolEnd to trigger Vue reactivity.
  bubbles.value.push({ role: 'ai', text: '', tools: [] })
  const aiBubble = bubbles.value[bubbles.value.length - 1]
  await scrollToBottom()

  try {
    await streamChat(
      {
        session_id: chatStore.currentSessionId,
        message: text,
        config_id: activeConfig.value.config_id,
      },
      {
        onSession: (data) => {
          chatStore.currentSessionId = data.session_id
        },
        onText: (delta) => {
          aiBubble.text += delta
          void scrollToBottom()
        },
        onToolStart: (data) => {
          // Pushed into the reactive array (aiBubble.tools) so the chip
          // proxy is tracked by Vue — use find() in onToolEnd to mutate
          // through the proxy.
          aiBubble.tools.push({ id: data.id, name: data.name, pending: true })
        },
        onToolEnd: (data) => {
          // Find through the reactive array to mutate via the Vue proxy.
          const chip = aiBubble.tools.find(c => c.id === data.id)
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
          void chatStore.loadSessions()
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
    chatStore.sending = false
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
  <div class="chat-view">
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
            :streaming="chatStore.sending && i === bubbles.length - 1 && msg.role === 'ai'"
          />
          <div v-else-if="chatStore.sending && i === bubbles.length - 1" class="chat-bubble typing">思考中…</div>
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
      <button class="chat-send-btn" :disabled="!input.trim() || chatStore.sending" @click="send">
        <Icon name="send" :size="18" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg-main);
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
