<script setup lang="ts">
// 浅色卡片式多选组件：替代原生 select multiple（原生选中态为深蓝，与浅色主题冲突且看不清选中项）
export interface CheckOption { id: number; label: string; hint?: string }

const props = defineProps<{
  modelValue: number[]
  options: CheckOption[]
  name: string
}>()

const emit = defineEmits<{ (event: 'update:modelValue', value: number[]): void }>()

function toggle(id: number) {
  const next = props.modelValue.includes(id) ? props.modelValue.filter((item) => item !== id) : [...props.modelValue, id]
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="choice-grid" role="group" :aria-label="name">
    <button
      v-for="option in options"
      :key="option.id"
      type="button"
      class="choice-chip"
      :class="{ 'choice-chip--on': modelValue.includes(option.id) }"
      :aria-pressed="modelValue.includes(option.id)"
      @click="toggle(option.id)"
    >
      <span class="choice-chip__check" aria-hidden="true">{{ modelValue.includes(option.id) ? '✓' : '' }}</span>
      <span class="choice-chip__body">
        <strong>{{ option.label }}</strong>
        <small v-if="option.hint">{{ option.hint }}</small>
      </span>
    </button>
  </div>
</template>
