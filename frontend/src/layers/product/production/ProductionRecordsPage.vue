<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { ColumnItem, FilterItem } from '../../common/ui/DataTablePage.vue'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import { submitErrorText, messageWithContext as message } from '../../common/api/errors'
import AttachmentList from '../../common/ui/AttachmentList.vue'
import AttachmentUpload from '../../common/ui/AttachmentUpload.vue'
import { useSubmitGuard } from '../../common/ui/useSubmitGuard'
import type { ProductionField, ProductionRecord, ProductionResource } from '../../common/api/production.models'
import { createProductionCorrection, createProductionRecord, deleteProductionDraft, listProductionRecords, submitProductionRecord, updateProductionRecord, verifyProductionRecord } from '../../features/production/production.service'

const props = withDefaults(defineProps<{
  resource: ProductionResource; title: string; label: string; description: string; createLabel: string
  fields: ProductionField[]; columns: ColumnItem[]; highRisk?: boolean
  extraFilters?: FilterItem[]
}>(), { highRisk: false })
const rows = ref<ProductionRecord[]>([])
const loading = ref(true)
const pageError = ref('')
const dialogError = ref('')
const formOpen = ref(false)
const editing = ref<ProductionRecord | null>(null)
const correcting = ref<ProductionRecord | null>(null)
const form = reactive<Record<string, string | number>>({})
const confirmAction = ref<'delete' | 'submit' | 'verify' | null>(null)
const target = ref<ProductionRecord | null>(null)
const evidenceText = ref('')
const entityType = computed(() => `production:${props.resource}`)
const attachmentRefreshKey = ref(0)
function onEvidenceUploaded(attachment: { id: number }) { addEvidenceId(attachment.id); attachmentRefreshKey.value += 1 }
function addEvidenceId(id: number) {
  const ids = evidenceText.value.split(',').map((item) => item.trim()).filter(Boolean)
  ids.push(String(id)); evidenceText.value = ids.join(',')
}

