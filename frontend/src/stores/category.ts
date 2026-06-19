import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as categoryApi from '@/api/category'
import type { CategoryNode, SnowflakeId } from '@/types'
import { extractErrorMessage } from '@/api/client'

export const useCategoryStore = defineStore('category', () => {
  const tree = ref<CategoryNode[]>([])
  const loading = ref(false)
  const selectedId = ref<SnowflakeId | null>(null)

  /** Flatten the tree into a list (for lookups / counts). */
  const flatList = computed<CategoryNode[]>(() => {
    const out: CategoryNode[] = []
    const walk = (nodes: CategoryNode[]) => {
      for (const n of nodes) {
        out.push(n)
        if (n.children?.length) walk(n.children)
      }
    }
    walk(tree.value)
    return out
  })

  const selectedCategory = computed(() =>
    flatList.value.find((c) => c.category_id === selectedId.value) ?? null,
  )

  function findCategory(id: SnowflakeId | null): CategoryNode | null {
    if (!id) return null
    return flatList.value.find((c) => c.category_id === id) ?? null
  }

  async function fetchTree() {
    loading.value = true
    try {
      tree.value = await categoryApi.listCategories()
    } finally {
      loading.value = false
    }
  }

  async function create(body: categoryApi.CategoryCreatePayload) {
    const created = await categoryApi.createCategory(body)
    await fetchTree()
    return created
  }

  async function update(id: SnowflakeId, body: categoryApi.CategoryUpdatePayload) {
    const updated = await categoryApi.updateCategory(id, body)
    await fetchTree()
    return updated
  }

  async function remove(id: SnowflakeId) {
    await categoryApi.deleteCategory(id)
    if (selectedId.value === id) selectedId.value = null
    await fetchTree()
  }

  function select(id: SnowflakeId | null) {
    selectedId.value = id
  }

  /** Convenience wrapper that throws a friendly Error. */
  async function safeCreate(body: categoryApi.CategoryCreatePayload) {
    try {
      return await create(body)
    } catch (err) {
      throw new Error(extractErrorMessage(err, '创建分类失败'))
    }
  }

  async function safeUpdate(id: SnowflakeId, body: categoryApi.CategoryUpdatePayload) {
    try {
      return await update(id, body)
    } catch (err) {
      throw new Error(extractErrorMessage(err, '更新分类失败'))
    }
  }

  async function safeRemove(id: SnowflakeId) {
    try {
      return await remove(id)
    } catch (err) {
      throw new Error(extractErrorMessage(err, '删除分类失败'))
    }
  }

  return {
    tree,
    loading,
    selectedId,
    flatList,
    selectedCategory,
    findCategory,
    fetchTree,
    create,
    update,
    remove,
    safeCreate,
    safeUpdate,
    safeRemove,
    select,
  }
})
