<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { ColumnItem } from '../../common/ui/DataTablePage.vue'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import { submitErrorText, messageWithContext as message } from '../../common/api/errors'
import AttachmentList from '../../common/ui/AttachmentList.vue'
import AttachmentUpload from '../../common/ui/AttachmentUpload.vue'
import { useSubmitGuard } from '../../common/ui/useSubmitGuard'
import type { WarehouseField, WarehouseRecord, WarehouseResource } from '../../common/api/warehouse.models'
import { cancelWarehouseTransfer, createWarehouseCorrection, createWarehouseRecord, deleteWarehouseDraft, dispatchWarehouseTransfer, listWarehouseRecords, receiveWarehouseTransfer, submitWarehouseRecord, updateWarehouseRecord, verifyWarehouseRecord } from '../../features/warehouse/warehouse.service'

const props = withDefaults(defineProps<{
  resource: WarehouseResource; title: string; label: string; description: string; createLabel: string
  fields: WarehouseField[]; columns: ColumnItem[]; evidenceRequired?: boolean; initialValues?: Record<string, string | number>
}>(), { evidenceRequired: false, initialValues: () => ({}) })
const rows = ref<WarehouseRecord[]>([])
const loading = ref(true)
const pageError = ref('')
const dialogError = ref('')
const formOpen = ref(false)
const editing = ref<WarehouseRecord | null>(null)
const correcting = ref<WarehouseRecord | null>(null)
const form = reactive<Record<string, string | number>>({})
const confirmAction = ref<'delete' | 'submit' | 'verify' | 'dispatch' | 'receive' | 'cancel' | null>(null)
const target = ref<WarehouseRecord | null>(null)
const evidenceText = ref('')
const receivedQuantity = ref(0)
const differenceReason = ref('')
const correctionReason = ref('')
const cancellationReason = ref('')
const entityType = computed(() => `warehouse:${props.resource}`)
const attachmentRefreshKey = ref(0)
function onEvidenceUploaded(attachment: { id: number }) { addEvidenceId(attachment.id); attachmentRefreshKey.value += 1 }
function addEvidenceId(id: number) {
  const ids = evidenceText.value.split(',').map((item) => item.trim()).filter(Boolean)
  ids.push(String(id)); evidenceText.value = ids.join(',')
}

