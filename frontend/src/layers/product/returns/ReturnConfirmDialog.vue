<script setup lang="ts">
import { ref } from 'vue'
import { ApiError, submitErrorText } from '../../common/api/errors'
import type { ReturnMode, ReturnRow } from './returnModel'

export type ReturnConfirmAction = 'delete' | 'submit' | 'verify' | 'cancel'

const props = defineProps<{
  mode: ReturnMode
  action: ReturnConfirmAction
  row: ReturnRow
  /** 执行动作；缺原因时抛错由本组件展示，避免无谓请求 */
  run: (action: ReturnConfirmAction, row: ReturnRow, reason: string) => Promise<void>
}>()
const emit = defineEmits<{ close: [] }>()

const cancellationReason = ref('')
const submitting = ref(false)
const dialogError = ref('')

const titles: Record<ReturnConfirmAction, string> = {
  submit: '提交退货核验', verify: '核验退货并冲减账目', cancel: '取消退货单', delete: '删除退货草稿',
}
const hints: Record<ReturnConfirmAction, string> = {
  verify: '核验会按退货数量回退库存流水并冲减应付/应收，核验后记录只读且不可修改。',
  submit: '提交后由核验人处理，经办人与核验人必须分离。',
  cancel: '取消必须填写原因，仅待核验记录可以取消。',
  delete: '仅未提交的退货草稿可以删除。',
}

async function confirm() {
  if (submitting.value) return
  submitting.value = true
  dialogError.value = ''
  try {
    if (props.action === 'cancel' && !cancellationReason.value.trim()) throw new Error('取消退货必须填写原因')
    await props.run(props.action, props.row, cancellationReason.value.trim())
    emit('close')
  } catch (error) {
    dialogError.value = error instanceof ApiError ? submitErrorText(error, error.message) : error instanceof Error ? error.message : '退货操作失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-overlay" role="dialog" aria-modal="true" aria-label="退货操作确认">
      <div class="modal-panel" style="width:min(520px,100%)">
        <div class="modal-panel__head">
          <div><p class="section-label">Confirm</p><h2>{{ titles[action] }}</h2></div>
          <button class="modal-close" type="button" aria-label="关闭" @click="emit('close')">×</button>
        </div>
        <p class="section-subtitle">{{ hints[action] }}</p>
        <label v-if="action === 'cancel'" class="modal-field" for="return-cancellation-reason">
          <span>取消原因 *</span>
          <textarea id="return-cancellation-reason" v-model="cancellationReason" rows="3" class="filter-input" style="width:100%;resize:vertical" />
        </label>
        <p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p>
        <div class="modal-panel__foot">
          <button class="ghost-action" type="button" @click="emit('close')">返回</button>
          <button class="primary-action" type="button" data-testid="return-confirm" :disabled="submitting" :aria-busy="submitting" @click="confirm">{{ submitting ? '处理中…' : '确认' }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
