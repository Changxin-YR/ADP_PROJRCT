<script setup lang="ts">
defineProps<{ id: string; label: string; hint?: string; error?: string }>()
</script>

<template>
  <div class="form-field" :class="{ 'has-error': Boolean(error) }">
    <label class="field-label" :for="id">{{ label }}</label>
    <div class="field-control" :aria-invalid="Boolean(error)" :aria-describedby="error ? `${id}-error` : hint ? `${id}-hint` : undefined"><slot /></div>
    <p v-if="hint && !error" :id="`${id}-hint`" class="field-hint">{{ hint }}</p>
    <p v-if="error" :id="`${id}-error`" class="field-error" role="alert">{{ error }}</p>
  </div>
</template>