const labels: Record<string, string> = { draft: '草稿', submitted: '待核验', in_transit: '在途', verified: '已核验', corrected: '已更正', cancelled: '已取消', archived: '已归档' }
const tones = { 草稿: 'slate', 待核验: 'amber', 在途: 'blue', 已核验: 'teal', 已更正: 'blue', 已取消: 'slate', 已归档: 'slate' } as const
const displayRows = computed(() => rows.value.map((row) => ({ ...row, lifecycle_label: labels[row.status] ?? row.status })))
const tableColumns = computed<ColumnItem[]>(() => [...props.columns, { key: 'lifecycle_label', label: '业务状态', type: 'badge', tones }])
const kpis = computed(() => [
  { label: '记录总数', value: rows.value.length, unit: '张', hint: '当前授权范围' },
  { label: '待核验', value: rows.value.filter((row) => row.status === 'submitted').length, unit: '张', tone: 'amber' as const, hint: '提交后仍可编辑' },
  { label: '正式记录', value: rows.value.filter((row) => row.status === 'verified').length, unit: '张', tone: 'teal' as const, hint: '核验后只读' },
])
async function load() {
  loading.value = true; pageError.value = ''
  try { rows.value = (await listWarehouseRecords(props.resource)).items }
  catch (error) { rows.value = []; pageError.value = message(error, '仓储数据加载失败') }
  finally { loading.value = false }
}
function openForm(row?: WarehouseRecord, correction = false) {
  editing.value = correction ? null : row ?? null; correcting.value = correction ? row ?? null : null; dialogError.value = ''; correctionReason.value = ''
  for (const field of props.fields) form[field.key] = (row?.[field.key] as string | number) ?? props.initialValues[field.key] ?? ''
  formOpen.value = true
}
function body() {
  const payload: Record<string, unknown> = {}
  for (const field of props.fields) {
    const value = form[field.key]
    if (field.required && !String(value ?? '').trim()) throw new Error(`请填写${field.label}`)
    if (value !== '') payload[field.key] = ['number', 'select'].includes(field.type ?? '') ? Number(value) : String(value).trim()
  }
  return payload
}
function replace(row: WarehouseRecord) {
  const index = rows.value.findIndex((item) => item.id === row.id)
  if (index < 0) rows.value.unshift(row); else rows.value[index] = row
}
const { busy: saving, run: runSave } = useSubmitGuard()
async function save() {
  dialogError.value = ''
  await runSave(async () => {
    try {
      const payload = body()
      if (correcting.value) {
        if (!correctionReason.value.trim()) throw new Error('请填写更正原因')
        payload.correction_reason = correctionReason.value.trim()
      }
      const result = correcting.value
        ? await createWarehouseCorrection(props.resource, correcting.value.id, { ...payload, expected_version: correcting.value.version })
        : editing.value
          ? await updateWarehouseRecord(props.resource, editing.value.id, { ...payload, expected_version: editing.value.version })
          : await createWarehouseRecord(props.resource, payload)
      replace(result.record); formOpen.value = false
    } catch (error) { dialogError.value = error instanceof Error ? submitErrorText(error, error.message) : '仓储记录保存失败' }
  })
}
function ask(action: 'delete' | 'submit' | 'verify' | 'dispatch' | 'receive' | 'cancel', row: WarehouseRecord) {
  target.value = row; confirmAction.value = action; evidenceText.value = ''; dialogError.value = ''
  receivedQuantity.value = Number(row.quantity ?? 0); differenceReason.value = ''; cancellationReason.value = ''
}
const { busy: confirming, run: runConfirm } = useSubmitGuard()
async function confirm() {
  if (!target.value || !confirmAction.value) return
  const row = target.value
  const action = confirmAction.value
  if (!row || !action) return
  await runConfirm(async () => {
  try {
    if (action === 'delete') { await deleteWarehouseDraft(props.resource, row.id); rows.value = rows.value.filter((item) => item.id !== row.id) }
    else if (action === 'dispatch') replace((await dispatchWarehouseTransfer(row.id, row.version)).record)
    else if (action === 'receive') replace((await receiveWarehouseTransfer(row.id, row.version, receivedQuantity.value, differenceReason.value.trim() || undefined)).record)
    else if (action === 'cancel') {
      if (!cancellationReason.value.trim()) throw new Error('取消调拨必须填写原因')
      replace((await cancelWarehouseTransfer(row.id, row.version, cancellationReason.value.trim())).record)
    }
    else {
      const evidence = evidenceText.value.split(',').map((item) => Number(item.trim())).filter((item) => Number.isInteger(item) && item > 0)
      if (action === 'verify' && props.evidenceRequired && !evidence.length) throw new Error('核验必须填写凭据附件 ID')
      const result = action === 'submit'
        ? await submitWarehouseRecord(props.resource, row.id, row.version)
        : await verifyWarehouseRecord(props.resource, row.id, row.version, evidence)
      replace(result.record)
    }
    confirmAction.value = null; target.value = null
  } catch (error) { dialogError.value = error instanceof Error ? message(error, error.message) : '操作失败' }
  })
}
function action(name: string, raw: Record<string, unknown>) {
  const row = rows.value.find((item) => item.id === Number(raw.id)); if (!row) return
  if (name === 'edit') openForm(row)
  else if (name === 'correct') openForm(row, true)
  else if (name === 'delete' || name === 'submit' || name === 'verify' || name === 'dispatch' || name === 'receive' || name === 'cancel') ask(name, row)
}
onMounted(load)
</script>