const names: Record<string, string> = { draft: '草稿', submitted: '待核验', verified: '已核验', corrected: '已更正', archived: '已归档' }
const batchNames: Record<string, string> = { stocked: '已放养', farming: '养殖中', pending_settlement: '待结算', closed: '已关闭' }
const tones = { 草稿: 'slate', 待核验: 'amber', 已核验: 'teal', 已更正: 'blue', 已归档: 'slate' } as const
const displayRows = computed(() => rows.value.map((row) => ({ ...row, lifecycle_label: names[row.status] ?? row.status, batch_status_label: batchNames[String(row.batch_status)] ?? row.batch_status })))
const tableColumns = computed<ColumnItem[]>(() => [...props.columns, { key: 'lifecycle_label', label: '业务状态', type: 'badge', tones }])
const filters = computed<FilterItem[]>(() => [
  ...(props.extraFilters ?? []),
  { key: 'status', type: 'select', label: '全部业务状态', options: Object.entries(names).map(([value, label]) => ({ value, label })) },
  { key: 'name', type: 'search', placeholder: `搜索${props.title} / 单号`, wide: true },
])
const kpis = computed(() => [
  { label: '记录总数', value: rows.value.length, unit: '条', hint: '当前授权范围' },
  { label: '待核验', value: rows.value.filter((row) => row.status === 'submitted').length, unit: '条', tone: 'amber' as const, hint: '提交后仍可编辑' },
  { label: '正式记录', value: rows.value.filter((row) => row.status === 'verified').length, unit: '条', tone: 'teal' as const, hint: '核验后只读' },
])
async function load() {
  loading.value = true; pageError.value = ''
  try { rows.value = (await listProductionRecords(props.resource)).items }
  catch (error) { rows.value = []; pageError.value = message(error, '生产数据加载失败') }
  finally { loading.value = false }
}
function openForm(row?: ProductionRecord, correction = false) {
  editing.value = correction ? null : row ?? null; correcting.value = correction ? row ?? null : null; dialogError.value = ''
  for (const field of props.fields) form[field.key] = correction && field.key === 'note' ? '' : (row?.[field.key] as string | number) ?? ''
  formOpen.value = true
}
function body() {
  const payload: Record<string, unknown> = {}
  for (const field of props.fields) {
    const value = form[field.key]
    if (field.required && !String(value ?? '').trim()) throw new Error(`请填写${field.label}`)
    if (value !== '') payload[field.key] = field.type === 'number' ? Number(value) : String(value).trim()
  }
  return payload
}
function replace(row: ProductionRecord) {
  const index = rows.value.findIndex((item) => item.id === row.id)
  if (index < 0) rows.value.unshift(row); else rows.value[index] = row
}
const { busy: saving, run: runSave } = useSubmitGuard()
async function save() {
  dialogError.value = ''
  await runSave(async () => {
    try {
      const payload = body()
      const result = correcting.value
        ? await createProductionCorrection(props.resource, correcting.value.id, { ...payload, expected_version: correcting.value.version })
        : editing.value
          ? await updateProductionRecord(props.resource, editing.value.id, { ...payload, expected_version: editing.value.version })
          : await createProductionRecord(props.resource, payload)
      replace(result.record); formOpen.value = false
    } catch (error) { dialogError.value = error instanceof Error ? submitErrorText(error, error.message) : '生产记录保存失败' }
  })
}
function ask(action: 'delete' | 'submit' | 'verify', row: ProductionRecord) {
  target.value = row; confirmAction.value = action; evidenceText.value = ''; dialogError.value = ''
}
const { busy: confirming, run: runConfirm } = useSubmitGuard()
async function confirm() {
  if (!target.value || !confirmAction.value) return
  dialogError.value = ''
  const row = target.value
  const action = confirmAction.value
  if (!row || !action) return
  await runConfirm(async () => {
  try {
    if (action === 'delete') { await deleteProductionDraft(props.resource, row.id); rows.value = rows.value.filter((item) => item.id !== row.id) }
    else {
      const evidence = evidenceText.value.split(',').map((item) => Number(item.trim())).filter((item) => Number.isInteger(item) && item > 0)
      if (action === 'verify' && props.highRisk && !evidence.length) throw new Error('高风险业务核验必须填写凭据附件 ID')
      const result = action === 'submit'
        ? await submitProductionRecord(props.resource, row.id, row.version)
        : await verifyProductionRecord(props.resource, row.id, row.version, evidence)
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
  else if (name === 'delete' || name === 'submit' || name === 'verify') ask(name, row)
}
onMounted(load)
</script>

<template>
  <div v-if="pageError" class="page-card table-empty" role="alert">{{ pageError }}<div style="margin-top:12px"><button class="ghost-action" type="button" @click="load">重新加载</button></div></div>
  <DataTablePage v-else :export-resource="resource" :title="title" :label="label" :description="description" :create-label="createLabel" :kpis="kpis"
    :filters="filters"
    :columns="tableColumns" :rows="displayRows" action-test-id-prefix="production-action"
    :empty-text="loading ? '正在加载生产记录…' : '当前授权范围内暂无记录'" @create="openForm()" @action="action" />
  <Teleport to="body">
    <div v-if="formOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="生产记录编辑"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">{{ correcting ? 'Correction' : editing ? 'Edit' : 'Create' }}</p><h2>{{ correcting ? `更正 · ${title}` : editing ? `编辑 · ${title}` : `新增 · ${title}` }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="formOpen = false">×</button></div><p class="section-subtitle">{{ correcting ? '将创建关联更正单；原核验记录保持只读且不会被修改。' : '提交后仍可编辑并保留版本；核验后只能查看或发起更正。' }}</p><div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))"><label v-for="field in fields" :key="field.key" class="modal-field" :for="`production-${field.key}`" :style="field.type === 'textarea' ? 'grid-column:1/-1' : ''"><span>{{ correcting && field.key === 'note' ? '更正原因' : field.label }}{{ field.required || correcting && field.key === 'note' ? ' *' : '' }}</span><textarea v-if="field.type === 'textarea'" :id="`production-${field.key}`" v-model="form[field.key]" rows="3" class="filter-input" style="width:100%;resize:vertical" /><input v-else :id="`production-${field.key}`" v-model="form[field.key]" :type="field.type ?? 'text'" :min="field.type === 'number' ? 0 : undefined" class="filter-input" style="width:100%"></label></div><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="formOpen = false">取消</button><button class="primary-action" type="button" data-testid="production-save" :disabled="saving" :aria-busy="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button></div></div></div>
    <div v-if="confirmAction && target" class="modal-overlay" role="dialog" aria-modal="true" aria-label="生产操作确认"><div class="modal-panel" style="width:min(500px,100%)"><div class="modal-panel__head"><div><p class="section-label">Confirm</p><h2>{{ confirmAction === 'verify' ? '核验并入账' : confirmAction === 'submit' ? '提交核验' : '删除草稿' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="confirmAction = null">×</button></div><p class="section-subtitle">{{ confirmAction === 'verify' ? '核验使用当前最新版本，完成后记录永久只读。' : confirmAction === 'submit' ? '提交后仍可编辑，待办将跟随最新版本。' : '仅无引用、未提交的草稿可以删除。' }}</p><div v-if="confirmAction === 'verify' && highRisk" class="modal-row" style="grid-template-columns:1fr"><label class="modal-field"><span>凭据附件 ID *</span><input id="production-evidence" v-model="evidenceText" class="filter-input" style="width:100%" placeholder="上传或选择附件后自动回填，多个 ID 用英文逗号分隔"></label><div class="modal-field"><span>上传凭据</span><AttachmentUpload :organization-id="Number((target as Record<string, unknown>).organization_id ?? 1)" :entity-type="entityType" :entity-id="target.id" @uploaded="onEvidenceUploaded" /></div><div class="modal-field"><span>已有凭据</span><AttachmentList :entity-type="entityType" :entity-id="target.id" :refresh-key="attachmentRefreshKey" selectable @select="addEvidenceId" /></div></div><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="confirmAction = null">取消</button><button class="primary-action" type="button" data-testid="production-confirm" :disabled="confirming" :aria-busy="confirming" @click="confirm">{{ confirming ? '处理中…' : '确认' }}</button></div></div></div>
  </Teleport>
</template>
