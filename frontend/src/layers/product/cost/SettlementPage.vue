<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { CostSettlementRecord } from '../../common/api/cost.models'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import { submitErrorText } from '../../common/api/errors'

// 写操作防重复提交：busy + disabled + 防抖（BUG-M2-05/BUG-M4-09）
const submitting = ref(false)
import { confirmCostSettlement, createCostSettlement, deleteCostSettlement, getSettlements, reverseCostSettlement, runCostAllocation, submitCostSettlement, updateCostSettlement, verifyCostSettlement } from '../../features/cost/cost.service'

const records = ref<CostSettlementRecord[]>([]), currentPage = ref(1), total = ref(0)
const error = ref(''), dialogError = ref(''), formOpen = ref(false)
const target = ref<CostSettlementRecord | null>(null), pendingAction = ref<'delete' | 'submit' | 'verify' | 'confirm' | 'reverse' | null>(null)
const formMode = ref<'create' | 'edit' | 'view'>('create')
const reason = ref(''), allocationMessage = ref('')
const form = reactive<Record<string, string | number>>({})
const statusLabels: Record<string, string> = { draft: '草稿', submitted: '待核验', verified: '待确认', confirmed: '已结算', reversed: '已反结算', cancelled: '已作废' }
const statusTones = { 草稿: 'slate', 待核验: 'amber', 待确认: 'blue', 已结算: 'teal', 已反结算: 'rose', 已作废: 'slate' } as const
const rows = computed(() => records.value.map((item) => ({ ...item, period: `${item.period_start} ~ ${item.period_end}`, incomeText: `¥${Number(item.income_amount).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`, costText: `¥${Number(item.cost_amount).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`, profitText: `¥${Number(item.profit_amount).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`, margin: Number(item.income_amount) ? `${(Number(item.profit_amount) / Number(item.income_amount) * 100).toFixed(1)}%` : '—', lifecycle_label: statusLabels[item.status] ?? item.status })))
const confirmed = computed(() => records.value.filter((item) => item.status === 'confirmed'))
const netProfit = computed(() => confirmed.value.reduce((sum, item) => sum + Number(item.profit_amount), 0))

