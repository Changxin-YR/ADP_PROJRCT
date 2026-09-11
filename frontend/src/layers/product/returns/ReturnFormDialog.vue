<script setup lang="ts">
/**
 * 退货单登记弹窗（供应商退货 / 客户退货）。
 *
 * 字段契约以 backend/layers/features/returns/return_store.py::create_return 为准：
 * - 采购退货请求体：code,name,source_receipt_id,quantity,reason + 由来源入库单自动带出的
 *   warehouse_id,material_id,inventory_lot_id（后端会把这三项与来源逐项比对，不一致即
 *   RETURN_SOURCE_INVALID，所以不给用户手填的输入框）；
 * - 销售退货请求体：code,name,source_delivery_id,quantity,refund_amount,reason；
 * - amount / payable_id / receivable_id 由后端从来源单据与单价计算，前端不提交。
 */
import { computed, reactive, ref, watch } from 'vue'
import { ApiError, submitErrorText } from '../../common/api/errors'
import { createPurchaseReturn } from '../../features/purchase/purchase.service'
import { createSalesReturn } from '../../features/sales/sales.service'
import { clearOfflineDraft, loadOfflineDraft, saveOfflineDraft } from '../../common/ui/offlineDraft'
import { numberOr, sourceHintOf, type ReturnFormField, type ReturnMode, type ReturnRow, type SourceDoc } from './returnModel'

const props = defineProps<{
  mode: ReturnMode
  sources: SourceDoc[]
  sourceOptions: Array<{ value: number; label: string }>
  /** 取所选来源单据；采购退货据此带出后端强校验的 warehouse_id/material_id/inventory_lot_id */
  pickSource: (form: Record<string, unknown>) => SourceDoc | null
}>()
const emit = defineEmits<{ close: []; saved: [row: ReturnRow] }>()

const form = reactive<Record<string, string | number>>({})
const submitting = ref(false)
const dialogError = ref('')
const draftNotice = ref('')
const draftScope = computed(() => `returns:${props.mode}`)
/** 提示随所选来源单据实时变化（必须在弹窗内计算，外壳拿不到表单状态） */
const hint = computed(() => sourceHintOf(props.pickSource(form), props.mode))

const fields = computed<ReturnFormField[]>(() => props.mode === 'purchase'
  ? [
      { key: 'code', label: '退货单号', required: true }, { key: 'name', label: '退货名称', required: true },
      { key: 'source_receipt_id', label: '来源入库单（已核验）', type: 'select', required: true, options: props.sourceOptions },
      { key: 'quantity', label: '退货数量', type: 'number', required: true },
      { key: 'reason', label: '退货原因', type: 'textarea', required: true },
    ]
  : [
      { key: 'code', label: '退货单号', required: true }, { key: 'name', label: '退货名称', required: true },
      { key: 'source_delivery_id', label: '来源交付单（已核验）', type: 'select', required: true, options: props.sourceOptions },
      { key: 'quantity', label: '退货数量', type: 'number', required: true },
      { key: 'refund_amount', label: '退款金额', type: 'number', required: true },
      { key: 'reason', label: '退货原因', type: 'textarea', required: true },
    ])

function reset() {
  for (const key of Object.keys(form)) delete form[key]
  for (const field of fields.value) form[field.key] = ''
  dialogError.value = ''
  draftNotice.value = ''
  const draft = loadOfflineDraft<Record<string, string | number>>(draftScope.value)
  if (draft) {
    Object.assign(form, draft.payload)
    draftNotice.value = '已恢复本地草稿，保存后将清除本地副本。'
  }
}
reset()
watch(() => props.mode, reset)

