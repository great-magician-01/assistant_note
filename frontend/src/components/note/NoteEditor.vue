<script setup lang="ts">
import { ref, watch, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import dayjs from 'dayjs'
import type Vditor from 'vditor'
// vditor does NOT auto-load its own stylesheet at runtime (it only fetches
// icons/i18n/lute JS dynamically). The main index.css must be imported by the
// app — otherwise the toolbar svgs render unstyled (giant + stacked). Importing
// it statically lets Vite bundle it; the vditor-local-assets middleware in
// vite.config.ts still serves the on-demand JS (lute, icons, i18n).
import 'vditor/dist/index.css'
import Icon from '@/components/Icon.vue'
import NoteHistoryDrawer from '@/components/note/NoteHistoryDrawer.vue'
import NoteAiDrawer from '@/components/note/NoteAiDrawer.vue'
import { useNoteStore } from '@/stores/note'
import { useCategoryStore } from '@/stores/category'
import { useToast } from '@/composables/useToast'
import { useTheme } from '@/composables/useTheme'
import { uploadImage } from '@/api/upload'
import type { Note } from '@/types'

const noteStore = useNoteStore()
const categoryStore = useCategoryStore()
const toast = useToast()
const { theme } = useTheme()

const vditorRef = ref<HTMLDivElement | null>(null)
const previewRef = ref<HTMLDivElement | null>(null)
const title = ref('')
const content = ref('')
const tagsStr = ref('')
const saving = ref(false)
const vditorReady = ref(false)
const historyVisible = ref(false)
const aiVisible = ref(false)
// Preview is the default when opening a note; the user opts into editing via
// the toolbar toggle. Empty notes (incl. just-created ones) skip preview since
// there is nothing to read.
const mode = ref<'preview' | 'edit'>('preview')
let saveTimer: number | undefined
// Guards against races between rapid note/mode switches while Lute loads.
let previewToken = 0
// Non-reactive: holding the Vditor instance directly avoids deep proxying.
let vditorInstance: Vditor | null = null

const note = computed<Note | null>(() => noteStore.currentNote)

const categoryName = computed(() => {
  const cid = note.value?.category_id ?? null
  return categoryStore.findCategory(cid)?.category_name ?? '未分类'
})

const wordCount = computed(() => content.value.length)

const updatedLabel = computed(() => {
  const iso = note.value?.updated_at || note.value?.created_at
  if (!iso) return ''
  const d = dayjs(iso)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : ''
})

function vditorTheme(): 'dark' | 'classic' {
  return theme.value === 'dark' ? 'dark' : 'classic'
}

function hljsStyle(): string {
  return theme.value === 'dark' ? 'github-dark' : 'github'
}

// Vditor toolbar: curated set.
const VDITOR_TOOLBAR: string[] = [
  'emoji', 'headings', 'bold', 'italic', 'strike', '|',
  'line', 'quote', 'list', 'ordered-list', 'check', 'outdent', 'indent', '|',
  'code', 'inline-code', 'link', 'upload', 'table', '|',
  'undo', 'redo', '|',
  'preview', 'fullscreen',
]

// Image upload — keep in sync with backend (UPLOAD_MAX_SIZE_MB / allowed exts).
// SVG excluded: see config.py UPLOAD_ALLOWED_EXT.
const UPLOAD_MAX_BYTES = 10 * 1024 * 1024
const UPLOAD_ALLOWED_EXT = ['png', 'jpg', 'jpeg', 'gif', 'webp']

// Editor uses Vditor `ir` (instant-render) mode: Markdown syntax is rendered
// inline as you type (# → heading, ** → bold), and pressing Enter creates a
// real block, so newlines/blank lines are preserved. This avoids the `sv`
// (split source) mode behavior where every keystroke re-parses the current
// block through Lute and Markdown-normalizes consecutive blank lines away
// (which made Enter-created blank lines vanish on the next character).
function buildVditorOptions(initialValue: string): ConstructorParameters<typeof Vditor>[1] {
  return {
    // Serve Vditor's runtime assets (Lute/CSS/fonts/...) locally instead of
    // from unpkg — see the vditor-local-assets plugin in vite.config.ts.
    cdn: `${import.meta.env.BASE_URL}vditor`,
    mode: 'ir',
    value: initialValue,
    placeholder: '开始写作…（支持 Markdown）',
    lang: 'zh_CN',
    // Fill the host container rather than sizing to content. The host chain
    // (.vditor-wrap → flex:1 → .editor-body → flex:1 → .editor) gives the
    // editor the full remaining viewport height.
    height: '100%',
    minHeight: 300,
    theme: vditorTheme(),
    icon: 'ant',
    cache: { enable: false },
    toolbar: VDITOR_TOOLBAR,
    toolbarConfig: { pin: true },
    preview: {
      hljs: { lineNumber: true, style: hljsStyle() },
    },
    upload: {
      // Custom upload handler — bypasses Vditor's own XHR so we use the app's
      // axios client (fresh auth token + sliding refresh) and control insertion
      // + error toasts. This single handler covers toolbar pick, paste, and
      // drag-and-drop of images. Returning null signals "no error" to Vditor.
      accept: 'image/*',
      multiple: false,
      handler: (files: File[]) => {
        void handleUpload(files)
        return null
      },
    },
    input: (value: string) => {
      content.value = value
      scheduleSave()
    },
    after: () => {
      vditorReady.value = true
      // The constructor's `value` is applied, but if a note switch happened
      // while Lute was still loading, content.value may now point at a newer
      // note — re-seed so the editor never shows stale content. `input` won't
      // fire for a no-op setValue, so this is safe on first load too.
      if (vditorInstance && vditorInstance.getValue() !== content.value) {
        vditorInstance.setValue(content.value, true)
      }
    },
  }
}

async function initVditor(initialValue: string) {
  if (!vditorRef.value) return
  const VditorCtor = (await import('vditor')).default
  vditorReady.value = false
  vditorInstance = new VditorCtor(vditorRef.value, buildVditorOptions(initialValue))
}

// Create the Vditor instance if it does not exist yet (covers the case where
// the editor mounts with no note selected, and the user picks one later — the
// note_id watch alone would only reset refs and never instantiate Vditor).
//
// The editor region is rendered behind `v-else` (only when a note is set), so
// when the FIRST note arrives the `vditorRef` element does not exist yet at the
// moment the watch fires — we must await nextTick for the DOM to render before
// initVditor can attach. Without this, initVditor's `if (!vditorRef.value)
// return` bails silently and the editor never appears until the next note
// switch (when the element already exists).
async function ensureVditor() {
  if (vditorInstance || !note.value) return
  await nextTick()
  if (!vditorRef.value || vditorInstance) return
  await initVditor(note.value.note_content ?? '')
}

// Render the note body as read-only Markdown into the preview container.
// Reuses Vditor's static preview renderer so preview matches edit-mode output.
async function renderPreview() {
  if (mode.value !== 'preview') return
  const el = previewRef.value
  if (!el || !content.value) return
  const token = ++previewToken
  const VditorCtor = (await import('vditor')).default
  // A later switch may have landed while Lute was loading — bail out stale.
  if (token !== previewToken || mode.value !== 'preview' || !previewRef.value) return
  await VditorCtor.preview(previewRef.value, content.value, {
    mode: theme.value === 'dark' ? 'dark' : 'light',
    cdn: `${import.meta.env.BASE_URL}vditor`,
    lang: 'zh_CN',
    icon: 'ant',
    hljs: { lineNumber: true, style: hljsStyle() },
    anchor: 0,
  })
}

function switchToEdit() {
  if (mode.value === 'edit') return
  mode.value = 'edit'
}

function switchToPreview() {
  if (mode.value === 'preview') return
  // Flush any pending autosave so the preview reflects the latest edits.
  if (saveTimer) {
    window.clearTimeout(saveTimer)
    void doSave()
  }
  mode.value = 'preview'
}

// Sync local editable fields only when the *note identity* changes — NOT on
// autosave echo (store reassigns currentNote with the same id after each save).
// This is what stops the title input from being snapped back to "无标题" right
// after the user clears it.
watch(
  () => note.value?.note_id,
  (id, prevId) => {
    if (id === prevId) return
    if (saveTimer) window.clearTimeout(saveTimer)
    const n = note.value
    title.value = n?.note_title ?? ''
    content.value = n?.note_content ?? ''
    tagsStr.value = (n?.note_tags ?? []).join(', ')
    // Opening a note defaults to preview; empty notes go straight to edit.
    mode.value = content.value.trim() ? 'preview' : 'edit'
    if (vditorInstance && vditorReady.value) {
      // Instance already loaded — swap in the new note's content.
      vditorInstance.setValue(content.value, true)
    }
    // The preview/edit host lives inside the `v-else` block, which is only in
    // the DOM while a note is selected. Switching from the empty state to the
    // first note updates the DOM *after* this pre-flush watcher runs, so
    // previewRef is still null here on that first switch (renderPreview would
    // bail, leaving the body blank until a later note switch re-binds the ref).
    // Defer to the next tick — mirroring ensureVditor — so the ref is bound.
    if (mode.value === 'preview') {
      void nextTick().then(() => renderPreview())
    }
  },
  { immediate: true },
)

// Entering edit mode lazily creates the Vditor instance (deferred so preview
// never pays the Lute-load cost). Entering preview re-renders the body.
watch(mode, (m) => {
  if (m === 'edit') {
    void ensureVditor()
  } else {
    void renderPreview()
  }
})

function scheduleSave() {
  if (!note.value) return
  if (saveTimer) window.clearTimeout(saveTimer)
  saving.value = true
  saveTimer = window.setTimeout(doSave, 800)
}

// Upload one or more images and insert them as Markdown at the cursor. Used by
// the toolbar upload button, paste, and drag-and-drop (all routed through
// Vditor's upload handler). Runs sequentially so insertions land in order.
async function handleUpload(files: File[]) {
  const vd = vditorInstance
  if (!vd) return
  for (const file of files) {
    const ext = (file.name.split('.').pop() ?? '').toLowerCase()
    if (!UPLOAD_ALLOWED_EXT.includes(ext)) {
      toast.error(`不支持的图片类型:${file.name}`)
      continue
    }
    if (file.size > UPLOAD_MAX_BYTES) {
      toast.error(`图片超过 10MB:${file.name}`)
      continue
    }
    // Use the filename (minus extension) as alt text; clip to keep it tidy.
    const alt = file.name.replace(/\.[^.]+$/, '').slice(0, 60) || 'image'
    try {
      const { url } = await uploadImage(file)
      vd.insertValue(`\n![${alt}](${url})\n`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '图片上传失败')
    }
  }
}

async function doSave() {
  if (!note.value) return
  saving.value = true
  try {
    await noteStore.update(note.value.note_id, {
      note_title: title.value.trim() || '无标题',
      note_content: content.value,
      note_tags: parseTags(tagsStr.value),
    })
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    saving.value = false
  }
}

function parseTags(s: string): string[] {
  return s
    .split(/[,，]/)
    .map((t) => t.trim())
    .filter(Boolean)
}

async function togglePin() {
  if (!note.value) return
  const next = note.value.is_pinned ? 0 : 1
  try {
    await noteStore.update(note.value.note_id, { is_pinned: next })
    toast.success(next ? '已置顶' : '已取消置顶')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '操作失败')
  }
}

