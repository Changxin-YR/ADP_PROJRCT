<script setup lang="ts">
import { computed, useSlots } from 'vue'
import type { VNode } from 'vue'

import AppIcon from './AppIcon.vue'

const props = withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'quiet' | 'danger'
  icon?: string
  loading?: boolean
  disabled?: boolean
  compact?: boolean
  label?: string
  type?: 'button' | 'submit' | 'reset'
}>(), {
  variant: 'secondary',
  loading: false,
  disabled: false,
  compact: false,
  type: 'button',
})

const slots = useSlots()
const slotLabel = computed(() => (slots.default?.({}) ?? [])
  .map((node: VNode) => typeof node.children === 'string' ? node.children : '')
  .join('')
  .trim())
const accessibleLabel = computed(() => props.label || slotLabel.value || undefined)
const iconOnly = computed(() => !slotLabel.value)
</script>

<template>
  <button
    :type="type"
    class="action-button"
    :class="[
      `action-button--${variant}`,
      { 'action-button--compact': compact, 'action-button--icon-only': iconOnly },
    ]"
    :disabled="disabled || loading"
    :aria-label="accessibleLabel"
    :aria-busy="loading ? 'true' : undefined"
  >
    <span v-if="loading" class="action-button__spinner" aria-hidden="true" />
    <AppIcon v-else-if="icon" :name="icon" :size="compact ? 15 : 17" />
    <span v-if="loading">处理中…</span>
    <span v-else-if="$slots.default" class="action-button__label"><slot /></span>
  </button>
</template>

<style scoped>
.action-button{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:var(--wb-action-height,40px);padding:0 16px;border:1px solid transparent;border-radius:var(--wb-action-radius,10px);font:inherit;font-size:14px;font-weight:750;line-height:1;white-space:nowrap;cursor:pointer;transition:background-color .16s,border-color .16s,color .16s,box-shadow .16s,transform .16s}.action-button:hover:not(:disabled){transform:translateY(-1px)}.action-button:focus-visible{outline:0;box-shadow:var(--wb-focus-ring,0 0 0 3px rgba(79,159,145,.22))}.action-button:disabled{opacity:.55;cursor:not-allowed;transform:none}.action-button--primary{color:#fff;background:var(--wb-teal);box-shadow:0 5px 12px rgba(47,126,115,.14)}.action-button--primary:hover:not(:disabled){background:#438f82}.action-button--secondary{border-color:var(--wb-line);color:#45645f;background:#fff}.action-button--secondary:hover:not(:disabled){border-color:#a9d3cb;color:var(--wb-navy);background:#f8fcfb}.action-button--quiet{color:#607a75;background:transparent}.action-button--quiet:hover:not(:disabled){color:var(--wb-navy);background:#edf7f4}.action-button--danger{border-color:#edcfcd;color:#b94d49;background:#fff8f7}.action-button--danger:hover:not(:disabled){border-color:#dea8a5;background:#fff1ef}.action-button--compact{min-height:var(--wb-action-compact-height,34px);padding:0 12px;font-size:13px}.action-button--icon-only{width:var(--wb-action-height,40px);padding:0}.action-button--compact.action-button--icon-only{width:var(--wb-action-compact-height,34px);padding:0}.action-button__spinner{width:15px;height:15px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:action-button-spin .7s linear infinite}@keyframes action-button-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.action-button,.action-button__spinner{transition:none;animation:none}}
</style>
