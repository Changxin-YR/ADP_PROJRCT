<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { CostAssetRecord } from '../../common/api/cost.models'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import EvidencePicker from '../../common/ui/EvidencePicker.vue'
import { submitErrorText } from '../../common/api/errors'

// 写操作防重复提交：busy + disabled + 防抖（BUG-M2-05/BUG-M4-09）
const submitting = ref(false)
import { confirmCostAsset, createCostAsset, deleteCostAsset, depreciateCostAsset, getAssets, submitCostAsset, updateCostAsset, verifyCostAsset } from '../../features/cost/cost.service'

const categories = [['equipment', '设备'], ['infrastructure', '基础建设'], ['pond_rent', '租赁'], ['other', '其他']]
const records = ref<CostAssetRecord[]>([]), currentPage = ref(1), total = ref(0)
const error = ref(''), dialogError = ref(''), formOpen = ref(false)
const editing = ref<CostAssetRecord | null>(null), target = ref<CostAssetRecord | null>(null)
const pendingAction = ref<'delete' | 'submit' | 'verify' | 'confirm' | 'depreciate' | null>(null)
const evidence = ref('')
const entityType = computed(() => 'cost:asset')
const attachmentRefreshKey = ref(0)
, period = ref('')
const form = reactive<Record<string, string | number>>({})
const statusLabels: Record<string, string> = { draft: '草稿', submitted: '待核验', verified: '待确认', confirmed: '在用', retired: '停用', disposed: '报废', cancelled: '已作废' }
const statusTones = { 草稿: 'slate', 待核验: 'amber', 待确认: 'blue', 在用: 'teal', 停用: 'slate', 报废: 'rose', 已作废: 'slate' } as const
const fields = [
  { key: 'organization_id', label: '企业 ID', type: 'number', required: true }, { key: 'farm_id', label: '基地 ID', type: 'number', required: true },
  { key: 'area_id', label: '区域 ID', type: 'number' }, { key: 'code', label: '资产编号', required: true }, { key: 'name', label: '资产名称', required: true },
  { key: 'asset_type', label: '资产类型', type: 'asset_type', required: true }, { key: 'category_code', label: '成本类别', type: 'category', required: true },
  { key: 'purchase_date', label: '购置日期', type: 'date', required: true }, { key: 'original_value', label: '资产原值', type: 'number', required: true },
  { key: 'salvage_value', label: '预计残值', type: 'number' }, { key: 'useful_life_months', label: '使用期限（月）', type: 'number', required: true },
  { key: 'depreciation_start_date', label: '折旧开始日', type: 'date', required: true }, { key: 'allocation_driver', label: '分摊依据', type: 'driver' },
  { key: 'target_type', label: '归属类型', type: 'target' }, { key: 'target_id', label: '归属对象 ID', type: 'number' }, { key: 'note', label: '备注' },
]
const rows = computed(() => records.value.map((item) => ({ ...item, valueText: `¥${Number(item.original_value).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`, life: `${item.useful_life_months} 个月`, depreciation: `¥${Number(item.accumulated_depreciation).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`, owner_scope: item.area_id ? `区域 #${item.area_id}` : '公共资产', lifecycle_label: statusLabels[item.status] ?? item.status })))
const originalValue = computed(() => records.value.reduce((sum, item) => sum + Number(item.original_value), 0))
const depreciation = computed(() => records.value.reduce((sum, item) => sum + Number(item.accumulated_depreciation), 0))

async function loadPage(query: Record<string, string | number> = {}) {
  error.value = ''
  try { const result = await getAssets({ page: Number(query.page ?? currentPage.value), page_size: Number(query.page_size ?? 20), status: String(query.status ?? ''), search: String(query.name ?? '') }); records.value = result.items; currentPage.value = result.page; total.value = result.total }
  catch { records.value = []; total.value = 0; error.value = '资产数据加载失败，请稍后重试' }
}
function defaults() { const today = new Date().toISOString().slice(0, 10); return { asset_type: 'equipment', category_code: 'equipment', purchase_date: today, depreciation_start_date: today, salvage_value: 0, useful_life_months: 60, allocation_driver: 'equipment_count' } }
function openForm(row?: CostAssetRecord) { editing.value = row ?? null; dialogError.value = ''; Object.keys(form).forEach((key) => delete form[key]); Object.assign(form, defaults(), row ?? {}); formOpen.value = true }
function payload() {
  const result: Record<string, unknown> = {}
  for (const field of fields) { const value = form[field.key]; if (field.required && !String(value ?? '').trim()) throw new Error(`请填写${field.label}`); if (value !== '' && value != null) result[field.key] = field.type === 'number' ? Number(value) : value }
  return result
}
function replace(row: CostAssetRecord) { const index = records.value.findIndex((item) => item.id === row.id); if (index < 0) records.value.unshift(row); else records.value[index] = row }
async function save() {
  if (submitting.value) return
  submitting.value = true
  dialogError.value = ''
  try { const body = payload(); replace(editing.value ? await updateCostAsset(editing.value.id, { ...body, expected_version: editing.value.version }) : await createCostAsset(body)); formOpen.value = false }
  catch (failure) { dialogError.value = failure instanceof Error ? submitErrorText(failure, failure.message) : '资产保存失败' }
  finally { submitting.value = false }
}
function action(name: string, raw: Record<string, unknown>) {
  const row = records.value.find((item) => item.id === Number(raw.id)); if (!row) return
  if (name === 'edit') openForm(row)
  else if (['delete', 'submit', 'verify', 'confirm', 'depreciate'].includes(name)) { target.value = row; pendingAction.value = name as typeof pendingAction.value; evidence.value = ''; period.value = ''; dialogError.value = '' }
}
function evidenceIds() { return [...new Set(evidence.value.split(',').map(Number).filter((id) => Number.isInteger(id) && id > 0))] }
async function confirmAction() {
  if (submitting.value) return
  submitting.value = true
  if (!target.value || !pendingAction.value) return
  try {
    const row = target.value, actionName = pendingAction.value
    if (actionName === 'delete') { await deleteCostAsset(row.id); records.value = records.value.filter((item) => item.id !== row.id) }
    else if (actionName === 'submit') replace(await submitCostAsset(row.id, row.version))
    else if (actionName === 'depreciate') { if (!/^\d{4}-\d{2}$/.test(period.value)) throw new Error('请选择折旧期间'); await depreciateCostAsset(row.id, period.value); await loadPage() }
    else { const ids = evidenceIds(); if (!ids.length) throw new Error('核验或确认必须填写凭据附件 ID'); replace(actionName === 'verify' ? await verifyCostAsset(row.id, row.version, ids) : await confirmCostAsset(row.id, row.version, ids)) }
    pendingAction.value = null; target.value = null
  } catch (failure) { dialogError.value = failure instanceof Error ? submitErrorText(failure, failure.message) : '资产操作失败' }
  finally { submitting.value = false }
}
onMounted(() => loadPage())
</script>

