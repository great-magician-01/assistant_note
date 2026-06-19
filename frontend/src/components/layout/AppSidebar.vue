<script setup lang="ts">
import { ref, watch } from 'vue'
import dayjs from 'dayjs'
import Icon from '@/components/Icon.vue'
import NoteTree from '@/components/NoteTree.vue'
import { useNoteStore } from '@/stores/note'
import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/composables/useTheme'
import type { SnowflakeId } from '@/types'

const props = defineProps<{
  selectedCategoryId: SnowflakeId | null
  selectedNoteId: SnowflakeId | null
  activeView: 'notes' | 'chat' | 'settings'
  keyword: string
}>()

const emit = defineEmits<{
  'update:keyword': [value: string]
  'new-note': []
  'new-note-in': [categoryId: SnowflakeId]
  'new-category': []
  'select-category': [id: SnowflakeId]
  'select-note': [id: SnowflakeId]
  'create-child': [parent: import('@/types').CategoryNode]
  rename: [node: import('@/types').CategoryNode]
  remove: [node: import('@/types').CategoryNode]
  'select-chat': []
  'select-settings': []
  logout: []
}>()

const noteStore = useNoteStore()
const authStore = useAuthStore()
const { theme, toggle } = useTheme()

// Debounced search input — drives the combined tree filter in AppView.
const localKeyword = ref(props.keyword)
let searchTimer: number | undefined
watch(localKeyword, (val) => {
  if (searchTimer) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => emit('update:keyword', val.trim()), 300)
})
// Keep local in sync if parent resets the keyword (e.g. cleared elsewhere).
watch(
  () => props.keyword,
  (val) => {
    if (val !== localKeyword.value) localKeyword.value = val
  },
)

function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = dayjs(iso)
  return d.isValid() ? d.format('MM-DD') : ''
}

const categories = () => noteStore.tree?.categories ?? []
const uncategorized = () => noteStore.tree?.uncategorized ?? []
</script>

