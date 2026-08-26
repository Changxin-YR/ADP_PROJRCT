<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { submitErrorText, messageWithContext as message } from '../../common/api/errors'
import type { PurchasePayable, PurchasePayment } from '../../common/api/purchase.models'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import EvidencePicker from '../../common/ui/EvidencePicker.vue'

// 写操作防重复提交：busy + disabled + 防抖（BUG-M2-05/BUG-M4-09）
const submitting = ref(false)
import { cancelPurchasePayment, createPurchasePayment, deletePurchasePayment, listPurchasePayables, listPurchasePayments, reversePurchasePayment, submitPurchasePayment, updatePurchasePayment, verifyPurchasePayment } from '../../features/purchase/purchase.service'

const tab = ref<'payables' | 'payments'>('payables')
const payables = ref<PurchasePayable[]>([])
const payments = ref<PurchasePayment[]>([])
const payableMeta = reactive({ page: 1, page_size: 20, total: 0 })
const paymentMeta = reactive({ page: 1, page_size: 20, total: 0 })
const loading = ref(true)
const pageError = ref('')
const dialogError = ref('')
const formOpen = ref(false)
const editing = ref<PurchasePayment | null>(null)
const target = ref<PurchasePayment | null>(null)
const confirmAction = ref<'delete' | 'submit' | 'verify' | 'cancel' | 'reverse' | null>(null)
const evidenceText = ref('')
const entityType = computed(() => 'purchase:payment')
const attachmentRefreshKey = ref(0)

const cancellationReason = ref('')
const reversalReason = ref('')
const form = reactive<Record<string, string | number>>({})
const fields = [
  { key: 'code', label: '付款单号', required: true }, { key: 'name', label: '付款名称', required: true },
  { key: 'payable_id', label: '应付来源', type: 'payable', required: true }, { key: 'amount', label: '付款金额', type: 'number', required: true },
  { key: 'paid_at', label: '付款日期', type: 'date', required: true }, { key: 'payment_method', label: '付款方式', type: 'payment_method', required: true },
  { key: 'note', label: '备注', type: 'textarea' },
]
const payableLabels: Record<string, string> = { unpaid: '未付款', partial: '部分付款', settled: '已结清', overpaid: '多付待处理', disputed: '有争议', cancelled: '已取消' }
const paymentLabels: Record<string, string> = { draft: '草稿', submitted: '待核验', verified: '已核验', cancelled: '已取消' }
const payableTones = { 未付款: 'rose', 部分付款: 'amber', 已结清: 'teal', 多付待处理: 'rose', 有争议: 'rose', 已取消: 'slate' } as const
const paymentTones = { 草稿: 'slate', 待核验: 'amber', 已核验: 'teal', 已冲销: 'slate', 已取消: 'slate' } as const
const payableRows = computed(() => payables.value.map((row) => ({ ...row, lifecycle_label: payableLabels[row.status] ?? row.status, term: row.overdue_days > 0 ? `逾期 ${row.overdue_days} 天` : `剩余 ${Math.abs(row.overdue_days)} 天` })))
const paymentRows = computed(() => payments.value.map((row) => ({ ...row, lifecycle_label: row.reversal_id ? '已冲销' : paymentLabels[row.status] ?? row.status })))
const payableKpis = computed(() => [
  { label: '应付总额', value: payables.value.reduce((sum, row) => sum + Number(row.amount), 0), hint: `${payables.value.length} 笔到货应付` },
  { label: '未付余额', value: payables.value.reduce((sum, row) => sum + Number(row.balance), 0), tone: 'amber' as const, hint: '付款核验后实时核销' },
  { label: '已结清', value: payables.value.filter((row) => row.status === 'settled').length, unit: '笔', tone: 'teal' as const, hint: '保留完整付款历史' },
])
const paymentKpis = computed(() => [
  { label: '付款记录', value: payments.value.length, unit: '笔', hint: '当前授权范围' },
  { label: '待核验', value: payments.value.filter((row) => row.status === 'submitted').length, unit: '笔', tone: 'amber' as const, hint: '经办与核验必须分离' },
  { label: '已核验', value: payments.value.filter((row) => row.status === 'verified' && !row.reversal_id).length, unit: '笔', tone: 'teal' as const, hint: '核验后只读' },
])

