<script setup lang="ts">
import { ref, watch } from 'vue'
import type { RecordAction } from '../api/lifecycle.models'

const props = withDefaults(defineProps<{ actions: RecordAction[]; testIdPrefix?: string }>(), { testIdPrefix: 'master-action' })
const emit = defineEmits<{ action: [action: RecordAction] }>()
const labels: Record<RecordAction, string> = {
  view: '查看', edit: '编辑', delete: '删除', submit: '提交',
  approve: '审批', verify: '核验', confirm: '确认', correct: '更正', reverse: '冲销',
  depreciate: '计提折旧',
  dispatch: '发出', receive: '接收', cancel: '取消', handle: '处理',
  archive: '归档',
}
// 防双击重复触发：一次点击后短暂锁定所有按钮，等待父级打开弹窗或发起请求
const locked = ref<RecordAction | null>(null)
// 服务端返回新的 allowed_actions（记录已被替换）时立即解锁
watch(() => props.actions, () => { locked.value = null })
function run(action: RecordAction) {
  if (locked.value) return
  locked.value = action
  emit('action', action)
  setTimeout(() => { if (locked.value === action) locked.value = null }, 600)
}
</script>

<template>
  <div class="table-actions">
    <button v-for="action in actions" :key="action" class="table-action-btn" :class="{ 'table-action-btn--danger': action === 'delete' }" type="button" :disabled="locked !== null" :aria-busy="locked === action" :data-testid="`${testIdPrefix}-${action}`" @click="run(action)">{{ locked === action ? '处理中…' : labels[action] }}</button>
  </div>
</template>

<style scoped>
.table-action-btn--danger { color: #c25450; }
.table-action-btn:disabled { opacity: .55; cursor: default; }
</style>