<template>
  <aside class="sidebar">
    <!-- Header -->
    <div class="sidebar-header">
      <img src="/favicon.svg" alt="智能笔记" class="logo-icon" />
      <span class="logo-text">智能笔记</span>
    </div>

    <!-- Actions -->
    <div class="sidebar-actions">
      <button class="btn btn-primary" @click="emit('new-note')">
        <Icon name="plus" :size="14" :stroke-width="2.2" />
        新建笔记
      </button>
      <button class="btn btn-ghost" @click="emit('new-category')">
        <Icon name="folder-plus" :size="14" :stroke-width="2.2" />
        分类
      </button>
    </div>

    <!-- Search -->
    <div class="sidebar-search">
      <Icon name="search" :size="14" class="search-icon" />
      <input
        v-model="localKeyword"
        type="text"
        placeholder="搜索笔记…"
        class="search-input"
      />
    </div>

    <!-- Combined category + note tree -->
    <div class="sidebar-content">
      <div v-if="noteStore.treeLoading && !noteStore.tree" class="loading-hint">
        加载中…
      </div>

      <template v-else-if="noteStore.tree">
        <div v-if="!categories().length && !uncategorized().length" class="empty-hint">
          还没有笔记，点击上方“新建笔记”开始
        </div>

        <NoteTree
          v-if="categories().length"
          :nodes="categories()"
          :selected-note-id="activeView === 'notes' ? selectedNoteId : null"
          :selected-category-id="selectedCategoryId"
          @select-note="emit('select-note', $event)"
          @select-category="emit('select-category', $event)"
          @create-child="emit('create-child', $event)"
          @rename="emit('rename', $event)"
          @remove="emit('remove', $event)"
          @new-note-in="emit('new-note-in', $event)"
        />

        <!-- Uncategorized notes -->
        <div v-if="uncategorized().length" class="uncategorized-group">
          <div class="group-label">
            <Icon name="inbox" :size="14" class="row-icon" />
            <span>未分类</span>
            <span class="count-badge">{{ uncategorized().length }}</span>
          </div>
          <div
            v-for="note in uncategorized()"
            :key="note.note_id"
            class="note-row"
            :class="{ active: note.note_id === selectedNoteId }"
            :title="note.note_summary || note.note_preview || ''"
            @click="emit('select-note', note.note_id)"
          >
            <Icon v-if="note.is_pinned" name="pin" :size="11" class="pin-icon" />
            <Icon v-else name="file-text" :size="13" class="note-icon" />
            <span class="note-title">{{ note.note_title || '无标题' }}</span>
            <span class="note-date">{{ formatDate(note.updated_at || note.created_at) }}</span>
          </div>
        </div>
      </template>

      <!-- Virtual "AI 对话" entry -->
      <div class="tree-section-title ai-title">
        <span>AI 助手</span>
      </div>
      <div
        class="tree-row ai-row"
        :class="{ active: activeView === 'chat' }"
        @click="emit('select-chat')"
      >
        <span class="tree-toggle" style="visibility: hidden"></span>
        <Icon name="robot" :size="16" class="row-icon" />
        <span class="tree-label">AI 对话</span>
      </div>
      <div
        v-if="authStore.isAdmin"
        class="tree-row ai-row"
        :class="{ active: activeView === 'settings' }"
        @click="emit('select-settings')"
      >
        <span class="tree-toggle" style="visibility: hidden"></span>
        <Icon name="settings" :size="16" class="row-icon" />
        <span class="tree-label">AI 设置</span>
      </div>
    </div>

    <!-- Footer -->
    <div class="sidebar-footer">
      <div class="avatar">{{ authStore.avatarChar }}</div>
      <div class="user-info">
        <div class="user-name">{{ authStore.displayName }}</div>
        <div class="user-role">{{ authStore.user?.user_account }}</div>
      </div>
      <div class="sidebar-footer-actions">
        <button class="btn-icon" title="切换主题" @click="toggle">
          <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
        </button>
        <button class="btn-icon" title="退出登录" @click="emit('logout')">
          <Icon name="logout" :size="16" />
        </button>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: background 0.3s, border-color 0.3s;
}
.sidebar-header {
  height: var(--header-height);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border-bottom: 1px solid var(--border);
}
.logo-icon {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}
.logo-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}
.sidebar-actions {
  display: flex;
  gap: 8px;
  padding: 12px 16px 8px;
}
.sidebar-search {
  position: relative;
  padding: 0 16px 8px;
}
.search-icon {
  position: absolute;
  left: 26px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary);
  pointer-events: none;
}
.search-input {
  width: 100%;
  height: 30px;
  padding: 0 10px 0 30px;
  font-size: 12px;
}
.sidebar-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px 10px;
}
.tree-section-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary);
  padding: 12px 6px 6px;
}
.ai-title {
  margin-top: 8px;
}
.loading-hint,
.empty-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 8px 10px;
}

/* Uncategorized group reuses the tree row styling. */
.uncategorized-group {
  margin-top: 4px;
}
.group-label {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
}
.group-label .row-icon {
  opacity: 0.7;
}
.count-badge {
  font-size: 10px;
  color: var(--text-tertiary);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0 6px;
  min-width: 16px;
  text-align: center;
}

/* Note leaf rows shared with NoteTree.vue. */
.note-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px 4px 22px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: background 0.15s, color 0.15s;
}
.note-row:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.note-row.active {
  background: var(--bg-active);
  color: var(--text-accent);
}
.pin-icon {
  color: var(--accent);
  flex-shrink: 0;
}
.note-icon {
  color: currentColor;
  opacity: 0.55;
  flex-shrink: 0;
}
.note-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
}
.note-date {
  font-size: 10px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

/* AI virtual row reuses tree-row styling */
.ai-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: background 0.15s, color 0.15s;
}
.ai-row:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.ai-row.active {
  background: var(--bg-active);
  color: var(--text-accent);
}
.row-icon {
  flex-shrink: 0;
  opacity: 0.75;
}
.tree-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
}
.tree-toggle {
  width: 18px;
  height: 18px;
}

.sidebar-footer {
  padding: 12px 14px;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 10px;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), #6366f1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}
.user-info {
  flex: 1;
  min-width: 0;
}
.user-name {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.user-role {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sidebar-footer-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}
.sidebar-footer-actions .btn-icon {
  width: 30px;
  height: 30px;
}
</style>
