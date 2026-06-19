<script setup lang="ts">
/**
 * MarkdownView — renders Markdown into a container using Vditor's static
 * preview renderer (same engine as NoteEditor's preview mode).
 *
 * Modes:
 *  - ``plain``: always show raw text with pre-wrap (for user messages — avoids
 *    Markdown misinterpreting casual input and preserves typed line breaks).
 *  - Markdown (default): while ``streaming`` is true, set the raw text directly
 *    (instant, no async render cost, no flicker); when streaming stops, render
 *    the full Markdown once. Gives live token-by-token feedback during
 *    generation and proper formatting (headings, lists, code, images) after.
 */
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useTheme } from '@/composables/useTheme'

const props = withDefaults(
  defineProps<{ content: string; streaming?: boolean; plain?: boolean }>(),
  { streaming: false, plain: false },
)

const el = ref<HTMLDivElement | null>(null)
const { theme } = useTheme()

// Guards against a stale async Vditor.preview landing after the content/theme
// changed (same token pattern NoteEditor uses for preview switches).
let token = 0
let raf: number | undefined

async function render() {
  if (!el.value) return
  const t = ++token
  const VditorCtor = (await import('vditor')).default
  if (t !== token || !el.value) return
  await VditorCtor.preview(el.value, props.content, {
    mode: theme.value === 'dark' ? 'dark' : 'light',
    cdn: `${import.meta.env.BASE_URL}vditor`,
    lang: 'zh_CN',
    icon: 'ant',
    hljs: { lineNumber: true, style: theme.value === 'dark' ? 'github-dark' : 'github' },
    anchor: 0,
  })
}

function syncRawText() {
  if (el.value) el.value.textContent = props.content
}

// Whether to show raw pre-wrapped text right now (plain mode, or mid-stream).
const showRaw = () => props.plain || props.streaming

// Content changed:
//  - raw (plain or streaming) → sync text immediately.
//  - finalized Markdown → render (debounced one frame so a burst of edits
//    doesn't trigger repeated async renders).
watch(
  () => props.content,
  () => {
    if (showRaw()) {
      syncRawText()
      return
    }
    if (raf) cancelAnimationFrame(raf)
    raf = requestAnimationFrame(() => void render())
  },
)

// Streaming just ended → render the final Markdown.
watch(
  () => props.streaming,
  (s) => {
    if (!s && !props.plain) {
      if (raf) cancelAnimationFrame(raf)
      void render()
    }
  },
)

// Re-render on theme change (only for finalized Markdown).
watch(theme, () => {
  if (!showRaw()) void render()
})

onMounted(() => {
  if (showRaw()) syncRawText()
  else void render()
})

onBeforeUnmount(() => {
  token += 1
  if (raf) cancelAnimationFrame(raf)
})
</script>

<template>
  <div ref="el" class="md-view" :class="{ 'is-raw': plain || streaming }" />
</template>

<style scoped>
.md-view {
  /* Vditor.preview injects .vditor-preview styles into this container. */
  min-width: 0;
}
/* Raw text (user messages + live streaming) — preserve line breaks. */
.md-view.is-raw {
  white-space: pre-wrap;
  word-break: break-word;
}
.md-view :deep(.vditor-preview) {
  background: transparent;
  padding: 0;
}
[data-theme="dark"] .md-view :deep(.vditor-preview) {
  color: var(--text-primary);
}
.md-view :deep(.vditor-preview p) {
  margin: 0 0 8px;
  line-height: 1.65;
}
.md-view :deep(.vditor-preview p:last-child) {
  margin-bottom: 0;
}
.md-view :deep(.vditor-preview code) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 0.9em;
}
.md-view :deep(.vditor-preview pre) {
  margin: 8px 0;
}
.md-view :deep(.vditor-preview ul),
.md-view :deep(.vditor-preview ol) {
  padding-left: 20px;
  margin: 0 0 8px;
}
.md-view :deep(.vditor-preview h1),
.md-view :deep(.vditor-preview h2),
.md-view :deep(.vditor-preview h3) {
  margin: 12px 0 6px;
}
.md-view :deep(.vditor-preview img) {
  max-width: 100%;
  border-radius: 6px;
}
</style>
