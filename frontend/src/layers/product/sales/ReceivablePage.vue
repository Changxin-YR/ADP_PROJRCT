<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ApiError, submitErrorText } from '../../common/api/errors'
import type { SalesReceivable, SalesReceipt } from '../../common/api/sales.models'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import EvidencePicker from '../../common/ui/EvidencePicker.vue'

// 写操作防重复提交：busy + disabled + 防抖（BUG-M2-05/BUG-M4-09）
const submitting = ref(false)
import { cancelSalesReceipt, createSalesReceipt, deleteSalesReceipt, listSalesReceivables, listSalesReceipts, reverseSalesReceipt, submitSalesReceipt, updateSalesReceipt, verifySalesReceipt } from '../../features/sales/sales.service'

const tab = ref<'receivables' | 'receipts'>('receivables')
const receivables = ref<SalesReceivable[]>([]), receipts = ref<SalesReceipt[]>([])
const receivableOptions = ref<SalesReceivable[]>([])
const receivableMeta = reactive({ page: 1, page_size: 20, total: 0 }), receiptMeta = reactive({ page: 1, page_size: 20, total: 0 })
const receivableSummary = reactive({ total_amount: 0, total_balance: 0, overpaid_amount: 0, overdue_count: 0 })
const loading = ref(true), pageError = ref(''), dialogError = ref(''), formOpen = ref(false)
const editing = ref<SalesReceipt | null>(null), target = ref<SalesReceipt | null>(null)
const confirmAction = ref<'delete' | 'submit' | 'verify' | 'cancel' | 'reverse' | null>(null)
const evidenceText = ref('')
const entityType = computed(() => 'sales:receipt')
const attachmentRefreshKey = ref(0)
, cancellationReason = ref(''), reversalReason = ref('')
const form = reactive<Record<string, string | number>>({})
const fields = [
  { key: 'code', label: '收款单号', required: true }, { key: 'name', label: '收款名称', required: true },
  { key: 'receivable_id', label: '应收来源', type: 'receivable', required: true }, { key: 'amount', label: '收款金额', type: 'number', required: true },
  { key: 'received_at', label: '收款日期', type: 'date', required: true }, { key: 'receipt_method', label: '收款方式', type: 'receipt_method', required: true },
  { key: 'note', label: '备注', type: 'textarea' },
]
const receivableLabels: Record<string, string> = { unpaid: '未收款', partial: '部分收款', settled: '已结清', overpaid: '多收待处理', disputed: '有争议', bad_debt: '坏账处理', cancelled: '已取消' }
const receiptLabels: Record<string, string> = { draft: '草稿', submitted: '待核验', verified: '已核验', cancelled: '已取消' }
const receivableTones = { 未收款: 'rose', 部分收款: 'amber', 已结清: 'teal', 多收待处理: 'rose', 有争议: 'rose', 坏账处理: 'slate', 已取消: 'slate' } as const
const receiptTones = { 草稿: 'slate', 待核验: 'amber', 已核验: 'teal', 已冲销: 'slate', 已取消: 'slate' } as const
const receivableRows = computed(() => receivables.value.map((row) => ({ ...row, lifecycle_label: receivableLabels[row.status] ?? row.status, term: row.overdue_days > 0 ? `逾期 ${row.overdue_days} 天` : `剩余 ${Math.abs(row.overdue_days)} 天` })))
const receiptRows = computed(() => receipts.value.map((row) => ({ ...row, lifecycle_label: row.reversal_id ? '已冲销' : receiptLabels[row.status] ?? row.status })))
const kpis = computed(() => tab.value === 'receivables' ? [
  { label: '应收总额', value: Number(receivableSummary.total_amount), hint: `${receivableMeta.total} 笔交付应收` },
  { label: '未收余额', value: Number(receivableSummary.total_balance), tone: 'amber' as const, hint: `多收待处理 ${Number(receivableSummary.overpaid_amount)}` },
  { label: '逾期应收', value: Number(receivableSummary.overdue_count), unit: '笔', tone: 'rose' as const, hint: '按到期日自动计算' },
] : [
  { label: '收款记录', value: receiptMeta.total, unit: '笔', hint: '当前授权范围' },
  { label: '待核验', value: receipts.value.filter((row) => row.status === 'submitted').length, unit: '笔', tone: 'amber' as const, hint: '经办与核验必须分离' },
  { label: '已核验', value: receipts.value.filter((row) => row.status === 'verified' && !row.reversal_id).length, unit: '笔', tone: 'teal' as const, hint: '核验后永久只读' },
])