async function confirmDelete() {
  if (!note.value) return
  if (!window.confirm(`确定删除「${note.value.note_title || '无标题'}」？`)) return
  try {
    await noteStore.remove(note.value.note_id)
    toast.success('已删除')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '删除失败')
  }
}

function toggleAi() {
  if (!note.value) return
  aiVisible.value = !aiVisible.value
}

function openHistory() {
  if (!note.value) return
  historyVisible.value = true
}

// After a server-side change to the current note (history rollback, or the AI
// drawer editing the note via a tool), re-fetch it and re-seed the local
// editor state. The note_id watch can't do this: it early-returns when the id
// is unchanged (an intentional guard against autosave echo snapping edits back),
// so a same-id refresh must be done explicitly here.
function syncFromNote() {
  const n = note.value
  if (!n) return
  title.value = n.note_title ?? ''
  content.value = n.note_content ?? ''
  tagsStr.value = (n.note_tags ?? []).join(', ')
  if (vditorInstance && vditorReady.value) {
    vditorInstance.setValue(content.value, true)
  }
  if (mode.value === 'preview') {
    void nextTick().then(() => renderPreview())
  }
}

async function reloadCurrentNote() {
  if (!note.value) return
  // Flush any pending autosave first so we don't overwrite the server-side
  // content with stale local edits.
  if (saveTimer) {
    window.clearTimeout(saveTimer)
    saveTimer = undefined
  }
  await noteStore.selectNote(note.value.note_id)
  syncFromNote()
}