async function loadPage(query: Record<string, string | number> = {}) {
  error.value = ''
  try { const result = await getSettlements({ page: Number(query.page ?? currentPage.value), page_size: Number(query.page_size ?? 20), status: String(query.status ?? ''), search: String(query.period ?? '') }); records.value = result.items; currentPage.value = result.page; total.value = result.total }
  catch { records.value = []; total.value = 0; error.value = '结算数据加载失败，请稍后重试' }
}
function openForm(row?: CostSettlementRecord, readOnly = false) {
  formMode.value = row ? (readOnly ? 'view' : 'edit') : 'create'; target.value = row ?? null
  const today = new Date().toISOString().slice(0, 10); Object.assign(form, row ? { name: row.name, farm_id: row.farm_id, area_id: row.area_id ?? '', period_start: row.period_start, period_end: row.period_end, allocation_run_id: row.allocation_run_id } : { name: `${today.slice(0, 7)} 期间结算`, farm_id: '', area_id: '', period_start: `${today.slice(0, 8)}01`, period_end: today, allocation_run_id: '' }); allocationMessage.value = ''; dialogError.value = ''; formOpen.value = true
}
async function allocate() {
  if (submitting.value) return
  submitting.value = true
  dialogError.value = ''
  try { if (!form.period_start || !form.period_end || !Number(form.farm_id)) throw new Error('请先选择基地和完整结算期间'); const area = Number(form.area_id); const result = await runCostAllocation(String(form.period_start), String(form.period_end), Number(form.farm_id), area || undefined); form.allocation_run_id = result.id; allocationMessage.value = `分摊完成：来源 ${result.source_total}，已分摊 ${result.allocated_total}` }
  catch (failure) { dialogError.value = failure instanceof Error ? submitErrorText(failure, failure.message) : '成本分摊失败' }
  finally { submitting.value = false }
}
function replace(row: CostSettlementRecord) { const index = records.value.findIndex((item) => item.id === row.id); if (index < 0) records.value.unshift(row); else records.value[index] = row }
async function save() {
  if (submitting.value) return
  submitting.value = true
  dialogError.value = ''
  try { if (!form.name) throw new Error('请填写结算名称'); const row = formMode.value === 'edit' && target.value ? await updateCostSettlement(target.value.id, { name: form.name, expected_version: target.value.version }) : await createCostSettlement({ name: form.name, period_start: form.period_start, period_end: form.period_end, allocation_run_id: Number(form.allocation_run_id) }); replace(row); formOpen.value = false }
  catch (failure) { dialogError.value = failure instanceof Error ? submitErrorText(failure, failure.message) : '结算保存失败' }
  finally { submitting.value = false }
}
function action(name: string, raw: Record<string, unknown>) {
  const row = records.value.find((item) => item.id === Number(raw.id)); if (!row) return
  if (name === 'view') { openForm(row, true); return }
  if (name === 'edit') { openForm(row); return }
  if (!['delete', 'submit', 'verify', 'confirm', 'reverse'].includes(name)) return
  target.value = row; pendingAction.value = name as typeof pendingAction.value; reason.value = ''; dialogError.value = ''
}
async function confirmAction() {
  if (submitting.value) return
  submitting.value = true
  if (!target.value || !pendingAction.value) return
  try {
    const row = target.value, actionName = pendingAction.value
    if (actionName === 'delete') { await deleteCostSettlement(row.id); records.value = records.value.filter((item) => item.id !== row.id); total.value = Math.max(0, total.value - 1) }
    else if (actionName === 'reverse') { if (reason.value.trim().length < 2) throw new Error('反结算必须填写原因'); replace(await reverseCostSettlement(row.id, row.version, reason.value.trim())) }
    else if (actionName === 'submit') replace(await submitCostSettlement(row.id, row.version))
    else if (actionName === 'verify') replace(await verifyCostSettlement(row.id, row.version))
    else replace(await confirmCostSettlement(row.id, row.version))
    pendingAction.value = null; target.value = null
  } catch (failure) { dialogError.value = failure instanceof Error ? submitErrorText(failure, failure.message) : '结算操作失败' }
  finally { submitting.value = false }
}
onMounted(() => loadPage())
</script>

