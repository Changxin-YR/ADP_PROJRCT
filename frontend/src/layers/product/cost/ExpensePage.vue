<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { CostExpenseRecord } from '../../common/api/cost.models'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import EvidencePicker from '../../common/ui/EvidencePicker.vue'
import { submitErrorText } from '../../common/api/errors'

// 写操作防重复提交：busy + disabled + 防抖（BUG-M2-05/BUG-M4-09）
const submitting = ref(false)
import { confirmCostExpense, createCostExpense, deleteCostExpense, getExpenses, reverseCostExpense, submitCostExpense, updateCostExpense, verifyCostExpense } from '../../features/cost/cost.service'

const categories = [['pond_rent', '塘租'], ['equipment', '设备'], ['infrastructure', '基础建设'], ['labor', '人工'], ['electricity', '电费'], ['seed', '苗种'], ['feed', '饲料'], ['health', '动保'], ['other', '其他费用']]
const records = ref<CostExpenseRecord[]>([]), currentPage = ref(1), total = ref(0)
const error = ref(''), dialogError = ref(''), formOpen = ref(false)
const editing = ref<CostExpenseRecord | null>(null), target = ref<CostExpenseRecord | null>(null)
const pendingAction = ref<'delete' | 'submit' | 'verify' | 'confirm' | 'reverse' | null>(null)
const evidence = ref('')
const entityType = computed(() => 'cost:expense')
const attachmentRefreshKey = ref(0)
, reason = ref('')
const form = reactive<Record<string, string | number>>({})
const statusLabels: Record<string, string> = { draft: '草稿', submitted: '待核验', verified: '待确认', confirmed: '已确认', reversed: '已冲销', cancelled: '已作废' }
const statusTones = { 草稿: 'slate', 待核验: 'amber', 待确认: 'blue', 已确认: 'teal', 已冲销: 'rose', 已作废: 'slate' } as const
const fields = [
  { key: 'organization_id', label: '企业 ID', type: 'number', required: true }, { key: 'farm_id', label: '基地 ID', type: 'number', required: true },
  { key: 'area_id', label: '区域 ID', type: 'number' }, { key: 'category_code', label: '费用类别', type: 'category', required: true },
  { key: 'amount', label: '金额', type: 'number', required: true }, { key: 'occurred_on', label: '发生日期', type: 'date', required: true },
  { key: 'period_start', label: '期间开始', type: 'date', required: true }, { key: 'period_end', label: '期间结束', type: 'date', required: true },
  { key: 'cost_nature', label: '成本性质', type: 'nature' }, { key: 'source_type', label: '来源类型', required: true },
  { key: 'source_ref', label: '费用单号', required: true }, { key: 'target_type', label: '归属类型', type: 'target' },
  { key: 'target_id', label: '归属对象 ID', type: 'number' },
]
const rows = computed(() => records.value.map((item) => ({ ...item, code: item.source_ref, category: item.category_name, amountText: `¥${Number(item.amount).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`, scope: item.target_type && item.target_id ? `${item.target_type} #${item.target_id}` : '公共范围', basis: item.cost_nature === 'direct' ? '直接归集' : '按规则分摊', lifecycle_label: statusLabels[item.status] ?? item.status })))
const totalAmount = computed(() => records.value.reduce((sum, item) => sum + Number(item.amount), 0))

async function loadPage(query: Record<string, string | number> = {}) {
  error.value = ''
  try { const result = await getExpenses({ page: Number(query.page ?? currentPage.value), page_size: Number(query.page_size ?? 20), status: String(query.status ?? ''), search: String(query.code ?? '') }); records.value = result.items; currentPage.value = result.page; total.value = result.total }
  catch { records.value = []; total.value = 0; error.value = '费用数据加载失败，请稍后重试' }
}
function defaults() { const today = new Date().toISOString().slice(0, 10); return { cost_nature: 'public', source_type: 'manual_expense', occurred_on: today, period_start: `${today.slice(0, 8)}01`, period_end: today } }
function openForm(row?: CostExpenseRecord) { editing.value = row ?? null; dialogError.value = ''; Object.keys(form).forEach((key) => delete form[key]); Object.assign(form, defaults(), row ?? {}); formOpen.value = true }
function payload() {
  const result: Record<string, unknown> = {}
  for (const field of fields) { const value = form[field.key]; if (field.required && !String(value ?? '').trim()) throw new Error(`请填写${field.label}`); if (value !== '' && value != null) result[field.key] = field.type === 'number' ? Number(value) : value }
  return result
}
function replace(row: CostExpenseRecord) { const index = records.value.findIndex((item) => item.id === row.id); if (index < 0) records.value.unshift(row); else records.value[index] = row }
async function save() {
  if (submitting.value) return
  submitting.value = true
  dialogError.value = ''
  try { const body = payload(); const row = editing.value ? await updateCostExpense(editing.value.id, { ...body, expected_version: editing.value.version }) : await createCostExpense(body); replace(row); formOpen.value = false }
  catch (failure) { dialogError.value = failure instanceof Error ? submitErrorText(failure, failure.message) : '费用保存失败' }
  finally { submitting.value = false }
}
function action(name: string, raw: Record<string, unknown>) {
  const row = records.value.find((item) => item.id === Number(raw.id)); if (!row) return
  if (name === 'edit') openForm(row)
  else if (['delete', 'submit', 'verify', 'confirm', 'reverse'].includes(name)) { target.value = row; pendingAction.value = name as typeof pendingAction.value; evidence.value = ''; reason.value = ''; dialogError.value = '' }
}
function evidenceIds() { return [...new Set(evidence.value.split(',').map(Number).filter((id) => Number.isInteger(id) && id > 0))] }
async function confirmAction() {
  if (submitting.value) return
  submitting.value = true
  if (!target.value || !pendingAction.value) return
  try {
    const row = target.value, actionName = pendingAction.value
    if (actionName === 'delete') { await deleteCostExpense(row.id); records.value = records.value.filter((item) => item.id !== row.id) }
    else if (actionName === 'submit') replace(await submitCostExpense(row.id, row.version))
    else if (actionName === 'reverse') { if (reason.value.trim().length < 2) throw new Error('冲销必须填写原因'); replace(await reverseCostExpense(row.id, reason.value.trim())) }
    else { const ids = evidenceIds(); if (!ids.length) throw new Error('核验或确认必须填写凭据附件 ID'); replace(actionName === 'verify' ? await verifyCostExpense(row.id, row.version, ids) : await confirmCostExpense(row.id, row.version, ids)) }
    pendingAction.value = null; target.value = null
  } catch (failure) { dialogError.value = failure instanceof Error ? submitErrorText(failure, failure.message) : '费用操作失败' }
  finally { submitting.value = false }
}
onMounted(() => loadPage())
</script>