async function onRolledBack() {
  await reloadCurrentNote()
}

// The note's AI drawer edited the note in place via a tool — reload so the
// editor reflects the AI's changes instead of showing stale local content.
function onAiNoteChanged() {
  void reloadCurrentNote()
}

// React to app theme changes.
watch(theme, () => {
  if (vditorInstance) {
    vditorInstance.setTheme(vditorTheme())
  }
  if (mode.value === 'preview') void renderPreview()
})

onMounted(() => {
  // The immediate note_id watch runs before the template mounts, so its
  // renderPreview/ensureVditor calls bail on null refs — finish the job here.
  if (mode.value === 'edit') void ensureVditor()
  else void renderPreview()
})

onBeforeUnmount(() => {
  if (saveTimer) {
    window.clearTimeout(saveTimer)
    void doSave()
  }
  if (vditorInstance) {
    vditorInstance.destroy()
    vditorInstance = null
  }
})
</script>

<template>
  <div class="editor">
    <!-- Empty state -->
    <div v-if="!note" class="empty-state">
      <Icon name="file-text" :size="48" />
      <p>选择一篇笔记开始阅读或编辑</p>
    </div>

    <template v-else>
      <div class="editor-toolbar py-3.5 px-4 md:py-4 md:px-8">
        <div class="toolbar-group">
          <span class="editor-mode-label" :class="{ 'mode-edit': mode === 'edit' }">
            {{ mode === 'edit' ? '编辑模式' : '预览模式' }}
          </span>
        </div>
        <div class="toolbar-group">
          <span class="save-status hidden md:inline">{{ saving ? '保存中…' : '已保存' }}</span>
          <button
            v-if="mode === 'preview'"
            class="toolbar-btn primary-btn"
            title="编辑"
            @click="switchToEdit"
          >
            <Icon name="edit" :size="16" />
            <span class="btn-text hidden md:inline">编辑</span>
          </button>
          <button
            v-else
            class="toolbar-btn primary-btn"
            title="完成编辑"
            @click="switchToPreview"
          >
            <Icon name="book" :size="16" />
            <span class="btn-text hidden md:inline">完成</span>
          </button>
          <button
            class="toolbar-btn"
            :class="{ active: note.is_pinned }"
            :title="note.is_pinned ? '取消置顶' : '置顶'"
            @click="togglePin"
          >
            <Icon name="pin" :size="16" />
          </button>
          <button class="toolbar-btn" title="历史记录" @click="openHistory">
            <Icon name="clock" :size="16" />
          </button>
          <button
            class="toolbar-btn"
            :class="{ active: aiVisible }"
            title="AI 助手"
            @click="toggleAi"
          >
            <Icon name="robot" :size="16" />
          </button>
          <button class="toolbar-btn" title="删除" @click="confirmDelete">
            <Icon name="trash" :size="16" />
          </button>
        </div>
      </div>

      <div class="editor-workspace">
        <!-- Read-only preview (default when opening a note) -->
        <div v-show="mode === 'preview'" class="editor-body preview-body p-5 md:py-6 md:px-8">
          <h1 class="preview-title">{{ title || '无标题' }}</h1>

          <div class="editor-meta-bar">
            <span class="editor-meta-item">
              <Icon name="calendar" :size="13" />
              {{ updatedLabel }}
            </span>
            <span class="editor-meta-item">
              <Icon name="folder" :size="13" />
              {{ categoryName }}
            </span>
            <span class="editor-meta-item">
              <Icon name="file-text" :size="13" />
              {{ wordCount }} 字
            </span>
          </div>

          <div v-if="(note.note_tags ?? []).length" class="tags-row preview-tags">
            <Icon name="tag" :size="14" class="tags-icon" />
            <span v-for="t in note.note_tags ?? []" :key="t" class="tag-chip">{{ t }}</span>
          </div>

          <div class="preview-content-wrap">
            <div ref="previewRef" class="preview-content" />
            <div v-if="!content" class="preview-empty">
              <Icon name="file-text" :size="36" />
              <p>这篇笔记还是空的，点击「编辑」开始写作</p>
            </div>
          </div>
        </div>

        <!-- Edit mode (Vditor) -->
        <div v-show="mode === 'edit'" class="editor-body p-5 md:py-6 md:px-8">
          <input
            v-model="title"
            class="editor-title-input"
            placeholder="笔记标题"
            @input="scheduleSave"
          />

          <div class="editor-meta-bar">
            <span class="editor-meta-item">
              <Icon name="calendar" :size="13" />
              {{ updatedLabel }}
            </span>
            <span class="editor-meta-item">
              <Icon name="folder" :size="13" />
              {{ categoryName }}
            </span>
            <span class="editor-meta-item">
              <Icon name="file-text" :size="13" />
              {{ wordCount }} 字
            </span>
          </div>

          <div class="tags-row">
            <Icon name="tag" :size="14" class="tags-icon" />
            <input
              v-model="tagsStr"
              class="tags-input"
              placeholder="标签，用逗号分隔"
              @input="scheduleSave"
            />
          </div>

          <div class="vditor-wrap">
            <div ref="vditorRef" class="vditor-host" />
            <div v-if="!vditorReady" class="vditor-loading">编辑器加载中…</div>
          </div>
        </div>

        <NoteAiDrawer
          v-model:visible="aiVisible"
          :note-id="note.note_id"
          :note-title="title || note.note_title || '无标题'"
          @note-changed="onAiNoteChanged"
        />
      </div>

      <NoteHistoryDrawer
        v-model:visible="historyVisible"
        :note-id="note.note_id"
        :current-content="note.note_content"
        :current-title="note.note_title"
        @rolled-back="onRolledBack"
      />
    </template>
  </div>
