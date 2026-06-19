<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import NoteEditor from '@/components/note/NoteEditor.vue'
import AiChat from '@/components/ai/AiChat.vue'
import Toaster from '@/components/Toaster.vue'
import CategoryFormModal from '@/components/category/CategoryFormModal.vue'
import { useAuthStore } from '@/stores/auth'
import { useCategoryStore } from '@/stores/category'
import { useNoteStore } from '@/stores/note'
import { useToast } from '@/composables/useToast'
import { initTheme } from '@/composables/useTheme'
import type { CategoryNode, SnowflakeId } from '@/types'

const router = useRouter()
const authStore = useAuthStore()
const categoryStore = useCategoryStore()
const noteStore = useNoteStore()
const toast = useToast()

const keyword = ref('')
const activeTag = ref<string | null>(null)
const selectedCategoryId = ref<SnowflakeId | null>(null)
const activeView = ref<'notes' | 'chat'>('notes')

// Category modal state
const modalVisible = ref(false)
const modalNode = ref<CategoryNode | null>(null)
const modalParent = ref<CategoryNode | null>(null)

function openCreate(parent: CategoryNode | null = null) {
  modalNode.value = null
  modalParent.value = parent
  modalVisible.value = true
}
function openRename(node: CategoryNode) {
  modalNode.value = node
  modalParent.value = null
  modalVisible.value = true
}

async function confirmRemoveCategory(node: CategoryNode) {
  if (!window.confirm(`确定删除分类「${node.category_name}」？\n（含子分类将一并删除；非空分类需先移动/删除其下笔记）`))
    return
  try {
    await categoryStore.safeRemove(node.category_id)
    if (selectedCategoryId.value === node.category_id) {
      selectedCategoryId.value = null
    }
    await noteStore.refreshTree()
    toast.success('已删除分类')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '删除失败')
  }
}

async function onCategorySaved() {
  // Category name/structure changed — refresh the combined tree too.
  await noteStore.refreshTree()
}

function selectCategory(id: SnowflakeId) {
  selectedCategoryId.value = id
  activeView.value = 'notes'
}

async function selectNote(id: SnowflakeId) {
  activeView.value = 'notes'
  try {
    await noteStore.selectNote(id)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '打开笔记失败')
  }
}

function selectChat() {
  activeView.value = 'chat'
  noteStore.clearSelection()
}

async function newNote(categoryId: SnowflakeId | null = selectedCategoryId.value) {
  activeView.value = 'notes'
  try {
    await noteStore.create({
      note_title: '无标题笔记',
      note_content: '',
      category_id: categoryId,
    })
    toast.success('已新建笔记')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '新建失败')
  }
}

// Debounced tree refetch when the search/tag filter changes.
let filterTimer: number | undefined
watch(
  () => [keyword.value, activeTag.value],
  () => {
    if (filterTimer) window.clearTimeout(filterTimer)
    filterTimer = window.setTimeout(() => {
      void noteStore.fetchTree({
        keyword: keyword.value || null,
        tag: activeTag.value,
      })
    }, 300)
  },
)

function logout() {
  authStore.logout()
  router.push('/login')
}

function onForceLogout() {
  toast.info('登录已过期，请重新登录')
  authStore.logout()
  router.push('/login')
}

onMounted(async () => {
  initTheme()
  window.addEventListener('auth:logout', onForceLogout)
  await authStore.fetchMe()
  await categoryStore.fetchTree()
  await noteStore.fetchTags()
  await noteStore.fetchTree()
})

onBeforeUnmount(() => {
  window.removeEventListener('auth:logout', onForceLogout)
})
</script>

<template>
  <div class="app">
    <AppSidebar
      :selected-category-id="selectedCategoryId"
      :selected-note-id="noteStore.selectedId"
      :active-view="activeView"
      :keyword="keyword"
      :active-tag="activeTag"
      :tags="noteStore.tags"
      @update:keyword="keyword = $event"
      @update:active-tag="activeTag = $event"
      @new-note="newNote()"
      @new-note-in="newNote($event)"
      @new-category="openCreate(null)"
      @select-category="selectCategory"
      @select-note="selectNote"
      @create-child="openCreate($event)"
      @rename="openRename($event)"
      @remove="confirmRemoveCategory"
      @select-chat="selectChat"
      @logout="logout"
    />

    <main class="main">
      <NoteEditor v-show="activeView === 'notes'" />
      <AiChat v-show="activeView === 'chat'" />
    </main>

    <CategoryFormModal
      v-model:visible="modalVisible"
      :node="modalNode"
      :parent="modalParent"
      @saved="onCategorySaved"
    />
    <Toaster />
  </div>
</template>

<style scoped>
.app {
  display: flex;
  height: 100vh;
}
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
</style>