const message = (error: unknown, fallback: string) => error instanceof ApiError ? `${fallback}：${error.message}` : fallback
async function loadReceivableOptions() {
  const items: SalesReceivable[] = []; let page = 1; let result
  do { result = await listSalesReceivables({ page, page_size: 100 }); items.push(...result.items); page += 1 } while (result.has_next)
  return items
}
async function load() {
  loading.value = true; pageError.value = ''
  try { const [a, b, options] = await Promise.all([listSalesReceivables(), listSalesReceipts(), loadReceivableOptions()]); receivables.value = a.items; receipts.value = b.items; receivableOptions.value = options; Object.assign(receivableMeta, a); Object.assign(receiptMeta, b); Object.assign(receivableSummary, a.summary) }
  catch (error) { receivables.value = []; receipts.value = []; pageError.value = message(error, '应收与收款数据加载失败') }
  finally { loading.value = false }
}
async function queryRows(query: Record<string, string | number>) {
  loading.value = true; pageError.value = ''
  try {
    const params = { page: Number(query.page), page_size: Number(query.page_size), status: String(query.status ?? ''), search: String(query.name ?? '') }
    if (tab.value === 'receivables') { const page = await listSalesReceivables(params); receivables.value = page.items; Object.assign(receivableMeta, page); Object.assign(receivableSummary, page.summary) }
    else { const page = await listSalesReceipts(params); receipts.value = page.items; Object.assign(receiptMeta, page) }
  } catch (error) { pageError.value = message(error, '应收与收款数据加载失败') }
  finally { loading.value = false }
}
function openForm(row?: SalesReceipt) { editing.value = row ?? null; dialogError.value = ''; for (const field of fields) form[field.key] = (row?.[field.key as keyof SalesReceipt] as string | number) ?? ''; formOpen.value = true }
function body() {
  const payload: Record<string, unknown> = {}
  for (const field of fields) { if (editing.value && field.key === 'receivable_id') continue; const value = form[field.key]; if (field.required && !String(value ?? '').trim()) throw new Error(`请填写${field.label}`); if (value !== '') payload[field.key] = ['number', 'receivable'].includes(field.type ?? '') ? Number(value) : String(value).trim() }
  return payload
}
function replace(row: SalesReceipt) { const index = receipts.value.findIndex((item) => item.id === row.id); if (index < 0) receipts.value.unshift(row); else receipts.value[index] = row }
async function reloadFinancials() {
  const [a, b, options] = await Promise.all([listSalesReceivables(), listSalesReceipts(), loadReceivableOptions()])
  receivables.value = a.items; receipts.value = b.items; receivableOptions.value = options; Object.assign(receivableMeta, a); Object.assign(receiptMeta, b); Object.assign(receivableSummary, a.summary)
}
async function save() {
  if (submitting.value) return
  submitting.value = true
  dialogError.value = ''
  try { const payload = body(); const result = editing.value ? await updateSalesReceipt(editing.value.id, { ...payload, expected_version: editing.value.version }) : await createSalesReceipt(payload); replace(result.record); formOpen.value = false; tab.value = 'receipts' }
  catch (error) { dialogError.value = error instanceof Error ? submitErrorText(error, error.message) : '收款记录保存失败' }
  finally { submitting.value = false }
}
function ask(action: 'delete' | 'submit' | 'verify' | 'cancel' | 'reverse', row: SalesReceipt) { target.value = row; confirmAction.value = action; evidenceText.value = ''; cancellationReason.value = ''; reversalReason.value = ''; dialogError.value = '' }
async function confirm() {
  if (submitting.value) return
  submitting.value = true
  if (!target.value || !confirmAction.value) return
  try {
    if (confirmAction.value === 'delete') { await deleteSalesReceipt(target.value.id); receipts.value = receipts.value.filter((row) => row.id !== target.value!.id) }
    else if (confirmAction.value === 'verify' || confirmAction.value === 'reverse') {
      const evidence = evidenceText.value.split(',').map(Number).filter((id) => Number.isInteger(id) && id > 0); if (!evidence.length) throw new Error('核验或冲销必须填写凭据附件 ID')
      if (confirmAction.value === 'reverse') { if (!reversalReason.value.trim()) throw new Error('冲销收款必须填写原因'); replace((await reverseSalesReceipt(target.value.id, target.value.version, reversalReason.value.trim(), evidence)).record) }
      else replace((await verifySalesReceipt(target.value.id, target.value.version, evidence)).record)
      await reloadFinancials()
    } else if (confirmAction.value === 'cancel') { if (!cancellationReason.value.trim()) throw new Error('取消收款必须填写原因'); replace((await cancelSalesReceipt(target.value.id, target.value.version, cancellationReason.value.trim())).record) }
    else replace((await submitSalesReceipt(target.value.id, target.value.version)).record)
    confirmAction.value = null; target.value = null
  } catch (error) { dialogError.value = error instanceof Error ? submitErrorText(error, error.message) : '收款操作失败' }
  finally { submitting.value = false }
}
function action(name: string, raw: Record<string, unknown>) { const row = receipts.value.find((item) => item.id === Number(raw.id)); if (!row) return; if (name === 'edit') openForm(row); else if (['delete', 'submit', 'verify', 'cancel', 'reverse'].includes(name)) ask(name as 'delete' | 'submit' | 'verify' | 'cancel' | 'reverse', row) }
onMounted(load)
</script>