</template>

<style scoped>
.editor {
  flex: 1;
  background: var(--bg-main);
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.editor-workspace {
  flex: 1;
  display: flex;
  flex-direction: row;
  min-height: 0;
  overflow: hidden;
  /* Breathing room between the toolbar and the note body. */
  padding-top: 80px;
}
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  gap: 12px;
}
.empty-state svg {
  opacity: 0.4;
}
.empty-state p {
  font-size: 14px;
}
.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border);
  gap: 12px;
}
.toolbar-group {
  display: flex;
  align-items: center;
  gap: 4px;
}
.editor-mode-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  padding: 5px 12px;
  background: var(--accent-light);
  border-radius: 6px;
}
.toolbar-btn {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  color: var(--text-tertiary);
  transition: all 0.15s;
}
.toolbar-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.toolbar-btn.active {
  color: var(--accent);
  background: var(--accent-light);
}
.save-status {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-right: 4px;
  min-width: 48px;
  text-align: right;
}
.editor-body {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  /* Allow flex children (vditor-wrap) to shrink so vditor can fill height
     instead of being squeezed to its min-height. */
  min-height: 0;
}
.editor-title-input {
  width: 100%;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  background: transparent;
  border: none;
  border-bottom: 1px solid transparent;
  border-radius: 0;
  padding: 0 0 8px;
  margin-bottom: 12px;
  letter-spacing: -0.5px;
}
.editor-title-input:focus {
  box-shadow: none;
  border-bottom-color: var(--accent);
}
.editor-meta-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--text-tertiary);
  flex-wrap: wrap;
}
.editor-meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.tags-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
.tags-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}
.tags-input {
  flex: 1;
  height: 32px;
  padding: 0 10px;
  font-size: 13px;
}
.vditor-wrap {
  position: relative;
  flex: 1;
  min-height: 360px;
  display: flex;
}
.vditor-host {
  width: 100%;
  /* Host must have an explicit height so vditor's height:100% fills it. */
  flex: 1;
  min-height: 0;
}
.vditor-host :deep(.vditor) {
  border-radius: var(--radius);
  border: 1px solid var(--border);
  height: 100%;
}
/* Vditor's dark theme CSS applies its own text colors for the editor area,
   but some content falls through to inherited colors — ensure base readability. */
