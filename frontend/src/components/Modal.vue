<script setup lang="ts">
import Icon from '@/components/Icon.vue'

defineProps<{
  title: string
  width?: string
}>()

const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <Teleport to="body">
    <div class="modal-overlay p-3 md:p-5" @click.self="emit('close')">
      <div class="modal" :style="{ maxWidth: width ?? '420px' }">
        <div class="modal-header">
          <span class="modal-title">{{ title }}</span>
          <button class="btn-icon" @click="emit('close')">
            <Icon name="plus" :size="16" style="transform: rotate(45deg)" />
          </button>
        </div>
        <div class="modal-body">
          <slot />
        </div>
        <div v-if="$slots.footer" class="modal-footer">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fade 0.15s ease;
}
@keyframes fade {
  from {
    opacity: 0;
  }
}
.modal {
  width: 100%;
  background: var(--bg-main);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  overflow: hidden;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}
.modal-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}
.modal-body {
  padding: 18px;
  overflow-y: auto;
}
.modal-footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--border);
}
</style>
