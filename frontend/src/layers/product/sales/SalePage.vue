<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ApiError, submitErrorText } from '../../common/api/errors'
import type { MasterRecord } from '../../common/api/master-data.models'
import type { ProductionRecord } from '../../common/api/production.models'
import type { SalesDelivery, SalesOrder } from '../../common/api/sales.models'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import { clearOfflineDraft, loadOfflineDraft, saveOfflineDraft } from '../../common/ui/offlineDraft'
import EvidencePicker from '../../common/ui/EvidencePicker.vue'
import { listMasterOptions } from '../../features/master-data/master-data.service'
import { listProductionRecords } from '../../features/production/production.service'

// 写操作防重复提交：busy + disabled + 防抖（BUG-M2-05/BUG-M4-09）
const submitting = ref(false)
import { approveSalesOrder, cancelSalesDelivery, cancelSalesOrder, correctSalesDelivery, createSalesDelivery, createSalesOrder, deleteSalesDelivery, deleteSalesOrder, listSalesDeliveries, listSalesOrders, submitSalesDelivery, submitSalesOrder, updateSalesDelivery, updateSalesOrder, verifySalesDelivery } from '../../features/sales/sales.service'

const tab = ref<'orders' | 'deliveries'>('orders')
const orders = ref<SalesOrder[]>([]), deliveries = ref<SalesDelivery[]>([])
const orderOptions = ref<SalesOrder[]>([])
const orderMeta = reactive({ page: 1, page_size: 20, total: 0 }), deliveryMeta = reactive({ page: 1, page_size: 20, total: 0 })
const customers = ref<MasterRecord[]>([]), ponds = ref<MasterRecord[]>([]), batches = ref<ProductionRecord[]>([]), harvests = ref<ProductionRecord[]>([])
const loading = ref(true), pageError = ref(''), dialogError = ref(''), formOpen = ref(false)
const draftNotice = ref('')
const editingOrder = ref<SalesOrder | null>(null), editingDelivery = ref<SalesDelivery | null>(null), correcting = ref<SalesDelivery | null>(null)
const target = ref<SalesOrder | SalesDelivery | null>(null), targetKind = ref<'order' | 'delivery'>('order')
const confirmAction = ref<'delete' | 'submit' | 'approve' | 'verify' | 'cancel' | null>(null)
const form = reactive<Record<string, string | number>>({})
const draftScope = computed(() => `sales:${tab.value}`)
const entityType = computed(() => 'sales:delivery')
const attachmentRefreshKey = ref(0)
, evidenceText = ref(''), cancellationReason = ref(''), correctionReason = ref('')
interface FormField { key: string; label: string; type?: string; required?: boolean; options?: Array<{ value: number; label: string }> }
const option = (row: { id: number; code: string; name: string }) => ({ value: row.id, label: `${row.code} · ${row.name}` })
const orderFields = computed<FormField[]>(() => [
  { key: 'code', label: '销售单号', required: true }, { key: 'name', label: '销售名称', required: true },
  { key: 'customer_id', label: '客户', type: 'select', required: true, options: customers.value.map(option) },
  { key: 'pond_id', label: '塘口', type: 'select', required: true, options: ponds.value.map(option) },
  { key: 'batch_id', label: '养殖批次', type: 'select', required: true, options: batches.value.map(option) },
  { key: 'species', label: '品种', required: true }, { key: 'quantity', label: '销售数量', type: 'number', required: true },
  { key: 'unit', label: '单位', type: 'unit', required: true }, { key: 'unit_price', label: '销售单价', type: 'number', required: true },
  { key: 'sold_at', label: '销售日期', type: 'date', required: true }, { key: 'due_date', label: '收款到期日', type: 'date', required: true },
  { key: 'note', label: '备注', type: 'textarea' },
])
const deliveryFields = computed<FormField[]>(() => [
  { key: 'code', label: '交付单号', required: true }, { key: 'name', label: '交付名称', required: true },
  { key: 'sales_order_id', label: '销售来源', type: 'order', required: true, options: orderOptions.value.filter((row) => ['approved', 'partially_delivered'].includes(row.status)).map((row) => ({ value: row.id, label: `${row.code} · ${row.customer_name ?? row.name}` })) },
  { key: 'harvest_document_id', label: '已核验出塘单', type: 'harvest', required: true, options: harvests.value.map(option) },
  { key: 'quantity', label: '交付数量', type: 'number', required: true }, { key: 'delivered_at', label: '交付时间', type: 'datetime-local', required: true },
  { key: 'transport_info', label: '运输或提货信息' }, { key: 'acceptance_note', label: '客户验收与差异', type: 'textarea' },
])
const orderLabels: Record<string, string> = { draft: '草稿', submitted: '待审批', approved: '待交付', partially_delivered: '部分交付', fully_delivered: '已交付', closed: '已关闭', cancelled: '已取消', disputed: '有争议' }
const deliveryLabels: Record<string, string> = { draft: '草稿', submitted: '待核验', verified: '已核验', cancelled: '已取消' }
const tones = { 草稿: 'slate', 待审批: 'amber', 待交付: 'blue', 部分交付: 'amber', 已交付: 'teal', 已关闭: 'teal', 已取消: 'slate', 有争议: 'rose', 待核验: 'amber', 已核验: 'teal' } as const
const orderRows = computed(() => orders.value.map((row) => ({ ...row, lifecycle_label: orderLabels[row.status] ?? row.status, balance: Number(row.receivable_amount || 0) - Number(row.received_amount || 0) })))
const deliveryRows = computed(() => deliveries.value.map((row) => ({ ...row, lifecycle_label: deliveryLabels[row.status] ?? row.status })))
const kpis = computed(() => tab.value === 'orders' ? [
  { label: '销售单', value: orderMeta.total, unit: '张', hint: '当前授权范围' },
  { label: '待审批', value: orders.value.filter((row) => row.status === 'submitted').length, unit: '张', tone: 'amber' as const, hint: '提交后仍可编辑' },
  { label: '待交付', value: orders.value.filter((row) => ['approved', 'partially_delivered'].includes(row.status)).length, unit: '张', tone: 'blue' as const, hint: '必须关联已核验出塘' },
] : [
  { label: '交付单', value: deliveryMeta.total, unit: '张', hint: '交付与出塘分开记账' },
  { label: '待核验', value: deliveries.value.filter((row) => row.status === 'submitted').length, unit: '张', tone: 'amber' as const, hint: '核验后形成应收' },
  { label: '已核验', value: deliveries.value.filter((row) => row.status === 'verified').length, unit: '张', tone: 'teal' as const, hint: '核验后只读' },
])

