<script setup lang="ts">
import { computed } from 'vue'
import AttachmentList from './AttachmentList.vue'
import AttachmentUpload from './AttachmentUpload.vue'

const props = defineProps<{ modelValue: string; organizationId: number; entityType: string; entityId: number; refreshKey?: number; inputId?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const effectiveRefresh = computed(() => props.refreshKey ?? 0)
function addEvidenceId(id: number) {
  const ids = props.modelValue.split(',').map((item) => item.trim()).filter(Boolean)
  ids.push(String(id))
  emit('update:modelValue', ids.join(','))
}
</script>

<template>
  <div class="evidence-picker modal-row" style="grid-template-columns:1fr">
    <label class="modal-field"><span>凭据附件 ID *</span>
      <input class="filter-input" style="width:100%" :id="inputId" :value="modelValue" placeholder="上传或选择附件后自动回填，多个 ID 用英文逗号分隔" @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)">
    </label>
    <div class="modal-field"><span>上传凭据</span>
      <AttachmentUpload :organization-id="organizationId" :entity-type="entityType" :entity-id="entityId" @uploaded="(attachment) => addEvidenceId(attachment.id)" />
    </div>
    <div class="modal-field"><span>已有凭据</span>
      <AttachmentList :entity-type="entityType" :entity-id="entityId" :refresh-key="effectiveRefresh" selectable @select="addEvidenceId" />
    </div>
  </div>
</template>
