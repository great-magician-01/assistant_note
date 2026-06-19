import { apiGet, apiPost } from './client'
import type { CategoryNode, SnowflakeId } from '@/types'

export interface CategoryCreatePayload {
  category_name: string
  category_icon?: string | null
  category_sort?: number
  parent_id?: SnowflakeId | null
}

export interface CategoryUpdatePayload {
  category_name?: string
  category_icon?: string | null
  category_sort?: number
  parent_id?: SnowflakeId | null
}

export function listCategories() {
  return apiGet<CategoryNode[]>('/v1/category')
}

export function createCategory(body: CategoryCreatePayload) {
  return apiPost<CategoryNode>('/v1/category', body)
}

export function updateCategory(id: SnowflakeId, body: CategoryUpdatePayload) {
  return apiPost<CategoryNode>(`/v1/category/${id}/update`, body)
}

export function deleteCategory(id: SnowflakeId) {
  return apiPost<{ message: string }>(`/v1/category/${id}/delete`)
}
