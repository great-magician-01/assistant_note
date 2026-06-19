import { ref, readonly } from 'vue'

export type ToastType = 'success' | 'error' | 'info'
export interface ToastItem {
  id: number
  type: ToastType
  message: string
}

const items = ref<ToastItem[]>([])
let counter = 0

function push(type: ToastType, message: string, duration = 3000) {
  const id = ++counter
  items.value.push({ id, type, message })
  if (duration > 0) {
    window.setTimeout(() => dismiss(id), duration)
  }
}

function dismiss(id: number) {
  const idx = items.value.findIndex((t) => t.id === id)
  if (idx >= 0) items.value.splice(idx, 1)
}

export function useToast() {
  return {
    items: readonly(items),
    success: (m: string, d?: number) => push('success', m, d),
    error: (m: string, d?: number) => push('error', m, d ?? 4500),
    info: (m: string, d?: number) => push('info', m, d),
    dismiss,
  }
}