const message = (error: unknown, fallback: string) => error instanceof ApiError ? `${fallback}：${error.message}` : fallback
async function allPages<T>(loadPage: (page: number) => Promise<{ items: T[]; has_next: boolean }>) {
  const items: T[] = []
  for (let page = 1; ; page += 1) {
    const result = await loadPage(page); items.push(...result.items)
    if (!result.has_next) return items
    if (!result.items.length) throw new Error('选项分页返回空页')
  }
}
async function load() {
  loading.value = true; pageError.value = ''
  try {
    const [orderPage, deliveryPage, customerRows, pondRows, batchRows, harvestRows, optionRows] = await Promise.all([
      listSalesOrders(), listSalesDeliveries(), allPages((page) => listMasterOptions('customers', page)), allPages((page) => listMasterOptions('ponds', page)),
      allPages((page) => listProductionRecords('batches', { page, page_size: 100, status: 'verified' })), allPages((page) => listProductionRecords('harvests', { page, page_size: 100, status: 'verified' })),
      allPages((page) => listSalesOrders({ page, page_size: 100 })),
    ])
    orders.value = orderPage.items; deliveries.value = deliveryPage.items; Object.assign(orderMeta, orderPage); Object.assign(deliveryMeta, deliveryPage)
    customers.value = customerRows; ponds.value = pondRows; batches.value = batchRows; harvests.value = harvestRows; orderOptions.value = optionRows
  } catch (error) { orders.value = []; deliveries.value = []; pageError.value = message(error, '销售数据加载失败') }
  finally { loading.value = false }
}
async function queryRows(query: Record<string, string | number>) {
  loading.value = true; pageError.value = ''
  try {
    const params = { page: Number(query.page), page_size: Number(query.page_size), status: String(query.status ?? ''), search: String(query.name ?? ''), sort_by: String(query.sort_by ?? ''), sort_dir: String(query.sort_dir ?? '') as 'asc' | 'desc' }
    if (tab.value === 'orders') { const page = await listSalesOrders(params); orders.value = page.items; Object.assign(orderMeta, page) }
    else { const page = await listSalesDeliveries(params); deliveries.value = page.items; Object.assign(deliveryMeta, page) }
  } catch (error) { pageError.value = message(error, '销售数据加载失败') }
  finally { loading.value = false }
}
function setForm(fields: Array<{ key: string }>, row?: Record<string, unknown>) { for (const field of fields) form[field.key] = (row?.[field.key] as string | number) ?? '' }
function openOrder(row?: SalesOrder) { editingOrder.value = row ?? null; editingDelivery.value = null; correcting.value = null; dialogError.value = ''; draftNotice.value = ''; setForm(orderFields.value, row as unknown as Record<string, unknown>); if (!row) { const draft = loadOfflineDraft<Record<string, string | number>>(draftScope.value); if (draft) { Object.assign(form, draft.payload); draftNotice.value = '已恢复本地草稿，保存后将清除本地副本。' } } formOpen.value = true }
function openDelivery(row?: SalesDelivery, correction = false, order?: SalesOrder) {
  editingOrder.value = null; editingDelivery.value = correction ? null : row ?? null; correcting.value = correction ? row ?? null : null; correctionReason.value = ''; dialogError.value = ''; draftNotice.value = ''
  setForm(deliveryFields.value, row as unknown as Record<string, unknown>); if (order) form.sales_order_id = order.id
  if (!row && !correction && !order) { const draft = loadOfflineDraft<Record<string, string | number>>(draftScope.value); if (draft) { Object.assign(form, draft.payload); draftNotice.value = '已恢复本地草稿，保存后将清除本地副本。' } }
  formOpen.value = true
}
function discardDraft() { clearOfflineDraft(draftScope.value); draftNotice.value = ''; formOpen.value = false }
function body(fields: Array<{ key: string; label: string; type?: string; required?: boolean }>, skip: string[] = []) {
  const payload: Record<string, unknown> = {}
  for (const field of fields) { if (skip.includes(field.key)) continue; const value = form[field.key]; if (field.required && !String(value ?? '').trim()) throw new Error(`请填写${field.label}`); if (value !== '') payload[field.key] = ['number', 'select', 'order', 'harvest'].includes(field.type ?? '') ? Number(value) : String(value).trim() }
  return payload
}
function replaceOrder(row: SalesOrder) {
  const index = orders.value.findIndex((item) => item.id === row.id); if (index < 0) orders.value.unshift(row); else orders.value[index] = row
  const optionIndex = orderOptions.value.findIndex((item) => item.id === row.id); if (optionIndex < 0) orderOptions.value.unshift(row); else orderOptions.value[optionIndex] = row
}
function replaceDelivery(row: SalesDelivery) { const index = deliveries.value.findIndex((item) => item.id === row.id); if (index < 0) deliveries.value.unshift(row); else deliveries.value[index] = row }
async function reloadSalesFacts() {
  const [orderPage, deliveryPage, optionRows] = await Promise.all([listSalesOrders(), listSalesDeliveries(), allPages((page) => listSalesOrders({ page, page_size: 100 }))])
  orders.value = orderPage.items; deliveries.value = deliveryPage.items; orderOptions.value = optionRows; Object.assign(orderMeta, orderPage); Object.assign(deliveryMeta, deliveryPage)
}
async function save() {
  if (submitting.value) return
  submitting.value = true
  dialogError.value = ''
  try {
    const scope = draftScope.value
    if (editingOrder.value || (!editingDelivery.value && !correcting.value && tab.value === 'orders')) {
      const payload = body(orderFields.value); const result = editingOrder.value ? await updateSalesOrder(editingOrder.value.id, { ...payload, expected_version: editingOrder.value.version }) : await createSalesOrder(payload); replaceOrder(result.record)
    } else {
      const payload = body(deliveryFields.value, editingDelivery.value || correcting.value ? ['sales_order_id'] : [])
      if (correcting.value && !correctionReason.value.trim()) throw new Error('更正交付必须填写原因')
      const result = correcting.value ? await correctSalesDelivery(correcting.value.id, { ...payload, expected_version: correcting.value.version, correction_reason: correctionReason.value.trim() }) : editingDelivery.value ? await updateSalesDelivery(editingDelivery.value.id, { ...payload, expected_version: editingDelivery.value.version }) : await createSalesDelivery(payload)
      replaceDelivery(result.record); tab.value = 'deliveries'
    }
    formOpen.value = false
    if (!editingOrder.value && !editingDelivery.value && !correcting.value) clearOfflineDraft(scope)
  } catch (error) { dialogError.value = error instanceof Error ? submitErrorText(error, error.message) : '销售记录保存失败' }
  finally { submitting.value = false }
}
function ask(kind: 'order' | 'delivery', action: 'delete' | 'submit' | 'approve' | 'verify' | 'cancel', row: SalesOrder | SalesDelivery) { targetKind.value = kind; target.value = row; confirmAction.value = action; evidenceText.value = ''; cancellationReason.value = ''; dialogError.value = '' }
async function confirm() {
  if (submitting.value) return
  submitting.value = true
  if (!target.value || !confirmAction.value) return
  try {
    if (targetKind.value === 'order') {
      const row = target.value as SalesOrder
      if (confirmAction.value === 'delete') { await deleteSalesOrder(row.id); orders.value = orders.value.filter((item) => item.id !== row.id) }
      else if (confirmAction.value === 'cancel') { if (!cancellationReason.value.trim()) throw new Error('取消销售单必须填写原因'); replaceOrder((await cancelSalesOrder(row.id, row.version, cancellationReason.value.trim())).record) }
      else replaceOrder((confirmAction.value === 'submit' ? await submitSalesOrder(row.id, row.version) : await approveSalesOrder(row.id, row.version)).record)
    } else {
      const row = target.value as SalesDelivery
      if (confirmAction.value === 'delete') { await deleteSalesDelivery(row.id); deliveries.value = deliveries.value.filter((item) => item.id !== row.id) }
      else if (confirmAction.value === 'verify') { const evidence = evidenceText.value.split(',').map(Number).filter((id) => Number.isInteger(id) && id > 0); if (!evidence.length) throw new Error('交付核验必须填写凭据附件 ID'); replaceDelivery((await verifySalesDelivery(row.id, row.version, evidence)).record); await reloadSalesFacts() }
      else if (confirmAction.value === 'cancel') { if (!cancellationReason.value.trim()) throw new Error('取消交付必须填写原因'); replaceDelivery((await cancelSalesDelivery(row.id, row.version, cancellationReason.value.trim())).record) }
      else replaceDelivery((await submitSalesDelivery(row.id, row.version)).record)
    }
    confirmAction.value = null; target.value = null
  } catch (error) { dialogError.value = error instanceof Error ? submitErrorText(error, error.message) : '销售操作失败' }
  finally { submitting.value = false }
}
function action(name: string, raw: Record<string, unknown>) {
  if (tab.value === 'orders') { const row = orders.value.find((item) => item.id === Number(raw.id)); if (!row) return; if (name === 'edit') openOrder(row); else if (name === 'deliver') openDelivery(undefined, false, row); else if (['delete', 'submit', 'approve', 'cancel'].includes(name)) ask('order', name as 'delete' | 'submit' | 'approve' | 'cancel', row) }
  else { const row = deliveries.value.find((item) => item.id === Number(raw.id)); if (!row) return; if (name === 'edit') openDelivery(row); else if (name === 'correct') openDelivery(row, true); else if (['delete', 'submit', 'verify', 'cancel'].includes(name)) ask('delivery', name as 'delete' | 'submit' | 'verify' | 'cancel', row) }
}
onMounted(load)
watch(form, (value) => {
  if (formOpen.value && !editingOrder.value && !editingDelivery.value && !correcting.value && Object.values(value).some((item) => String(item ?? '').trim())) saveOfflineDraft(draftScope.value, { ...value })
}, { deep: true })
</script>

