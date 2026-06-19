import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as authApi from '@/api/auth'
import { tokenStorage } from '@/api/client'
import type { UserInfo } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const loading = ref(false)

  const isLoggedIn = computed(() => !!tokenStorage.getAccess())
  const displayName = computed(() => user.value?.user_name ?? '用户')
  const avatarChar = computed(() => {
    const name = user.value?.user_name ?? ''
    return name ? name.charAt(0).toUpperCase() : '?'
  })

  async function login(user_account: string, password: string) {
    loading.value = true
    try {
      const res = await authApi.login(user_account, password)
      tokenStorage.set(res.access_token, res.refresh_token)
      await fetchMe()
    } finally {
      loading.value = false
    }
  }

  async function register(body: {
    user_account: string
    user_name: string
    password: string
  }) {
    loading.value = true
    try {
      const res = await authApi.register(body)
      tokenStorage.set(res.access_token, res.refresh_token)
      await fetchMe()
    } finally {
      loading.value = false
    }
  }

  async function fetchMe() {
    if (!tokenStorage.getAccess()) return
    try {
      user.value = await authApi.getMe()
    } catch {
      logout()
    }
  }

  function logout() {
    user.value = null
    tokenStorage.clear()
  }

  return {
    user,
    loading,
    isLoggedIn,
    displayName,
    avatarChar,
    login,
    register,
    fetchMe,
    logout,
  }
})
