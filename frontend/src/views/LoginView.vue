<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/api/client'
import { initTheme } from '@/composables/useTheme'

const authStore = useAuthStore()
const toast = useToast()
const router = useRouter()
const route = useRoute()

type Mode = 'login' | 'register'
const mode = ref<Mode>('login')

const account = ref('')
const userName = ref('')
const password = ref('')
const confirm = ref('')
const submitting = ref(false)

initTheme()

function switchMode(m: Mode) {
  mode.value = m
  password.value = ''
  confirm.value = ''
}

async function submit() {
  if (!account.value || !password.value) {
    toast.error('请输入账号和密码')
    return
  }
  if (mode.value === 'register') {
    if (!userName.value.trim()) {
      toast.error('请输入用户名')
      return
    }
    if (password.value.length < 6) {
      toast.error('密码至少 6 位')
      return
    }
    if (password.value !== confirm.value) {
      toast.error('两次密码不一致')
      return
    }
  }

  submitting.value = true
  try {
    if (mode.value === 'login') {
      await authStore.login(account.value.trim(), password.value)
      toast.success('登录成功')
      const redirect = (route.query.redirect as string) || '/'
      router.replace(redirect)
    } else {
      await authStore.register({
        user_account: account.value.trim(),
        user_name: userName.value.trim(),
        password: password.value,
      })
      // Approval-gated registration: no auto-login. Tell the user and return
      // to the login tab so they can come back once an admin approves them.
      toast.success('注册成功，请等待管理员审核后登录')
      switchMode('login')
    }
  } catch (err) {
    toast.error(extractErrorMessage(err, mode.value === 'login' ? '登录失败' : '注册失败'))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <img src="/favicon.svg" alt="智能笔记" class="brand-icon" />
        <h1 class="brand-title">智能笔记</h1>
        <p class="brand-sub">AI 驱动的云笔记 · 整理你的所思所学</p>
      </div>

      <div class="tabs">
        <button
          class="tab"
          :class="{ active: mode === 'login' }"
          @click="switchMode('login')"
        >
          登录
        </button>
        <button
          class="tab"
          :class="{ active: mode === 'register' }"
          @click="switchMode('register')"
        >
          注册
        </button>
      </div>

      <form class="form" @submit.prevent="submit">
        <label class="field">
          <span class="label">账号</span>
          <input
            v-model="account"
            class="input"
            placeholder="账号 / 邮箱"
            autocomplete="username"
          />
        </label>

        <label v-if="mode === 'register'" class="field">
          <span class="label">用户名</span>
          <input
            v-model="userName"
            class="input"
            placeholder="显示名称"
            autocomplete="nickname"
          />
        </label>

        <label class="field">
          <span class="label">密码</span>
          <input
            v-model="password"
            class="input"
            type="password"
            placeholder="至少 6 位"
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
          />
        </label>

        <label v-if="mode === 'register'" class="field">
          <span class="label">确认密码</span>
          <input
            v-model="confirm"
            class="input"
            type="password"
            placeholder="再次输入密码"
            autocomplete="new-password"
          />
        </label>

        <button class="submit-btn" type="submit" :disabled="submitting">
          {{ submitting ? '处理中…' : mode === 'login' ? '登 录' : '注 册' }}
        </button>
      </form>

      <p class="hint">
        <template v-if="mode === 'login'">
          还没有账号？<a @click="switchMode('register')">立即注册</a>
        </template>
        <template v-else>
          已有账号？<a @click="switchMode('login')">直接登录</a>
        </template>
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--bg-body), var(--accent-light));
  padding: 20px;
}
.login-card {
  width: 100%;
  max-width: 380px;
  background: var(--bg-main);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: var(--shadow-lg);
  padding: 28px 24px;
}
@media (min-width: 768px) {
  .login-card {
    padding: 36px 32px;
  }
}
.brand {
  text-align: center;
  margin-bottom: 24px;
}
.brand-icon {
  width: 48px;
  height: 48px;
}
.brand-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin-top: 8px;
  letter-spacing: -0.5px;
}
.brand-sub {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}
.tabs {
  display: flex;
  background: var(--bg-input);
  border-radius: 8px;
  padding: 4px;
  margin-bottom: 20px;
}
.tab {
  flex: 1;
  padding: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-tertiary);
  border-radius: 6px;
  transition: all 0.2s;
}
.tab.active {
  background: var(--bg-main);
  color: var(--text-primary);
  box-shadow: var(--shadow);
}
.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
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
  height: 40px;
  padding: 0 12px;
  font-size: 14px;
}
.submit-btn {
  margin-top: 4px;
  height: 42px;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  transition: background 0.2s, opacity 0.2s;
}
.submit-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}
.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.hint {
  margin-top: 18px;
  text-align: center;
  font-size: 12px;
  color: var(--text-tertiary);
}
.hint a {
  color: var(--accent);
  cursor: pointer;
  font-weight: 500;
}
</style>