[data-theme="dark"] .vditor-host :deep(.vditor) {
  color-scheme: dark;
}
[data-theme="dark"] .vditor-host :deep(.vditor-ir) {
  color: var(--text-primary);
}
.vditor-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  font-size: 13px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.editor-mode-label.mode-edit {
  background: var(--accent);
  color: #fff;
}
.primary-btn {
  width: auto;
  padding: 0 12px;
  gap: 5px;
  color: var(--accent);
  font-size: 13px;
  font-weight: 500;
}
.primary-btn:hover {
  background: var(--accent);
  color: #fff;
}
.btn-text {
  line-height: 1;
}
/* ---- Preview mode ---- */
.preview-body {
  /* Center the article (title/meta/tags/body) in a comfortable reading column
     instead of spanning the full editor width — matches the framed feel of
     edit mode and keeps line lengths readable on wide screens. */
  align-items: center;
}
.preview-body > * {
  width: 100%;
  max-width: var(--reading-width);
}
.preview-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
  margin: 0 0 12px;
  word-break: break-word;
}
.preview-tags {
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.tag-chip {
  font-size: 12px;
  color: var(--text-accent);
  background: var(--accent-light);
  padding: 3px 10px;
  border-radius: 12px;
}
.preview-content-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 0 24px;
}
.preview-content {
  /* Vditor.preview injects its own content styles (.vditor-preview) here. */
  min-height: 100%;
}
.preview-content :deep(.vditor-preview) {
  background: transparent;
}
/* Ensure readable text contrast in dark mode — Vditor's content theme
   (mode: 'dark') sets many but not all text colors; this catches the rest. */
[data-theme="dark"] .preview-content :deep(.vditor-preview) {
  color: var(--text-primary);
}
.preview-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-tertiary);
}
.preview-empty svg {
  opacity: 0.35;
}
.preview-empty p {
  font-size: 14px;
}
</style>
