<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '@/components/Icon.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import NoteEditor from '@/components/note/NoteEditor.vue'
import AiChat from '@/components/ai/AiChat.vue'
import AiSettings from '@/components/ai/AiSettings.vue'
import UserManage from '@/components/admin/UserManage.vue'
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
const activeView = ref<'notes' | 'chat' | 'settings' | 'users'>('notes')

// Mobile sidebar drawer state. On desktop (md+) the sidebar is always visible
// (static, translate-x-0), so this flag only affects the mobile overlay.
const sidebarOpen = ref(false)
function closeSidebar() {
  sidebarOpen.value = false
}
const sidebarClass = computed(() => [
  // Mobile: fixed overlay drawer, hidden off-canvas by default.
  // Desktop: static, always visible.
  'fixed inset-y-0 left-0 z-40 w-[min(86vw,var(--sidebar-width))] transition-transform duration-200',
  sidebarOpen.value ? 'translate-x-0' : '-translate-x-full',
  'md:static md:translate-x-0 md:z-auto md:w-[var(--sidebar-width)] md:flex-shrink-0',
])

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
  closeSidebar()
}

async function selectNote(id: SnowflakeId) {
  activeView.value = 'notes'
  closeSidebar()
  try {
    await noteStore.selectNote(id)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '打开笔记失败')
  }
}

function selectChat() {
  activeView.value = 'chat'
  noteStore.clearSelection()
  closeSidebar()
}

function selectSettings() {
  activeView.value = 'settings'
  noteStore.clearSelection()
  closeSidebar()
}

function selectUsers() {
  activeView.value = 'users'
  noteStore.clearSelection()
  closeSidebar()
}

async function newNote(categoryId: SnowflakeId | null = selectedCategoryId.value) {
  activeView.value = 'notes'
  closeSidebar()
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
  <div class="flex flex-col md:flex-row h-[100dvh]">
    <!-- Mobile top bar (hamburger to open the sidebar drawer) -->
    <header
      class="md:hidden flex items-center gap-2 h-[var(--header-height)] px-3 flex-shrink-0 border-b border-[var(--border)] bg-[var(--bg-sidebar)]"
    >
      <button class="btn-icon" title="菜单" @click="sidebarOpen = true">
        <Icon name="menu" :size="20" />
      </button>
      <img src="/favicon.svg" alt="智能笔记" class="w-7 h-7" />
      <span class="font-semibold text-[var(--text-primary)]">智能笔记</span>
    </header>

    <!-- Mobile sidebar backdrop -->
    <div
      v-if="sidebarOpen"
      class="md:hidden fixed inset-0 bg-black/40 z-30"
      @click="closeSidebar"
    />

    <AppSidebar
      :class="sidebarClass"
      :selected-category-id="selectedCategoryId"
      :selected-note-id="noteStore.selectedId"
      :active-view="activeView"
      :keyword="keyword"
      @update:keyword="keyword = $event"
      @new-note="newNote()"
      @new-note-in="newNote($event)"
      @new-category="openCreate(null)"
      @select-category="selectCategory"
      @select-note="selectNote"
      @create-child="openCreate($event)"
      @rename="openRename($event)"
      @remove="confirmRemoveCategory"
      @select-chat="selectChat"
      @select-settings="selectSettings"
      @select-users="selectUsers"
      @logout="logout"
    />

    <main class="flex-1 flex flex-col min-w-0 min-h-0">
      <NoteEditor v-show="activeView === 'notes'" />
      <AiChat v-show="activeView === 'chat'" />
      <AiSettings v-show="activeView === 'settings'" :visible="activeView === 'settings'" />
      <UserManage v-show="activeView === 'users'" :visible="activeView === 'users'" />
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
