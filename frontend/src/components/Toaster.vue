<script setup lang="ts">
import { useToast } from '@/composables/useToast'

const toast = useToast()
</script>

<template>
  <Teleport to="body">
    <div class="toaster">
      <transition-group name="toast">
        <div
          v-for="t in toast.items.value"
          :key="t.id"
          class="toast"
          :class="t.type"
          @click="toast.dismiss(t.id)"
        >
          <span class="dot" />
          <span class="msg">{{ t.message }}</span>
        </div>
      </transition-group>
    </div>
  </Teleport>
</template>

<style scoped>
.toaster {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}
.toast {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 13px;
  background: var(--bg-main);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-lg);
  color: var(--text-primary);
  max-width: min(460px, calc(100vw - 32px));
  cursor: pointer;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.toast.success .dot {
  background: #16a34a;
}
.toast.error .dot {
  background: var(--danger);
}
.toast.info .dot {
  background: var(--accent);
}
.toast-enter-active,
.toast-leave-active {
  transition: all 0.25s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
