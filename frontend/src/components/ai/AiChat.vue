<script setup lang="ts">
import { ref, onMounted, nextTick, computed } from 'vue'
import Icon from '@/components/Icon.vue'
import { listAiConfigs } from '@/api/ai'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/api/client'
import type { AiConfig, ChatMessage } from '@/types'

const authStore = useAuthStore()
const toast = useToast()

const messages = ref<ChatMessage[]>([])
const input = ref('')
const sending = ref(false)
const configs = ref<AiConfig[]>([])
const loadingConfigs = ref(false)
const messagesEl = ref<HTMLDivElement | null>(null)

const activeConfig = computed(
  () =>
    configs.value.find((c) => c.is_default && c.is_active) ??
    configs.value.find((c) => c.is_active) ??
    null,
)

onMounted(async () => {
  await loadConfigs()
  if (!messages.value.length) {
    messages.value.push({
      role: 'ai',
      content:
        '你好！我是 DeepSeek AI 助手。你可以向我提问、让我总结笔记或帮你润色文字。\n\n（提示：AI 推理接口尚未在后端上线，当前为离线演示模式。）',
    })
  }
})

async function loadConfigs() {
  loadingConfigs.value = true
  try {
    configs.value = await listAiConfigs()
  } catch (err) {
    // Non-fatal — configs may not be set up yet.
    configs.value = []
    console.warn(extractErrorMessage(err, '加载 AI 配置失败'))
  } finally {
    loadingConfigs.value = false
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  sending.value = true
  await scrollToBottom()

  // The backend does not yet expose a chat-completion endpoint. We surface a
  // clear, honest placeholder reply rather than fabricating model output.
  await new Promise((r) => setTimeout(r, 400))
  messages.value.push({
    role: 'ai',
    content:
      'AI 推理接口（/v1/ai/chat）尚未在后端上线，暂时无法生成回复。\n\n' +
      `当前已配置 ${configs.value.length} 个 AI 配置${
        activeConfig.value ? `（默认：${activeConfig.value.config_name}）` : ''
      }。待后端接入模型推理后即可正常对话。`,
  })
  sending.value = false
  await scrollToBottom()

  if (!configs.value.length) {
    toast.info('未检测到 AI 配置，请先在设置中添加模型与配置')
  }
}

function onKeydown(e: KeyboardEvent) {
  // Ctrl/Cmd+Enter to send, plain Enter for newline.
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
        <div class="chat-header-title">DeepSeek AI 助手</div>
        <div class="chat-header-status">
          <template v-if="loadingConfigs">加载配置中…</template>
          <template v-else-if="activeConfig">
            {{ activeConfig.config_name }} · {{ activeConfig.model || '未知模型' }}
          </template>
          <template v-else>未配置可用模型</template>
        </div>
      </div>
    </div>

    <div ref="messagesEl" class="chat-messages">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="chat-message"
        :class="msg.role"
      >
        <div class="chat-avatar">
          {{ msg.role === 'user' ? authStore.avatarChar : 'AI' }}
        </div>
        <div class="chat-bubble">{{ msg.content }}</div>
      </div>
      <div v-if="sending" class="chat-message ai">
        <div class="chat-avatar">AI</div>
        <div class="chat-bubble typing">思考中…</div>
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
  white-space: pre-wrap;
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
