import { ref } from 'vue'
import type { CategoryTreeNode, SnowflakeId } from '@/types'

/**
 * Pointer-events-based drag & drop for the sidebar tree.
 *
 * We avoid native HTML5 DnD (`draggable`/`dragstart`/`drop`) because it does
 * not fire on touch input and is brittle with custom nested trees. Instead we
 * listen to pointerdown on a source row, arm a pending drag, and only enter
 * "dragging" mode once the pointer moves past a small threshold (so a plain
 * click still selects the note/category normally). Drop targets are marked with
 * `data-drop-cat="<id>"` / `data-drop-root` and found via `elementFromPoint`.
 *
 * State lives at module scope so the recursive `NoteTree` instances and the
 * `AppSidebar` uncategorized list all share one in-flight drag.
 */
export type DragPayload =
  | { type: 'note'; id: SnowflakeId; categoryId: SnowflakeId | null; label: string }
  | { type: 'category'; id: SnowflakeId; label: string }

/** A valid drop location: a category id, or 'root' (uncategorized / top-level). */
export type DropTarget = SnowflakeId | 'root'

const payload = ref<DragPayload | null>(null)
const dragPos = ref<{ x: number; y: number } | null>(null)
const dropTarget = ref<DropTarget | null>(null)

const THRESHOLD = 4
let pending: {
  p: DragPayload
  x: number
  y: number
  forbidden: Set<SnowflakeId>
} | null = null
let active = false
let forbidden = new Set<SnowflakeId>()
let onCommitCb: ((p: DragPayload, t: DropTarget) => void) | null = null

/** Collect a category's own id plus every descendant category id. */
export function collectSubtreeIds(
  nodes: CategoryTreeNode[],
  id: SnowflakeId,
): Set<SnowflakeId> {
  const out = new Set<SnowflakeId>()
  const find = (list: CategoryTreeNode[]): CategoryTreeNode | null => {
    for (const n of list) {
      if (n.category_id === id) return n
      if (n.children?.length) {
        const r = find(n.children)
        if (r) return r
      }
    }
    return null
  }
  const collect = (n: CategoryTreeNode) => {
    out.add(n.category_id)
    n.children?.forEach(collect)
  }
  const node = find(nodes)
  if (node) collect(node)
  return out
}

function isValidTarget(t: DropTarget | null): boolean {
  if (!t || !payload.value) return false
  if (t === 'root') return true
  return !forbidden.has(t)
}

function detectTarget(x: number, y: number): DropTarget | null {
  const el = document.elementFromPoint(x, y) as Element | null
  const hit = el?.closest('[data-drop-cat],[data-drop-root]') as HTMLElement | null
  if (!hit) return null
  if (hit.hasAttribute('data-drop-root')) return 'root'
  const catId = hit.getAttribute('data-drop-cat')
  return catId as DropTarget
}

function onPointerMove(e: PointerEvent) {
  if (!active) {
    if (!pending) return
    if (
      Math.abs(e.clientX - pending.x) <= THRESHOLD &&
      Math.abs(e.clientY - pending.y) <= THRESHOLD
    ) {
      return
    }
    forbidden = pending.forbidden
    payload.value = pending.p
    active = true
    document.body.classList.add('tree-dragging')
  }
  e.preventDefault()
  dragPos.value = { x: e.clientX, y: e.clientY }
  const t = detectTarget(e.clientX, e.clientY)
  dropTarget.value = isValidTarget(t) ? t : null
}

function onPointerUp() {
  document.removeEventListener('pointermove', onPointerMove)
  document.removeEventListener('pointerup', onPointerUp)
  const p = payload.value
  const t = dropTarget.value
  pending = null
  active = false
  payload.value = null
  dragPos.value = null
  dropTarget.value = null
  forbidden = new Set()
  document.body.classList.remove('tree-dragging')
  if (p && t && onCommitCb) onCommitCb(p, t)
}

/**
 * Arm a drag from a pointerdown on a source row. `tree` is the category roots
 * (used to compute the forbidden drop set for category sources — can't drop a
 * category into itself or a descendant).
 */
export function beginDrag(
  p: DragPayload,
  e: PointerEvent,
  tree: CategoryTreeNode[],
) {
  if (e.pointerType === 'mouse' && e.button !== 0) return
  const f = new Set<SnowflakeId>()
  if (p.type === 'category') {
    f.add(p.id)
    collectSubtreeIds(tree, p.id).forEach((id) => f.add(id))
  } else if (p.categoryId) {
    f.add(p.categoryId)
  }
  pending = { p, x: e.clientX, y: e.clientY, forbidden: f }
  document.addEventListener('pointermove', onPointerMove)
  document.addEventListener('pointerup', onPointerUp)
}

/** Register the single commit handler (called once, from AppSidebar). */
export function onCommit(cb: (p: DragPayload, t: DropTarget) => void) {
  onCommitCb = cb
}

export function useTreeDnd() {
  return {
    payload,
    dragPos,
    dropTarget,
    beginDrag,
    onCommit,
    isValidTarget,
    collectSubtreeIds,
  }
}