<template>
  <div v-if="pageError" class="page-card table-empty" role="alert">{{ pageError }}<div style="margin-top:12px"><button class="ghost-action" type="button" @click="load">重新加载</button></div></div>
  <DataTablePage v-else :export-resource="resource === 'transfers' ? 'warehouse-transfers' : resource" :title="title" :label="label" :description="description" :create-label="createLabel" :kpis="kpis"
    :filters="[{ key: 'status', type: 'select', label: '全部业务状态', options: Object.entries(labels).map(([value, label]) => ({ value, label })) }, { key: 'name', type: 'search', placeholder: `搜索${title} / 单号`, wide: true }]"
    :columns="tableColumns" :rows="displayRows" action-test-id-prefix="warehouse-action"
    :empty-text="loading ? '正在加载仓储记录…' : '当前授权范围内暂无记录'" @create="openForm()" @action="action" />
  <Teleport to="body">
    <div v-if="formOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="仓储记录编辑"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">{{ correcting ? 'Correction' : editing ? 'Edit' : 'Create' }}</p><h2>{{ correcting ? `更正 · ${title}` : editing ? `编辑 · ${title}` : `新增 · ${title}` }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="formOpen = false">×</button></div><p class="section-subtitle">{{ correcting ? '将创建关联更正单；原核验单据和库存流水保持只读，仅追加差额流水。' : '提交后仍可编辑并保留版本；核验后永久只读，库存只由正式流水汇总。' }}</p><div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))"><label v-for="field in fields" :key="field.key" class="modal-field" :for="`warehouse-${field.key}`" :style="field.type === 'textarea' ? 'grid-column:1/-1' : ''"><span>{{ field.label }}{{ field.required ? ' *' : '' }}</span><textarea v-if="field.type === 'textarea'" :id="`warehouse-${field.key}`" v-model="form[field.key]" rows="3" class="filter-input" style="width:100%;resize:vertical" /><select v-else-if="field.type === 'select'" :id="`warehouse-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%"><option value="" disabled>请选择{{ field.label }}</option><option v-for="item in field.options" :key="item.value" :value="item.value">{{ item.label }}</option></select><input v-else :id="`warehouse-${field.key}`" v-model="form[field.key]" :type="field.type ?? 'text'" :min="field.type === 'number' ? 0 : undefined" class="filter-input" style="width:100%"></label><label v-if="correcting" class="modal-field" for="warehouse-correction-reason" style="grid-column:1/-1"><span>更正原因 *</span><textarea id="warehouse-correction-reason" v-model="correctionReason" rows="3" class="filter-input" style="width:100%;resize:vertical" /></label></div><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="formOpen = false">取消</button><button class="primary-action" type="button" data-testid="warehouse-save" :disabled="saving" :aria-busy="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button></div></div></div>
    <div v-if="confirmAction && target" class="modal-overlay" role="dialog" aria-modal="true" aria-label="仓储操作确认"><div class="modal-panel" style="width:min(500px,100%)"><div class="modal-panel__head"><div><p class="section-label">Confirm</p><h2>{{ confirmAction === 'verify' ? '核验并入账' : confirmAction === 'submit' ? '提交核验' : confirmAction === 'dispatch' ? '确认发出调拨' : confirmAction === 'receive' ? '确认接收调拨' : confirmAction === 'cancel' ? '取消调拨' : '删除草稿' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="confirmAction = null">×</button></div><p class="section-subtitle">{{ confirmAction === 'dispatch' ? '发出后库存从调出仓扣减并进入在途，尚不计入调入仓。' : confirmAction === 'receive' ? '接收后按实际接收量计入调入仓，差异必须留痕。' : confirmAction === 'cancel' ? '在途取消会用追加流水恢复调出仓库存，原发出流水仍永久保留。' : confirmAction === 'verify' ? '核验后单据永久只读，库存影响以追加流水入账。' : confirmAction === 'submit' ? '提交后仍可编辑，待办跟随最新版本。' : '仅无引用、未提交的草稿可以删除。' }}</p><div v-if="confirmAction === 'verify' && evidenceRequired" class="modal-row" style="grid-template-columns:1fr"><label class="modal-field" for="warehouse-evidence"><span>凭据附件 ID *</span><input id="warehouse-evidence" v-model="evidenceText" class="filter-input" style="width:100%" placeholder="上传或选择附件后自动回填，多个 ID 用英文逗号分隔"></label><div class="modal-field"><span>上传凭据</span><AttachmentUpload :organization-id="Number((target as Record<string, unknown>).organization_id ?? 1)" :entity-type="entityType" :entity-id="target.id" @uploaded="onEvidenceUploaded" /></div><div class="modal-field"><span>已有凭据</span><AttachmentList :entity-type="entityType" :entity-id="target.id" :refresh-key="attachmentRefreshKey" selectable @select="addEvidenceId" /></div></div><template v-if="confirmAction === 'receive'"><label class="modal-field" for="warehouse-received-quantity"><span>实际接收数量 *</span><input id="warehouse-received-quantity" v-model.number="receivedQuantity" type="number" min="0" class="filter-input" style="width:100%"></label><label class="modal-field" for="warehouse-difference-reason"><span>接收差异与处理结果</span><textarea id="warehouse-difference-reason" v-model="differenceReason" rows="3" class="filter-input" style="width:100%;resize:vertical" /></label></template><label v-if="confirmAction === 'cancel'" class="modal-field" for="warehouse-cancellation-reason"><span>取消原因 *</span><textarea id="warehouse-cancellation-reason" v-model="cancellationReason" rows="3" class="filter-input" style="width:100%;resize:vertical" /></label><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="confirmAction = null">返回</button><button class="primary-action" type="button" data-testid="warehouse-confirm" :disabled="confirming" :aria-busy="confirming" @click="confirm">{{ confirming ? '处理中…' : '确认' }}</button></div></div></div>
  </Teleport>
</template>
