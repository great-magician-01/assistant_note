import { ref } from 'vue'

type Theme = 'light' | 'dark'

const STORAGE_KEY = 'ain_theme'
const theme = ref<Theme>('light')
let initialized = false

function apply(value: Theme) {
  document.documentElement.setAttribute('data-theme', value)
  localStorage.setItem(STORAGE_KEY, value)
  theme.value = value
}

/** Initialize theme once on app start: stored pref → system pref → light. */
export function initTheme() {
  if (initialized) return
  initialized = true
  const stored = localStorage.getItem(STORAGE_KEY) as Theme | null
  if (stored === 'light' || stored === 'dark') {
    apply(stored)
    return
  }
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  apply(prefersDark ? 'dark' : 'light')
}

export function useTheme() {
  const toggle = () => apply(theme.value === 'dark' ? 'light' : 'dark')
  return { theme, toggle }
}