<template>
  <p v-if="error" class="form-error" role="alert">{{ error }}</p>
  <DataTablePage export-resource="expenses" title="费用登记" label="Cost & operations / Expenses" description="塘租、电费、人工等日常费用逐笔登记，已确认记录进入正式成本。" create-label="＋ 新增费用" :kpis="[
    { label: '本页费用', value: `¥${totalAmount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`, hint: `全量 ${total} 笔` },
    { label: '本页待核验', value: records.filter((item) => item.status === 'submitted').length, unit: '笔', tone: 'amber' },
    { label: '本页已确认', value: records.filter((item) => item.status === 'confirmed').length, unit: '笔', tone: 'teal' },
  ]" :filters="[{ key: 'status', type: 'select', label: '全部状态', options: Object.entries(statusLabels).map(([value, label]) => ({ value, label })) }, { key: 'code', type: 'search', placeholder: '搜索费用单号' }]" :columns="[
    { key: 'code', label: '费用单号', type: 'title', sub: 'occurred_on' }, { key: 'category', label: '费用类别' }, { key: 'amountText', label: '金额', type: 'strong' }, { key: 'scope', label: '归属范围' }, { key: 'basis', label: '成本口径' }, { key: 'lifecycle_label', label: '状态', type: 'badge', tones: statusTones },
  ]" :rows="rows" action-test-id-prefix="cost-expense-action" server-side :total="total" :current-page="currentPage" :page-size="20" @create="openForm()" @action="action" @query="loadPage" empty-text="当前范围没有费用记录" />
  <Teleport to="body">
    <div v-if="formOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="费用编辑"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">Expense</p><h2>{{ editing ? '编辑费用' : '新增费用' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="formOpen = false">×</button></div><p class="section-subtitle">提交后仍可编辑并递增版本；核验后只读，历史更正使用冲销记录。</p><div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))"><label v-for="field in fields" :key="field.key" class="modal-field" :for="`cost-expense-${field.key}`"><span>{{ field.label }}{{ field.required ? ' *' : '' }}</span><select v-if="field.type === 'category'" :id="`cost-expense-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%"><option value="" disabled>请选择费用类别</option><option v-for="item in categories" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select><select v-else-if="field.type === 'nature'" :id="`cost-expense-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%"><option value="public">公共成本</option><option value="direct">直接成本</option></select><select v-else-if="field.type === 'target'" :id="`cost-expense-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%"><option value="">公共范围</option><option v-for="item in ['farm','area','group','pond','batch']" :key="item" :value="item">{{ item }}</option></select><input v-else :id="`cost-expense-${field.key}`" v-model="form[field.key]" :type="field.type ?? 'text'" :min="field.type === 'number' ? 0 : undefined" class="filter-input" style="width:100%"></label></div><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="formOpen = false">取消</button><button class="primary-action" type="button" data-testid="cost-expense-save" :disabled="submitting" :aria-busy="submitting" @click="save">{{ submitting ? '保存中…' : '保存' }}</button></div></div></div>
    <div v-if="pendingAction && target" class="modal-overlay" role="dialog" aria-modal="true" aria-label="费用操作确认"><div class="modal-panel" style="width:min(500px,100%)"><div class="modal-panel__head"><div><p class="section-label">Confirm</p><h2>确认{{ pendingAction === 'reverse' ? '冲销' : pendingAction === 'verify' ? '核验' : pendingAction === 'confirm' ? '确认入账' : pendingAction === 'submit' ? '提交' : '删除草稿' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="pendingAction = null">×</button></div><p class="section-subtitle">正式费用不会删除；核验完成后记录永久只读。</p><EvidencePicker v-if="pendingAction === 'verify' || pendingAction === 'confirm'" v-model="evidence" input-id="cost-expense-evidence" :organization-id="Number((target as Record<string, unknown>).organization_id ?? 1)" :entity-type="entityType" :entity-id="target.id" :refresh-key="attachmentRefreshKey" /><label v-if="pendingAction === 'reverse'" class="modal-field" for="cost-expense-reason"><span>冲销原因 *</span><textarea id="cost-expense-reason" v-model="reason" rows="3" class="filter-input" style="width:100%"></textarea></label><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="pendingAction = null">返回</button><button class="primary-action" type="button" data-testid="cost-expense-confirm" :disabled="submitting" :aria-busy="submitting" @click="confirmAction">{{ submitting ? '处理中…' : '确认' }}</button></div></div></div>
  </Teleport>
</template>
