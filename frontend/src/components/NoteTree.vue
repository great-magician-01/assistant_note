<script setup lang="ts">
import { ref } from 'vue'
import dayjs from 'dayjs'
import Icon from '@/components/Icon.vue'
import type { CategoryTreeNode, SnowflakeId } from '@/types'

const props = defineProps<{
  nodes: CategoryTreeNode[]
  selectedNoteId: SnowflakeId | null
  selectedCategoryId: SnowflakeId | null
  /** Indentation depth — only set on recursive self-invocations. */
  depth?: number
}>()

const emit = defineEmits<{
  'select-note': [id: SnowflakeId]
  'select-category': [id: SnowflakeId]
  'create-child': [parent: CategoryTreeNode]
  rename: [node: CategoryTreeNode]
  remove: [node: CategoryTreeNode]
  'new-note-in': [categoryId: SnowflakeId]
}>()

// Track which nodes are collapsed, keyed by id. Empty = everything expanded,
// so notes are visible by default (the tree doubles as the note list).
const collapsed = ref<Record<string, boolean>>({})

function toggle(id: SnowflakeId, e: MouseEvent) {
  e.stopPropagation()
  collapsed.value[id] = !collapsed.value[id]
}

function isCollapsed(id: SnowflakeId) {
  return collapsed.value[id] === true
}

function iconFor(node: CategoryTreeNode): string {
  return node.category_icon || 'folder'
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = dayjs(iso)
  return d.isValid() ? d.format('MM-DD') : ''
}
</script>

<template>
  <div class="tree">
    <div v-for="node in nodes" :key="node.category_id" class="tree-node">
      <div
        class="tree-row"
        :class="{ active: node.category_id === selectedCategoryId }"
        @click="emit('select-category', node.category_id)"
      >
        <span
          class="tree-toggle"
          :class="{ collapsed: isCollapsed(node.category_id) }"
          :style="{
            visibility: node.children.length || node.notes.length ? 'visible' : 'hidden',
          }"
          @click="toggle(node.category_id, $event)"
        >
          <Icon name="chevron-down" :size="12" :stroke-width="2.5" />
        </span>
        <Icon :name="iconFor(node)" :size="15" class="row-icon" />
        <span class="tree-label">{{ node.category_name }}</span>
        <span v-if="node.notes.length" class="count-badge">{{ node.notes.length }}</span>

        <span class="row-actions">
          <button
            class="row-action"
            title="在此分类新建笔记"
            @click.stop="emit('new-note-in', node.category_id)"
          >
            <Icon name="plus" :size="13" />
          </button>
          <button
            class="row-action"
            title="新建子分类"
            @click.stop="emit('create-child', node)"
          >
            <Icon name="folder-plus" :size="13" />
          </button>
          <button class="row-action" title="重命名" @click.stop="emit('rename', node)">
            <Icon name="edit" :size="13" />
          </button>
          <button class="row-action danger" title="删除" @click.stop="emit('remove', node)">
            <Icon name="trash" :size="13" />
          </button>
        </span>
      </div>

      <div
        v-if="!isCollapsed(node.category_id) && (node.children.length || node.notes.length)"
        class="tree-children"
      >
        <!-- Sub-categories first, then this category's notes -->
        <NoteTree
          v-if="node.children.length"
          :nodes="node.children"
          :selected-note-id="selectedNoteId"
          :selected-category-id="selectedCategoryId"
          :depth="(depth ?? 0) + 1"
          @select-note="emit('select-note', $event)"
          @select-category="emit('select-category', $event)"
          @create-child="emit('create-child', $event)"
          @rename="emit('rename', $event)"
          @remove="emit('remove', $event)"
          @new-note-in="emit('new-note-in', $event)"
        />

        <div
          v-for="note in node.notes"
          :key="note.note_id"
          class="note-row"
          :class="{ active: note.note_id === selectedNoteId }"
          :title="note.note_summary || note.note_preview || ''"
          @click="emit('select-note', note.note_id)"
        >
          <Icon
            v-if="note.is_pinned"
            name="pin"
            :size="11"
            class="pin-icon"
          />
          <Icon v-else name="file-text" :size="13" class="note-icon" />
          <span class="note-title">{{ note.note_title || '无标题' }}</span>
          <span class="note-date">{{ formatDate(note.updated_at || note.created_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tree-node {
  user-select: none;
}
.tree-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  color: var(--text-secondary);
  position: relative;
}
.tree-row:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.tree-row.active {
  background: var(--bg-active);
  color: var(--text-accent);
}
.row-icon {
  flex-shrink: 0;
  color: currentColor;
  opacity: 0.75;
}
.tree-toggle {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  flex-shrink: 0;
  transition: transform 0.2s;
  color: var(--text-tertiary);
}
.tree-toggle:hover {
  background: var(--bg-active);
}
.tree-toggle.collapsed {
  transform: rotate(-90deg);
}
.tree-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
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
  flex-shrink: 0;
}
.row-actions {
  display: none;
  gap: 1px;
  flex-shrink: 0;
}
.tree-row:hover .row-actions {
  display: flex;
}
.row-action {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: var(--text-tertiary);
}
.row-action:hover {
  background: var(--bg-active);
  color: var(--text-primary);
}
.row-action.danger:hover {
  color: var(--danger);
}
.tree-children {
  padding-left: 16px;
  overflow: hidden;
}

/* Note leaf rows — compact, one line, file-explorer style */
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
</style>