<template>
  <div v-if="pageError" class="page-card table-empty" role="alert">{{ pageError }}<div style="margin-top:12px"><button class="ghost-action" type="button" @click="load">重新加载</button></div></div>
  <DataTablePage v-else :export-resource="tab === 'receivables' ? 'receivables' : 'customer-receipts'" :title="tab === 'receivables' ? '应收账款' : '收款记录'" label="Sales / Receivables" description="应收按核验交付唯一生成；收款支持部分核销、结清和追加式冲销。" create-label="＋ 登记收款" :kpis="kpis"
    :filters="tab === 'receivables' ? [{ key: 'status', type: 'select', label: '全部应收状态', options: Object.entries(receivableLabels).map(([value, label]) => ({ value, label })) }, { key: 'name', type: 'search', placeholder: '搜索销售单 / 客户', wide: true }] : [{ key: 'status', type: 'select', label: '全部收款状态', options: Object.entries(receiptLabels).map(([value, label]) => ({ value, label })) }, { key: 'name', type: 'search', placeholder: '搜索收款单 / 客户', wide: true }]"
    :columns="tab === 'receivables' ? [{ key: 'customer_name', label: '客户', type: 'title', sub: 'order_code' }, { key: 'amount', label: '应收金额', type: 'amount' }, { key: 'received_amount', label: '已收金额', type: 'amount' }, { key: 'balance', label: '未收金额', type: 'number' }, { key: 'due_date', label: '到期日' }, { key: 'term', label: '账期' }, { key: 'lifecycle_label', label: '状态', type: 'badge', tones: receivableTones }] : [{ key: 'code', label: '收款单号', type: 'title', sub: 'name' }, { key: 'customer_name', label: '客户' }, { key: 'amount', label: '收款金额', type: 'amount' }, { key: 'received_at', label: '收款日期' }, { key: 'receipt_method', label: '收款方式' }, { key: 'lifecycle_label', label: '状态', type: 'badge', tones: receiptTones }]"
    :rows="tab === 'receivables' ? receivableRows : receiptRows" action-test-id-prefix="sales-receipt-action" server-side :total="tab === 'receivables' ? receivableMeta.total : receiptMeta.total" :current-page="tab === 'receivables' ? receivableMeta.page : receiptMeta.page" :page-size="tab === 'receivables' ? receivableMeta.page_size : receiptMeta.page_size" :empty-text="loading ? '正在加载应收数据…' : '当前授权范围内暂无记录'" @create="openForm()" @action="action" @query="queryRows">
    <template #tabs><nav class="filter-bar" aria-label="应收与收款视图" style="justify-content:flex-start"><button type="button" :class="tab === 'receivables' ? 'primary-action' : 'ghost-action'" data-testid="sales-tab-receivables" @click="tab = 'receivables'">应收账款</button><button type="button" :class="tab === 'receipts' ? 'primary-action' : 'ghost-action'" data-testid="sales-tab-receipts" @click="tab = 'receipts'">收款记录</button></nav></template>
  </DataTablePage>
  <Teleport to="body">
    <div v-if="formOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="收款记录编辑"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">{{ editing ? 'Edit' : 'Create' }}</p><h2>{{ editing ? '编辑收款记录' : '登记收款' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="formOpen = false">×</button></div><p class="section-subtitle">提交后仍可编辑；核验时必须上传凭据并由不同人员办理。</p><div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))"><label v-for="field in fields" :key="field.key" class="modal-field" :for="`receipt-${field.key}`" :style="field.type === 'textarea' ? 'grid-column:1/-1' : ''"><span>{{ field.label }}{{ field.required ? ' *' : '' }}</span><textarea v-if="field.type === 'textarea'" :id="`receipt-${field.key}`" v-model="form[field.key]" rows="3" class="filter-input" style="width:100%;resize:vertical" /><select v-else-if="field.type === 'receivable'" :id="`receipt-${field.key}`" v-model="form[field.key]" :disabled="Boolean(editing)" class="filter-select" style="width:100%"><option value="" disabled>请选择应收来源</option><option v-for="item in receivableOptions.filter((row) => Number(row.balance) > 0 || row.id === editing?.receivable_id)" :key="item.id" :value="item.id">{{ item.order_code }} · {{ item.customer_name }} · 余额 {{ item.balance }}</option></select><select v-else-if="field.type === 'receipt_method'" :id="`receipt-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%"><option value="" disabled>请选择收款方式</option><option value="bank_transfer">银行转账</option><option value="cash">现金</option><option value="check">支票</option><option value="digital_wallet">电子钱包</option><option value="other">其他</option></select><input v-else :id="`receipt-${field.key}`" v-model="form[field.key]" :type="field.type ?? 'text'" :min="field.type === 'number' ? 0 : undefined" class="filter-input" style="width:100%"></label></div><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="formOpen = false">取消</button><button class="primary-action" type="button" data-testid="receipt-save" :disabled="submitting" :aria-busy="submitting" @click="save">{{ submitting ? '保存中…' : '保存' }}</button></div></div></div>
    <div v-if="confirmAction && target" class="modal-overlay" role="dialog" aria-modal="true" aria-label="收款操作确认"><div class="modal-panel" style="width:min(500px,100%)"><div class="modal-panel__head"><div><p class="section-label">Confirm</p><h2>{{ confirmAction === 'verify' ? '核验收款' : confirmAction === 'reverse' ? '冲销收款' : confirmAction === 'submit' ? '提交核验' : confirmAction === 'cancel' ? '取消收款' : '删除草稿' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="confirmAction = null">×</button></div><p class="section-subtitle">{{ confirmAction === 'verify' ? '核验后收款永久只读，并在同一事务核销应收余额。' : confirmAction === 'reverse' ? '冲销追加反向记录并恢复应收余额，原收款不删除也不改写。' : confirmAction === 'cancel' ? '已提交收款有痕取消，历史仍保留。' : confirmAction === 'submit' ? '提交后仍可编辑，核验待办跟随最新版本。' : '仅未提交收款草稿可以删除。' }}</p><label v-if="confirmAction === 'reverse'" class="modal-field" for="receipt-reversal-reason"><span>冲销原因 *</span><textarea id="receipt-reversal-reason" v-model="reversalReason" rows="3" class="filter-input" style="width:100%;resize:vertical" /></label><EvidencePicker v-if="confirmAction === 'verify' || confirmAction === 'reverse'" v-model="evidenceText" input-id="receipt-evidence" :organization-id="Number((target as Record<string, unknown>).organization_id ?? 1)" :entity-type="entityType" :entity-id="target.id" :refresh-key="attachmentRefreshKey" /><label v-if="confirmAction === 'cancel'" class="modal-field" for="receipt-cancellation-reason"><span>取消原因 *</span><textarea id="receipt-cancellation-reason" v-model="cancellationReason" rows="3" class="filter-input" style="width:100%;resize:vertical" /></label><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="confirmAction = null">返回</button><button class="primary-action" type="button" data-testid="receipt-confirm" :disabled="submitting" :aria-busy="submitting" @click="confirm">{{ submitting ? '处理中…' : '确认' }}</button></div></div></div>
  </Teleport>
</template>
