<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { downloadAttachment, getAttachments, type Attachment } from '../../features/data-exchange/data-exchange.service'

const props = defineProps<{ entityType: string; entityId: number; refreshKey?: number; selectable?: boolean }>()
const emit = defineEmits<{ select: [id: number] }>()
const rows = ref<Attachment[]>([])
const error = ref('')
async function load() {
  try { rows.value = (await getAttachments(props.entityType, props.entityId)).items; error.value = '' }
  catch { error.value = '附件加载失败' }
}
onMounted(load)
watch(() => props.refreshKey, load)
defineExpose({ load })
</script>

<template>
  <div class="attachment-list"><p v-if="error" class="form-error" role="alert">{{ error }}</p><p v-if="!rows.length" class="section-subtitle">暂无附件</p><button v-for="row in rows" :key="row.id" class="table-action-btn" type="button" @click="props.selectable ? emit('select', row.id) : downloadAttachment(row.id, row.original_name)">{{ props.selectable ? '选择 ' : '' }}{{ row.original_name }} · {{ Math.ceil(row.size_bytes / 1024) }} KB</button></div>
</template>
