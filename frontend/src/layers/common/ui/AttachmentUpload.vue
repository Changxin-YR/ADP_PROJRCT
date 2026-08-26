<script setup lang="ts">
import { ref } from 'vue'
import { uploadAttachment, type Attachment } from '../../features/data-exchange/data-exchange.service'

const props = defineProps<{ organizationId: number; entityType: string; entityId: number }>()
const emit = defineEmits<{ uploaded: [attachment: Attachment] }>()
const busy = ref(false)
const error = ref('')
async function choose(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  busy.value = true; error.value = ''
  try { emit('uploaded', (await uploadAttachment(props.organizationId, props.entityType, props.entityId, file)).attachment); input.value = '' }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '附件上传失败' }
  finally { busy.value = false }
}
</script>

<template>
  <div class="attachment-upload"><label class="ghost-action"><input type="file" accept=".pdf,.xlsx,image/png,image/jpeg" :disabled="busy" style="display:none" @change="choose">{{ busy ? '上传中…' : '上传附件' }}</label><span v-if="error" class="form-error" role="alert">{{ error }}</span></div>
</template>
