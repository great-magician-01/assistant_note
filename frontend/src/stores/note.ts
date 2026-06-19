import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as noteApi from '@/api/note'
import type {
  CategoryTreeNode,
  Note,
  NoteTreeItem,
  NoteTreeParams,
  SnowflakeId,
} from '@/types'
import { extractErrorMessage } from '@/api/client'

export const useNoteStore = defineStore('note', () => {
  // Combined sidebar tree: categories (with nested notes) + uncategorized notes.
  const tree = ref<{ categories: CategoryTreeNode[]; uncategorized: NoteTreeItem[]; total: number } | null>(null)
  const treeLoading = ref(false)
  // Remember the last filter so CUD operations can refresh the same view.
  const lastParams = ref<NoteTreeParams>({})

  const selectedId = ref<SnowflakeId | null>(null)
  /** The currently selected full note (with content), fetched on open. */
  const currentNote = ref<Note | null>(null)
  const tags = ref<string[]>([])

  async function fetchTree(params: NoteTreeParams = {}) {
    lastParams.value = { ...params }
    treeLoading.value = true
    try {
      tree.value = await noteApi.listNoteTree(params)
    } catch (err) {
      throw new Error(extractErrorMessage(err, '加载笔记失败'))
    } finally {
      treeLoading.value = false
    }
  }

  /** Re-fetch with the last-used filter (after CUD). */
  async function refreshTree() {
    await fetchTree(lastParams.value)
  }

  async function fetchTags() {
    try {
      tags.value = await noteApi.listTags()
    } catch (err) {
      // Non-fatal — tags are an enhancement.
      console.warn(extractErrorMessage(err, '加载标签失败'))
    }
  }

  async function selectNote(id: SnowflakeId | null) {
    selectedId.value = id
    if (!id) {
      currentNote.value = null
      return null
    }
    // Tree items omit content; fetch the full note for the editor.
    try {
      currentNote.value = await noteApi.getNote(id)
      return currentNote.value
    } catch (err) {
      throw new Error(extractErrorMessage(err, '加载笔记失败'))
    }
  }

  async function create(body: noteApi.NoteCreatePayload) {
    try {
      const created = await noteApi.createNote(body)
      await refreshTree()
      await selectNote(created.note_id)
      return created
    } catch (err) {
      throw new Error(extractErrorMessage(err, '创建笔记失败'))
    }
  }

  async function update(id: SnowflakeId, body: noteApi.NoteUpdatePayload) {
    try {
      const updated = await noteApi.updateNote(id, body)
      currentNote.value = updated
      // Keep the sidebar item in sync without a full refetch (autosave-friendly).
      patchNoteInTree(id, {
        note_title: updated.note_title,
        note_summary: updated.note_summary,
        note_tags: updated.note_tags,
        is_pinned: updated.is_pinned,
        note_word_count: updated.note_word_count,
        updated_at: updated.updated_at,
      })
      return updated
    } catch (err) {
      throw new Error(extractErrorMessage(err, '保存笔记失败'))
    }
  }

  async function remove(id: SnowflakeId) {
    try {
      await noteApi.deleteNote(id)
      removeNoteFromTree(id)
      if (selectedId.value === id) {
        selectedId.value = null
        currentNote.value = null
      }
    } catch (err) {
      throw new Error(extractErrorMessage(err, '删除笔记失败'))
    }
  }

  async function move(noteIds: SnowflakeId[], categoryId: SnowflakeId | null) {
    try {
      const res = await noteApi.moveNotes(noteIds, categoryId)
      await refreshTree()
      return res
    } catch (err) {
      throw new Error(extractErrorMessage(err, '移动笔记失败'))
    }
  }

  function clearSelection() {
    selectedId.value = null
    currentNote.value = null
  }

  // ── Tree mutation helpers (operate in place to avoid refetching on autosave) ─

  function patchNoteInTree(id: SnowflakeId, patch: Partial<NoteTreeItem>) {
    if (!tree.value) return
    const apply = (list: NoteTreeItem[]): boolean => {
      const i = list.findIndex((x) => x.note_id === id)
      if (i >= 0) {
        list[i] = { ...list[i], ...patch }
        return true
      }
      return false
    }
    const walk = (nodes: CategoryTreeNode[]): boolean => {
      for (const n of nodes) {
        if (apply(n.notes)) return true
        if (n.children?.length && walk(n.children)) return true
      }
      return false
    }
    walk(tree.value.categories) || apply(tree.value.uncategorized)
  }

  function removeNoteFromTree(id: SnowflakeId) {
    if (!tree.value) return
    const drop = (list: NoteTreeItem[]): boolean => {
      const i = list.findIndex((x) => x.note_id === id)
      if (i >= 0) {
        list.splice(i, 1)
        return true
      }
      return false
    }
    const walk = (nodes: CategoryTreeNode[]): boolean => {
      for (const n of nodes) {
        if (drop(n.notes)) return true
        if (n.children?.length && walk(n.children)) return true
      }
      return false
    }
    walk(tree.value.categories) || drop(tree.value.uncategorized)
  }

  return {
    tree,
    treeLoading,
    selectedId,
    currentNote,
    tags,
    fetchTree,
    refreshTree,
    fetchTags,
    selectNote,
    create,
    update,
    remove,
    move,
    clearSelection,
    patchNoteInTree,
    removeNoteFromTree,
  }
})
