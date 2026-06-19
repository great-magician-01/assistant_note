import { apiGet, apiPost } from './client'
import type { UserItem, UserListResponse } from '@/types'

export function listUsers(params: {
  status?: number | null
  keyword?: string | null
  page?: number
  page_size?: number
} = {}) {
  return apiGet<UserListResponse>('/v1/user', { params })
}

export function approveUser(user_id: string) {
  return apiPost<UserItem>(`/v1/user/${user_id}/approve`)
}

export function rejectUser(user_id: string) {
  return apiPost<UserItem>(`/v1/user/${user_id}/reject`)
}

export function updateUser(user_id: string, body: { is_active?: number }) {
  return apiPost<UserItem>(`/v1/user/${user_id}/update`, body)
}

export function resetUserPassword(user_id: string, password: string) {
  return apiPost<{ message: string }>(`/v1/user/${user_id}/reset-password`, { password })
}
