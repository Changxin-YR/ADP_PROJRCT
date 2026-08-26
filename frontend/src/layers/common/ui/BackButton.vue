<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = withDefaults(defineProps<{ fallback?: string }>(), { fallback: '/workbench' })
const router = useRouter()

async function goBack() {
  const previous = router.options.history.state.back
  if (typeof previous === 'string' && !previous.startsWith('/auth/login')) {
    await router.back()
    return
  }
  await router.push(props.fallback)
}
</script>

<template>
  <button class="back-button" type="button" aria-label="返回上一步" @click="goBack">
    <span aria-hidden="true">←</span>
    返回上一步
  </button>
</template>