<template>
  <p v-if="error" class="form-error" role="alert">{{ error }}</p>
  <DataTablePage export-resource="settlements" title="期间结算" label="Cost & operations / Settlements" description="按确认的收入、成本和分摊快照生成期间结果；反结算保留原始来源。" create-label="＋ 新建结算" :kpis="[
    { label: '本页已结算', value: confirmed.length, unit: '期', hint: `全量 ${total} 期` }, { label: '本页已确认净利润', value: `¥${netProfit.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`, tone: netProfit >= 0 ? 'teal' : 'rose' }, { label: '本页待处理', value: records.filter((item) => ['submitted', 'verified'].includes(item.status)).length, unit: '期', tone: 'amber' },
  ]" :filters="[{ key: 'status', type: 'select', label: '全部状态', options: Object.entries(statusLabels).map(([value, label]) => ({ value, label })) }, { key: 'period', type: 'search', placeholder: '搜索结算期间 / 单号' }]" :columns="[
    { key: 'code', label: '结算单号', type: 'title', sub: 'period' }, { key: 'incomeText', label: '确认收入', type: 'strong' }, { key: 'costText', label: '归集成本' }, { key: 'profitText', label: '净利润' }, { key: 'margin', label: '利润率', type: 'number' }, { key: 'operator', label: '经办人' }, { key: 'lifecycle_label', label: '状态', type: 'badge', tones: statusTones },
  ]" :rows="rows" action-test-id-prefix="cost-settlement-action" server-side :total="total" :current-page="currentPage" :page-size="20" @create="openForm" @action="action" @query="loadPage" empty-text="当前范围没有结算记录" />
  <Teleport to="body">
    <div v-if="formOpen" class="modal-overlay" role="dialog" aria-modal="true" :aria-label="formMode === 'view' ? '查看期间结算' : formMode === 'edit' ? '编辑期间结算' : '新建期间结算'"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">Settlement</p><h2>{{ formMode === 'view' ? '查看期间结算' : formMode === 'edit' ? '编辑期间结算' : '新建期间结算' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="formOpen = false">×</button></div><p class="section-subtitle">结算来源快照不可改；草稿和待核验记录可修改名称，核验后全部只读。</p><div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))"><label class="modal-field" for="cost-settlement-name"><span>结算名称 *</span><input id="cost-settlement-name" v-model="form.name" :readonly="formMode === 'view'" class="filter-input" style="width:100%"></label><label class="modal-field" for="cost-settlement-farm"><span>基地 ID *</span><input id="cost-settlement-farm" v-model="form.farm_id" type="number" min="1" :readonly="formMode !== 'create'" class="filter-input" style="width:100%"></label><label class="modal-field" for="cost-settlement-area"><span>区域 ID</span><input id="cost-settlement-area" v-model="form.area_id" type="number" min="1" :readonly="formMode !== 'create'" class="filter-input" style="width:100%"></label><label class="modal-field" for="cost-settlement-allocation"><span>分摊结果 ID *</span><input id="cost-settlement-allocation" v-model="form.allocation_run_id" type="number" min="1" readonly class="filter-input" style="width:100%"></label><label class="modal-field" for="cost-settlement-start"><span>期间开始 *</span><input id="cost-settlement-start" v-model="form.period_start" type="date" :readonly="formMode !== 'create'" class="filter-input" style="width:100%"></label><label class="modal-field" for="cost-settlement-end"><span>期间结束 *</span><input id="cost-settlement-end" v-model="form.period_end" type="date" :readonly="formMode !== 'create'" class="filter-input" style="width:100%"></label></div><p v-if="allocationMessage" class="section-subtitle" style="color:#3f8f7f">{{ allocationMessage }}</p><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="formOpen = false">关闭</button><button v-if="formMode === 'create'" class="ghost-action" type="button" data-testid="cost-settlement-allocate" :disabled="submitting" :aria-busy="submitting" @click="allocate">{{ submitting ? '分摊中…' : '运行分摊' }}</button><button v-if="formMode !== 'view'" class="primary-action" type="button" data-testid="cost-settlement-save" :disabled="submitting" :aria-busy="submitting" @click="save">{{ submitting ? '保存中…' : '保存' }}</button></div></div></div>
    <div v-if="pendingAction && target" class="modal-overlay" role="dialog" aria-modal="true" aria-label="结算操作确认"><div class="modal-panel" style="width:min(500px,100%)"><div class="modal-panel__head"><div><p class="section-label">Confirm</p><h2>确认{{ pendingAction === 'reverse' ? '反结算' : pendingAction === 'verify' ? '核验' : pendingAction === 'confirm' ? '锁定结算' : '提交' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="pendingAction = null">×</button></div><p class="section-subtitle">确认结算后期间锁定；历史漏单只能先反结算再重新核算。</p><label v-if="pendingAction === 'reverse'" class="modal-field" for="cost-settlement-reason"><span>反结算原因 *</span><textarea id="cost-settlement-reason" v-model="reason" rows="3" class="filter-input" style="width:100%"></textarea></label><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="pendingAction = null">返回</button><button class="primary-action" type="button" data-testid="cost-settlement-confirm" :disabled="submitting" :aria-busy="submitting" @click="confirmAction">{{ submitting ? '处理中…' : '确认' }}</button></div></div></div>
  </Teleport>
</template>