<template>
  <div v-if="pageError" class="page-card table-empty" role="alert">{{ pageError }}<div style="margin-top:12px"><button class="ghost-action" type="button" @click="load">重新加载</button></div></div>
  <DataTablePage v-else :export-resource="tab === 'orders' ? 'sales-orders' : 'sales-deliveries'" :title="tab === 'orders' ? '销售明细' : '销售交付'" label="Sales / Orders" description="销售交易与出塘事实分别留痕；交付核验后按有效数量形成应收，不重复扣减批次存量。" :create-label="tab === 'orders' ? '＋ 新建销售单' : '＋ 登记交付'" :kpis="kpis"
    :filters="[{ key: 'status', type: 'select', label: '全部业务状态', options: Object.entries(tab === 'orders' ? orderLabels : deliveryLabels).map(([value, label]) => ({ value, label })) }, { key: 'name', type: 'search', placeholder: '搜索单号 / 客户 / 塘口', wide: true }]"
    :columns="tab === 'orders' ? [{ key: 'code', label: '销售单号', type: 'title', sub: 'name' }, { key: 'customer_name', label: '客户' }, { key: 'pond_name', label: '塘口', type: 'title', sub: 'batch_code' }, { key: 'species', label: '品种' }, { key: 'quantity', label: '销售数量', type: 'number' }, { key: 'delivered_quantity', label: '已交付', type: 'number' }, { key: 'total_amount', label: '金额', type: 'amount' }, { key: 'balance', label: '待收', type: 'amount' }, { key: 'lifecycle_label', label: '状态', type: 'badge', tones }] : [{ key: 'code', label: '交付单号', type: 'title', sub: 'name' }, { key: 'order_code', label: '销售来源' }, { key: 'customer_name', label: '客户' }, { key: 'quantity', label: '交付数量', type: 'number' }, { key: 'delivered_at', label: '交付时间' }, { key: 'harvest_document_id', label: '出塘单 ID', type: 'number' }, { key: 'lifecycle_label', label: '状态', type: 'badge', tones }]"
    :rows="tab === 'orders' ? orderRows : deliveryRows" :action-test-id-prefix="tab === 'orders' ? 'sales-order-action' : 'sales-delivery-action'" server-side :total="tab === 'orders' ? orderMeta.total : deliveryMeta.total" :current-page="tab === 'orders' ? orderMeta.page : deliveryMeta.page" :page-size="tab === 'orders' ? orderMeta.page_size : deliveryMeta.page_size" :empty-text="loading ? '正在加载销售数据…' : '当前授权范围内暂无记录'" @create="tab === 'orders' ? openOrder() : openDelivery()" @action="action" @query="queryRows">
    <template #tabs><nav class="filter-bar" aria-label="销售与交付视图" style="justify-content:flex-start"><button type="button" :class="tab === 'orders' ? 'primary-action' : 'ghost-action'" data-testid="sales-tab-orders" @click="tab = 'orders'">销售单</button><button type="button" :class="tab === 'deliveries' ? 'primary-action' : 'ghost-action'" data-testid="sales-tab-deliveries" @click="tab = 'deliveries'">交付记录</button></nav></template>
  </DataTablePage>
  <Teleport to="body">
    <p v-if="formOpen && draftNotice" class="offline-draft-notice" role="status">{{ draftNotice }} <button type="button" data-testid="sales-discard-draft" @click="discardDraft">丢弃本地草稿</button></p>
    <div v-if="formOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="销售记录编辑"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">{{ correcting ? 'Correction' : editingOrder || editingDelivery ? 'Edit' : 'Create' }}</p><h2>{{ correcting ? '更正交付记录' : tab === 'orders' ? (editingOrder ? '编辑销售单' : '新增销售单') : (editingDelivery ? '编辑交付' : '登记交付') }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="formOpen = false">×</button></div><p class="section-subtitle">提交后仍可编辑并递增版本；审批或核验后业务字段只读，只能查看或有痕更正。</p><div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))"><label v-for="field in (editingOrder || (!editingDelivery && !correcting && tab === 'orders') ? orderFields : deliveryFields)" :key="field.key" class="modal-field" :for="`sales-${field.key}`" :style="field.type === 'textarea' ? 'grid-column:1/-1' : ''"><span>{{ field.label }}{{ field.required ? ' *' : '' }}</span><textarea v-if="field.type === 'textarea'" :id="`sales-${field.key}`" v-model="form[field.key]" rows="3" class="filter-input" style="width:100%;resize:vertical" /><select v-else-if="['select', 'order', 'harvest'].includes(field.type ?? '')" :id="`sales-${field.key}`" v-model="form[field.key]" :disabled="field.type === 'order' && Boolean(editingDelivery || correcting)" class="filter-select" style="width:100%"><option value="" disabled>请选择{{ field.label }}</option><option v-for="item in field.options" :key="item.value" :value="item.value">{{ item.label }}</option></select><select v-else-if="field.type === 'unit'" :id="`sales-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%"><option value="kg">千克</option><option value="jin">斤</option><option value="tail">尾</option></select><input v-else :id="`sales-${field.key}`" v-model="form[field.key]" :type="field.type ?? 'text'" :min="field.type === 'number' ? 0 : undefined" class="filter-input" style="width:100%"></label><label v-if="correcting" class="modal-field" for="sales-correction-reason" style="grid-column:1/-1"><span>更正原因 *</span><textarea id="sales-correction-reason" v-model="correctionReason" rows="3" class="filter-input" style="width:100%;resize:vertical" /></label></div><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="formOpen = false">取消</button><button class="primary-action" type="button" data-testid="sales-save" :disabled="submitting" :aria-busy="submitting" @click="save">{{ submitting ? '保存中…' : '保存' }}</button></div></div></div>
    <div v-if="confirmAction && target" class="modal-overlay" role="dialog" aria-modal="true" aria-label="销售操作确认"><div class="modal-panel" style="width:min(500px,100%)"><div class="modal-panel__head"><div><p class="section-label">Confirm</p><h2>{{ confirmAction === 'approve' ? '审批销售单' : confirmAction === 'verify' ? '核验交付' : confirmAction === 'submit' ? '提交审核' : confirmAction === 'cancel' ? '取消记录' : '删除草稿' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="confirmAction = null">×</button></div><p class="section-subtitle">{{ confirmAction === 'verify' ? '核验后交付永久只读，并在同一事务生成应收；批次库存仍只由出塘事实扣减。' : confirmAction === 'approve' ? '审批销售交易，不直接确认应收或扣减批次库存。' : confirmAction === 'cancel' ? '取消会保留单据与原因，不删除正式数据。' : confirmAction === 'submit' ? '提交后仍可编辑，待办跟随最新版本。' : '仅无引用的未提交草稿可以删除。' }}</p><EvidencePicker v-if="confirmAction === 'verify'" v-model="evidenceText" input-id="sales-evidence" :organization-id="Number((target as Record<string, unknown>).organization_id ?? 1)" :entity-type="entityType" :entity-id="target.id" :refresh-key="attachmentRefreshKey" /><label v-if="confirmAction === 'cancel'" class="modal-field" for="sales-cancellation-reason"><span>取消原因 *</span><textarea id="sales-cancellation-reason" v-model="cancellationReason" rows="3" class="filter-input" style="width:100%;resize:vertical" /></label><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="confirmAction = null">返回</button><button class="primary-action" type="button" data-testid="sales-confirm" :disabled="submitting" :aria-busy="submitting" @click="confirm">{{ submitting ? '处理中…' : '确认' }}</button></div></div></div>
  </Teleport>
</template>