async function load() {
  loading.value = true; pageError.value = ''
  try {
    const [payablePage, paymentPage] = await Promise.all([listPurchasePayables(), listPurchasePayments()])
    payables.value = payablePage.items; payments.value = paymentPage.items
    Object.assign(payableMeta, payablePage); Object.assign(paymentMeta, paymentPage)
  } catch (error) { payables.value = []; payments.value = []; pageError.value = message(error, '应付与付款数据加载失败') }
  finally { loading.value = false }
}
async function queryRows(query: Record<string, string | number>) {
  loading.value = true; pageError.value = ''
  try {
    const common = { page: Number(query.page), page_size: Number(query.page_size), status: String(query.status ?? '') }
    if (tab.value === 'payables') {
      const result = await listPurchasePayables({ ...common, search: String(query.supplier_name ?? '') })
      payables.value = result.items; Object.assign(payableMeta, result)
    } else {
      const result = await listPurchasePayments({ ...common, search: String(query.name ?? '') })
      payments.value = result.items; Object.assign(paymentMeta, result)
    }
  } catch (error) { pageError.value = message(error, '应付与付款数据加载失败') }
  finally { loading.value = false }
}
function openForm(row?: PurchasePayment) {
  editing.value = row ?? null; dialogError.value = ''
  for (const field of fields) form[field.key] = (row?.[field.key as keyof PurchasePayment] as string | number) ?? ''
  formOpen.value = true
}
function body() {
  const payload: Record<string, unknown> = {}
  for (const field of fields) {
    if (editing.value && field.key === 'payable_id') continue
    const value = form[field.key]
    if (field.required && !String(value ?? '').trim()) throw new Error(`请填写${field.label}`)
    if (value !== '') payload[field.key] = ['number', 'payable'].includes(field.type ?? '') ? Number(value) : String(value).trim()
  }
  return payload
}
function replace(row: PurchasePayment) {
  const index = payments.value.findIndex((item) => item.id === row.id)
  if (index < 0) payments.value.unshift(row); else payments.value[index] = row
}
async function save() {
  if (submitting.value) return
  submitting.value = true
  dialogError.value = ''
  try {
    const payload = body()
    const result = editing.value
      ? await updatePurchasePayment(editing.value.id, { ...payload, expected_version: editing.value.version })
      : await createPurchasePayment(payload)
    replace(result.record); formOpen.value = false; tab.value = 'payments'
  } catch (error) { dialogError.value = error instanceof Error ? submitErrorText(error, error.message) : '付款记录保存失败' }
  finally { submitting.value = false }
}
function ask(action: 'delete' | 'submit' | 'verify' | 'cancel' | 'reverse', row: PurchasePayment) {
  target.value = row; confirmAction.value = action; evidenceText.value = ''; cancellationReason.value = ''; reversalReason.value = ''; dialogError.value = ''
}
async function confirm() {
  if (submitting.value) return
  submitting.value = true
  if (!target.value || !confirmAction.value) return
  dialogError.value = ''
  try {
    if (confirmAction.value === 'delete') { await deletePurchasePayment(target.value.id); payments.value = payments.value.filter((row) => row.id !== target.value!.id) }
    else if (confirmAction.value === 'verify' || confirmAction.value === 'reverse') {
      const evidence = evidenceText.value.split(',').map((item) => Number(item.trim())).filter((item) => Number.isInteger(item) && item > 0)
      if (!evidence.length) throw new Error(`${confirmAction.value === 'reverse' ? '付款冲销' : '付款核验'}必须填写凭据附件 ID`)
      if (confirmAction.value === 'reverse') {
        if (!reversalReason.value.trim()) throw new Error('冲销付款必须填写原因')
        replace((await reversePurchasePayment(target.value.id, target.value.version, reversalReason.value.trim(), evidence)).record)
      } else replace((await verifyPurchasePayment(target.value.id, target.value.version, evidence)).record)
    } else if (confirmAction.value === 'cancel') {
      if (!cancellationReason.value.trim()) throw new Error('取消付款必须填写原因')
      replace((await cancelPurchasePayment(target.value.id, target.value.version, cancellationReason.value.trim())).record)
    } else replace((await submitPurchasePayment(target.value.id, target.value.version)).record)
    confirmAction.value = null; target.value = null
  } catch (error) { dialogError.value = error instanceof Error ? submitErrorText(error, error.message) : '付款操作失败' }
  finally { submitting.value = false }
}
function action(name: string, raw: Record<string, unknown>) {
  const row = payments.value.find((item) => item.id === Number(raw.id)); if (!row) return
  if (name === 'edit') openForm(row)
  else if (name === 'delete' || name === 'submit' || name === 'verify' || name === 'cancel' || name === 'reverse') ask(name, row)
}
onMounted(load)
</script>

