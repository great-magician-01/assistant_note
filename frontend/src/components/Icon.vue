<script setup lang="ts">
/**
 * Icon — renders an SVG from `src/assets/icons/<name>.svg`.
 *
 * Icons live as standalone .svg files (feather-style: 24×24, stroke
 * currentColor, fill none) rather than inline path strings, so they can be
 * opened/edited individually and reused outside the component.
 *
 * Vite's `import.meta.glob('...?raw')` inlines each file's source as a string
 * at build time; we render it via v-html inside a sized span. The inner svg
 * scales to fill the span, and inherits `currentColor` + a CSS stroke-width.
 */
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    name: string
    size?: number | string
    strokeWidth?: number | string
  }>(),
  { size: 16, strokeWidth: 2 },
)

// Eagerly import every icon file as a raw string, keyed by filename (no ext).
const modules = import.meta.glob('../assets/icons/*.svg', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const ICONS: Record<string, string> = {}
for (const [path, raw] of Object.entries(modules)) {
  const name = path.split('/').pop()!.replace(/\.svg$/, '')
  ICONS[name] = raw
}

const raw = computed(() => ICONS[props.name] ?? ICONS['file-text'])

const dim = computed(() =>
  typeof props.size === 'number' ? `${props.size}px` : props.size,
)
const sw = computed(() => String(props.strokeWidth))
</script>

<template>
  <span
    class="icon"
    :style="{ width: dim, height: dim, '--icon-stroke': sw } as Record<string, string>"
    v-html="raw"
  />
</template>

<style scoped>
.icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
  color: inherit;
}
.icon :deep(svg) {
  width: 100%;
  height: 100%;
  display: block;
  /* Overrides the file's stroke-width attribute via an author rule, while
     the file keeps a sane default when opened standalone. */
  stroke-width: var(--icon-stroke, 2);
}
</style>