<template>
  <p v-if="error" class="form-error" role="alert">{{ error }}</p>
  <DataTablePage export-resource="assets" title="资产台账" label="Cost & operations / Assets" description="设备、基础设施与租赁资产按确认状态和折旧期间留痕管理。" create-label="＋ 新增资产" :kpis="[
    { label: '资产总数', value: total, unit: '项', hint: '当前授权范围' }, { label: '本页资产原值', value: `¥${originalValue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` }, { label: '本页累计折旧', value: `¥${depreciation.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`, tone: 'blue' },
  ]" :filters="[{ key: 'status', type: 'select', label: '全部状态', options: Object.entries(statusLabels).map(([value, label]) => ({ value, label })) }, { key: 'name', type: 'search', placeholder: '搜索资产名称 / 编号' }]" :columns="[
    { key: 'code', label: '资产编号', type: 'title', sub: 'category_name' }, { key: 'name', label: '资产名称' }, { key: 'valueText', label: '原值', type: 'strong' }, { key: 'life', label: '使用期限' }, { key: 'depreciation', label: '累计折旧' }, { key: 'owner_scope', label: '归属' }, { key: 'lifecycle_label', label: '状态', type: 'badge', tones: statusTones },
  ]" :rows="rows" action-test-id-prefix="cost-asset-action" server-side :total="total" :current-page="currentPage" :page-size="20" @create="openForm()" @action="action" @query="loadPage" empty-text="当前范围没有资产记录" />
  <Teleport to="body">
    <div v-if="formOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="资产编辑"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">Asset</p><h2>{{ editing ? '编辑资产' : '新增资产' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="formOpen = false">×</button></div><p class="section-subtitle">提交后仍可编辑；核验后业务字段只读，折旧按期间追加记录。</p><div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))"><label v-for="field in fields" :key="field.key" class="modal-field" :for="`cost-asset-${field.key}`"><span>{{ field.label }}{{ field.required ? ' *' : '' }}</span><select v-if="field.type === 'category'" :id="`cost-asset-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%"><option v-for="item in categories" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select><select v-else-if="field.type === 'asset_type'" :id="`cost-asset-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%"><option value="equipment">设备</option><option value="infrastructure">基础设施</option><option value="lease">租赁</option></select><select v-else-if="field.type === 'driver'" :id="`cost-asset-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%"><option v-for="item in ['area','equipment_count','runtime_hours','equal']" :key="item" :value="item">{{ item }}</option></select><select v-else-if="field.type === 'target'" :id="`cost-asset-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%"><option value="">公共范围</option><option v-for="item in ['farm','area','group','pond','batch']" :key="item" :value="item">{{ item }}</option></select><input v-else :id="`cost-asset-${field.key}`" v-model="form[field.key]" :type="field.type ?? 'text'" :min="field.type === 'number' ? 0 : undefined" class="filter-input" style="width:100%"></label></div><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="formOpen = false">取消</button><button class="primary-action" type="button" data-testid="cost-asset-save" :disabled="submitting" :aria-busy="submitting" @click="save">{{ submitting ? '保存中…' : '保存' }}</button></div></div></div>
    <div v-if="pendingAction && target" class="modal-overlay" role="dialog" aria-modal="true" aria-label="资产操作确认"><div class="modal-panel" style="width:min(500px,100%)"><div class="modal-panel__head"><div><p class="section-label">Confirm</p><h2>确认{{ pendingAction === 'depreciate' ? '计提折旧' : pendingAction === 'verify' ? '核验' : pendingAction === 'confirm' ? '确认资产' : pendingAction === 'submit' ? '提交' : '删除草稿' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="pendingAction = null">×</button></div><p class="section-subtitle">已确认资产不删除、不改写；折旧以追加记录进入成本。</p><EvidencePicker v-if="pendingAction === 'verify' || pendingAction === 'confirm'" v-model="evidence" input-id="cost-asset-evidence" :organization-id="Number((target as Record<string, unknown>).organization_id ?? 1)" :entity-type="entityType" :entity-id="target.id" :refresh-key="attachmentRefreshKey" /><label v-if="pendingAction === 'depreciate'" class="modal-field" for="cost-asset-period"><span>折旧期间 *</span><input id="cost-asset-period" v-model="period" type="month" class="filter-input" style="width:100%"></label><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="pendingAction = null">返回</button><button class="primary-action" type="button" data-testid="cost-asset-confirm" :disabled="submitting" :aria-busy="submitting" @click="confirmAction">{{ submitting ? '处理中…' : '确认' }}</button></div></div></div>
  </Teleport>
</template>