/** 只发送后端 create_return 真正读取的字段（amount/payable_id/receivable_id 由后端算） */
function body(): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const field of fields.value) {
    const value = form[field.key]
    if (field.required && !String(value ?? '').trim()) throw new Error(`请填写${field.label}`)
    if (value === '' || value === undefined || value === null) continue
    payload[field.key] = ['number', 'select'].includes(field.type ?? '') ? Number(value) : String(value).trim()
  }
  if (props.mode === 'purchase') {
    const receipt = props.pickSource(form)
    if (!receipt || !receipt.warehouse_id || !receipt.material_id || !receipt.inventory_lot_id) {
      throw new Error('所选入库单缺少仓库、物料或批次信息，无法登记退货，请确认入库单已核验')
    }
    payload.warehouse_id = numberOr(receipt.warehouse_id)
    payload.material_id = numberOr(receipt.material_id)
    payload.inventory_lot_id = numberOr(receipt.inventory_lot_id)
  }
  if (props.mode === 'purchase' && !payload.source_receipt_id) throw new Error('请选择来源入库单')
  if (props.mode === 'sales' && !payload.source_delivery_id) throw new Error('请选择来源交付单')
  if (Number(payload.quantity) <= 0) throw new Error('退货数量必须大于零')
  return payload
}

async function save() {
  if (submitting.value) return
  submitting.value = true
  dialogError.value = ''
  try {
    const payload = body()
    const result = props.mode === 'purchase' ? await createPurchaseReturn(payload) : await createSalesReturn(payload)
    clearOfflineDraft(draftScope.value)
    emit('saved', result.record as unknown as ReturnRow)
  } catch (error) {
    dialogError.value = error instanceof ApiError ? submitErrorText(error, error.message) : error instanceof Error ? error.message : '退货单保存失败'
  } finally {
    submitting.value = false
  }
}

function discardDraft() {
  clearOfflineDraft(draftScope.value)
  draftNotice.value = ''
  emit('close')
}

// 离线草稿：未提交内容随输入落本地，断网/关页后重进可恢复（与 PurchasePage 一致）
watch(form, (value) => {
  if (Object.values(value).some((item) => String(item ?? '').trim())) saveOfflineDraft(draftScope.value, { ...value })
}, { deep: true })
</script>

<template>
  <Teleport to="body">
    <p v-if="draftNotice" class="offline-draft-notice" role="status">
      {{ draftNotice }} <button type="button" data-testid="return-discard-draft" @click="discardDraft">丢弃本地草稿</button>
    </p>
    <div class="modal-overlay" role="dialog" aria-modal="true" :aria-label="mode === 'purchase' ? '供应商退货登记' : '客户退货登记'">
      <div class="modal-panel">
        <div class="modal-panel__head">
          <div><p class="section-label">Create</p><h2>{{ mode === 'purchase' ? '登记供应商退货' : '登记客户退货' }}</h2></div>
          <button class="modal-close" type="button" aria-label="关闭" @click="emit('close')">×</button>
        </div>
        <p class="section-subtitle">必须关联已核验来源单据；退货金额由后端按来源单价与退货数量计算，核验后才冲减账目。</p>
        <div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))">
          <label v-for="field in fields" :key="field.key" class="modal-field" :for="`return-${field.key}`"
            :style="field.type === 'textarea' ? 'grid-column:1/-1' : ''">
            <span>{{ field.label }}{{ field.required ? ' *' : '' }}</span>
            <textarea v-if="field.type === 'textarea'" :id="`return-${field.key}`" v-model="form[field.key]" rows="3" class="filter-input" style="width:100%;resize:vertical" />
            <select v-else-if="field.type === 'select'" :id="`return-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%">
              <option value="" disabled>请选择{{ field.label }}</option>
              <option v-for="item in field.options" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
            <input v-else :id="`return-${field.key}`" v-model="form[field.key]" :type="field.type ?? 'text'"
              :min="field.type === 'number' ? 0 : undefined" :step="field.type === 'number' ? '0.001' : undefined" class="filter-input" style="width:100%">
          </label>
        </div>
        <p v-if="hint" class="section-subtitle" data-testid="return-source-hint">{{ hint }}</p>
        <p class="section-subtitle">来源单据下拉只列出「已核验」单据，无法手填 ID。</p>
        <p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p>
        <div class="modal-panel__foot">
          <button class="ghost-action" type="button" @click="emit('close')">取消</button>
          <button class="primary-action" type="button" data-testid="return-save" :disabled="submitting" :aria-busy="submitting" @click="save">{{ submitting ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
