import { apiGet, apiPost } from './client'
import type { TokenResponse, UserInfo } from '@/types'

export function login(user_account: string, password: string) {
  return apiPost<TokenResponse>('/v1/auth/login', { user_account, password })
}

export function register(body: {
  user_account: string
  user_name: string
  password: string
}) {
  return apiPost<TokenResponse>('/v1/auth/register', body)
}

export function refresh(refresh_token: string) {
  return apiPost<TokenResponse>('/v1/auth/refresh', { refresh_token })
}

export function getMe() {
  return apiGet<UserInfo>('/v1/auth/me')
}