<template>
  <div v-if="pageError" class="page-card table-empty" role="alert">{{ pageError }}<div style="margin-top:12px"><button class="ghost-action" type="button" @click="load">重新加载</button></div></div>
  <DataTablePage v-else :export-resource="tab === 'payables' ? 'payables' : 'payments'" :title="tab === 'payables' ? '应付账款' : '付款记录'" label="Purchase / Payables" description="应付按核验到货唯一生成；付款支持部分核销与结清。" create-label="＋ 登记付款" :kpis="tab === 'payables' ? payableKpis : paymentKpis"
    :filters="tab === 'payables' ? [{ key: 'status', type: 'select', label: '全部应付状态', options: Object.entries(payableLabels).map(([value, label]) => ({ value, label })) }, { key: 'supplier_name', type: 'search', placeholder: '搜索采购单 / 供应商', wide: true }] : [{ key: 'status', type: 'select', label: '全部付款状态', options: Object.entries(paymentLabels).map(([value, label]) => ({ value, label })) }, { key: 'name', type: 'search', placeholder: '搜索付款单 / 供应商', wide: true }]"
    :columns="tab === 'payables' ? [{ key: 'supplier_name', label: '供应商', type: 'title', sub: 'order_code' }, { key: 'amount', label: '应付金额', type: 'amount' }, { key: 'paid_amount', label: '已付金额', type: 'amount' }, { key: 'balance', label: '未付余额', type: 'amount' }, { key: 'due_date', label: '到期日' }, { key: 'term', label: '账期' }, { key: 'lifecycle_label', label: '状态', type: 'badge', tones: payableTones }] : [{ key: 'code', label: '付款单号', type: 'title', sub: 'name' }, { key: 'supplier_name', label: '供应商' }, { key: 'amount', label: '付款金额', type: 'amount' }, { key: 'paid_at', label: '付款日期' }, { key: 'lifecycle_label', label: '状态', type: 'badge', tones: paymentTones }]"
    :rows="tab === 'payables' ? payableRows : paymentRows" action-test-id-prefix="purchase-payment-action" server-side :total="tab === 'payables' ? payableMeta.total : paymentMeta.total" :current-page="tab === 'payables' ? payableMeta.page : paymentMeta.page" :page-size="tab === 'payables' ? payableMeta.page_size : paymentMeta.page_size" :empty-text="loading ? '正在加载应付数据…' : '当前授权范围内暂无记录'" @create="openForm()" @action="action" @query="queryRows">
    <template #tabs><nav class="filter-bar" aria-label="应付与付款视图" style="justify-content:flex-start"><button type="button" :class="tab === 'payables' ? 'primary-action' : 'ghost-action'" data-testid="purchase-tab-payables" @click="tab = 'payables'">应付账款</button><button type="button" :class="tab === 'payments' ? 'primary-action' : 'ghost-action'" data-testid="purchase-tab-payments" @click="tab = 'payments'">付款记录</button></nav></template>
  </DataTablePage>
  <Teleport to="body">
    <div v-if="formOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="付款记录编辑"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">{{ editing ? 'Edit' : 'Create' }}</p><h2>{{ editing ? '编辑付款记录' : '登记付款' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="formOpen = false">×</button></div><p class="section-subtitle">付款可分次登记；核验时必须上传凭据并由不同人员办理。</p><div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))"><label v-for="field in fields" :key="field.key" class="modal-field" :for="`payment-${field.key}`" :style="field.type === 'textarea' ? 'grid-column:1/-1' : ''"><span>{{ field.label }}{{ field.required ? ' *' : '' }}</span><textarea v-if="field.type === 'textarea'" :id="`payment-${field.key}`" v-model="form[field.key]" rows="3" class="filter-input" style="width:100%;resize:vertical" /><select v-else-if="field.type === 'payable'" :id="`payment-${field.key}`" v-model="form[field.key]" :disabled="Boolean(editing)" class="filter-select" style="width:100%"><option value="" disabled>请选择应付来源</option><option v-for="item in payables.filter((row) => Number(row.balance) > 0 || row.id === editing?.payable_id)" :key="item.id" :value="item.id">{{ item.order_code }} · {{ item.supplier_name }} · 余额 {{ item.balance }}</option></select><select v-else-if="field.type === 'payment_method'" :id="`payment-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%"><option value="" disabled>请选择付款方式</option><option value="bank_transfer">银行转账</option><option value="cash">现金</option><option value="check">支票</option><option value="digital_wallet">电子钱包</option><option value="other">其他</option></select><input v-else :id="`payment-${field.key}`" v-model="form[field.key]" :type="field.type ?? 'text'" :min="field.type === 'number' ? 0 : undefined" class="filter-input" style="width:100%"></label></div><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="formOpen = false">取消</button><button class="primary-action" type="button" data-testid="payment-save" :disabled="submitting" :aria-busy="submitting" @click="save">{{ submitting ? '保存中…' : '保存' }}</button></div></div></div>
    <div v-if="confirmAction && target" class="modal-overlay" role="dialog" aria-modal="true" aria-label="付款操作确认"><div class="modal-panel" style="width:min(500px,100%)"><div class="modal-panel__head"><div><p class="section-label">Confirm</p><h2>{{ confirmAction === 'verify' ? '核验付款' : confirmAction === 'reverse' ? '冲销付款' : confirmAction === 'submit' ? '提交核验' : confirmAction === 'cancel' ? '取消付款' : '删除草稿' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="confirmAction = null">×</button></div><p class="section-subtitle">{{ confirmAction === 'verify' ? '核验后付款只读，并在同一事务核销应付余额。' : confirmAction === 'reverse' ? '冲销将追加反向流水并恢复应付余额，原付款不会删除或改写。' : confirmAction === 'cancel' ? '已提交付款将有痕取消，历史仍保留。' : confirmAction === 'submit' ? '提交后仍可编辑，核验待办跟随最新版本。' : '仅未提交付款草稿可以删除。' }}</p><label v-if="confirmAction === 'reverse'" class="modal-field" for="payment-reversal-reason"><span>冲销原因 *</span><textarea id="payment-reversal-reason" v-model="reversalReason" rows="3" class="filter-input" style="width:100%;resize:vertical" /></label><EvidencePicker v-if="confirmAction === 'verify' || confirmAction === 'reverse'" v-model="evidenceText" input-id="payment-evidence" :organization-id="Number((target as Record<string, unknown>).organization_id ?? 1)" :entity-type="entityType" :entity-id="target.id" :refresh-key="attachmentRefreshKey" /><label v-if="confirmAction === 'cancel'" class="modal-field" for="payment-cancellation-reason"><span>取消原因 *</span><textarea id="payment-cancellation-reason" v-model="cancellationReason" rows="3" class="filter-input" style="width:100%;resize:vertical" /></label><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="confirmAction = null">返回</button><button class="primary-action" type="button" data-testid="payment-confirm" :disabled="submitting" :aria-busy="submitting" @click="confirm">{{ submitting ? '处理中…' : '确认' }}</button></div></div></div>
  </Teleport>
</template>
