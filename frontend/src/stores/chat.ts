import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listChatSessions } from '@/api/ai'
import type { ChatSession, SnowflakeId } from '@/types'

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<ChatSession[]>([])
  const currentSessionId = ref<SnowflakeId | null>(null)
  const sending = ref(false)

  async function loadSessions() {
    try {
      sessions.value = await listChatSessions()
    } catch {
      sessions.value = []
    }
  }

  function startNewChat() {
    if (sending.value) return
    currentSessionId.value = null
  }

  function setCurrentSession(id: SnowflakeId) {
    if (sending.value) return
    currentSessionId.value = id
  }

  function removeSession(id: SnowflakeId) {
    sessions.value = sessions.value.filter((s) => s.session_id !== id)
    if (currentSessionId.value === id) startNewChat()
  }

  return { sessions, currentSessionId, sending, loadSessions, startNewChat, setCurrentSession, removeSession }
})
