<script setup lang="ts">
defineProps<{ label: string; tone?: 'teal' | 'blue' | 'amber' | 'slate' | 'rose' }>()
</script>

<template><span class="status-badge" :class="`status-badge--${tone ?? 'slate'}`"><i />{{ label }}</span></template>
