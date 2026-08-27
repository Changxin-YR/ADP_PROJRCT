<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { submitErrorText, messageWithContext as message } from '../../common/api/errors'
import type { MasterRecord } from '../../common/api/master-data.models'
import type { PurchaseOrder } from '../../common/api/purchase.models'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import { listAllMasterOptions } from '../../features/master-data/master-data.service'
import { approvePurchaseOrder, cancelPurchaseOrder, createPurchaseOrder, deletePurchaseOrder, listPurchaseOrders, submitPurchaseOrder, updatePurchaseOrder } from '../../features/purchase/purchase.service'

// 写操作防重复提交：busy + disabled + 防抖（BUG-M2-05/BUG-M4-09）
const submitting = ref(false)
import { listWarehouseOptions } from '../../features/warehouse/warehouse.service'

const rows = ref<PurchaseOrder[]>([])
const pageMeta = reactive({ page: 1, page_size: 20, total: 0 })
const loading = ref(true)
const pageError = ref('')
const dialogError = ref('')
const formOpen = ref(false)
const editing = ref<PurchaseOrder | null>(null)
const target = ref<PurchaseOrder | null>(null)
const confirmAction = ref<'delete' | 'submit' | 'approve' | 'cancel' | null>(null)
const cancellationReason = ref('')
const form = reactive<Record<string, string | number>>({})
const suppliers = ref<MasterRecord[]>([])
const materials = ref<MasterRecord[]>([])
const warehouses = ref<Array<{ id: number; code: string; name: string }>>([])
const option = (row: { id: number; code: string; name: string }) => ({ value: row.id, label: `${row.code} · ${row.name}` })
const fields = computed(() => [
  { key: 'code', label: '采购单号', required: true }, { key: 'name', label: '采购名称', required: true },
  { key: 'supplier_id', label: '供应商', type: 'select', required: true, options: suppliers.value.map(option) },
  { key: 'material_id', label: '物料', type: 'select', required: true, options: materials.value.map(option) },
  { key: 'warehouse_id', label: '收货仓', type: 'select', required: true, options: warehouses.value.map(option) },
  { key: 'quantity', label: '数量', type: 'number', required: true },
  { key: 'unit_price', label: '采购单价', type: 'number', required: true }, { key: 'expected_delivery_date', label: '预计到货日', type: 'date' },
  { key: 'due_date', label: '付款到期日', type: 'date', required: true }, { key: 'note', label: '备注', type: 'textarea' },
])
const labels: Record<string, string> = { draft: '草稿', submitted: '待审批', approved: '已审批', partially_received: '部分到货', fully_received: '全部到货', closed: '已关闭', cancelled: '已取消', disputed: '有争议' }
const tones = { 草稿: 'slate', 待审批: 'amber', 已审批: 'blue', 部分到货: 'blue', 全部到货: 'teal', 已关闭: 'teal', 已取消: 'slate', 有争议: 'rose' } as const
const displayRows = computed(() => rows.value.map((row) => ({ ...row, lifecycle_label: labels[row.status] ?? row.status, unpaid_amount: Number(row.total_amount) - Number(row.paid_amount || 0) })))
const kpis = computed(() => [
  { label: '采购单', value: rows.value.length, unit: '张', hint: '当前授权范围' },
  { label: '待审批', value: rows.value.filter((row) => row.status === 'submitted').length, unit: '张', tone: 'amber' as const, hint: '提交后仍可编辑' },
  { label: '在途采购', value: rows.value.filter((row) => ['approved', 'partially_received'].includes(row.status)).length, unit: '张', tone: 'blue' as const, hint: '审批不入库，到货核验后入账' },
])

async function load() {
  loading.value = true; pageError.value = ''
  try {
    const [orderPage, supplierPage, materialPage, warehousePage] = await Promise.all([
      listPurchaseOrders(), listAllMasterOptions('suppliers'), listAllMasterOptions('materials'), listWarehouseOptions(),
    ])
    rows.value = orderPage.items; Object.assign(pageMeta, orderPage)
    suppliers.value = supplierPage.filter((row) => !row.status || row.status === 'verified')
    materials.value = materialPage.filter((row) => !row.status || row.status === 'verified')
    warehouses.value = warehousePage.items
  }
  catch (error) { rows.value = []; pageError.value = message(error, '采购数据加载失败') }
  finally { loading.value = false }
}
async function queryOrders(query: Record<string, string | number>) {
  loading.value = true; pageError.value = ''
  try {
    const result = await listPurchaseOrders({ page: Number(query.page), page_size: Number(query.page_size), status: String(query.status ?? ''), search: String(query.name ?? '') })
    rows.value = result.items; Object.assign(pageMeta, result)
  } catch (error) { rows.value = []; pageError.value = message(error, '采购数据加载失败') }
  finally { loading.value = false }
}
function openForm(row?: PurchaseOrder) {
  editing.value = row ?? null; dialogError.value = ''
  for (const field of fields.value) form[field.key] = (row?.[field.key as keyof PurchaseOrder] as string | number) ?? ''
  formOpen.value = true
}
function body() {
  const payload: Record<string, unknown> = {}
  for (const field of fields.value) {
    const value = form[field.key]
    if (field.required && !String(value ?? '').trim()) throw new Error(`请填写${field.label}`)
    if (value !== '') payload[field.key] = ['number', 'select'].includes(field.type ?? '') ? Number(value) : String(value).trim()
  }
  return payload
}
function replace(row: PurchaseOrder) {
  const index = rows.value.findIndex((item) => item.id === row.id)
  if (index < 0) rows.value.unshift(row); else rows.value[index] = row
}
async function save() {
  if (submitting.value) return
  submitting.value = true
  dialogError.value = ''
  try {
    const payload = body()
    const result = editing.value
      ? await updatePurchaseOrder(editing.value.id, { ...payload, expected_version: editing.value.version })
      : await createPurchaseOrder(payload)
    replace(result.record); formOpen.value = false
  } catch (error) { dialogError.value = error instanceof Error ? submitErrorText(error, error.message) : '采购单保存失败' }
  finally { submitting.value = false }
}
function ask(action: 'delete' | 'submit' | 'approve' | 'cancel', row: PurchaseOrder) {
  target.value = row; confirmAction.value = action; cancellationReason.value = ''; dialogError.value = ''
}
async function confirm() {
  if (submitting.value) return
  submitting.value = true
  if (!target.value || !confirmAction.value) return
  dialogError.value = ''
  try {
    if (confirmAction.value === 'delete') { await deletePurchaseOrder(target.value.id); rows.value = rows.value.filter((row) => row.id !== target.value!.id) }
    else if (confirmAction.value === 'cancel') {
      if (!cancellationReason.value.trim()) throw new Error('取消采购单必须填写原因')
      replace((await cancelPurchaseOrder(target.value.id, target.value.version, cancellationReason.value.trim())).record)
    } else replace((confirmAction.value === 'submit'
      ? await submitPurchaseOrder(target.value.id, target.value.version)
      : await approvePurchaseOrder(target.value.id, target.value.version)).record)
    confirmAction.value = null; target.value = null
  } catch (error) { dialogError.value = error instanceof Error ? submitErrorText(error, error.message) : '采购操作失败' }
  finally { submitting.value = false }
}
function action(name: string, raw: Record<string, unknown>) {
  const row = rows.value.find((item) => item.id === Number(raw.id)); if (!row) return
  if (name === 'edit') openForm(row)
  else if (name === 'delete' || name === 'submit' || name === 'approve' || name === 'cancel') ask(name, row)
  else if (name === 'receive') {
    const query = new URLSearchParams({ purchase_order_id: String(row.id), warehouse_id: String(row.warehouse_id), material_id: String(row.material_id), unit_cost: String(row.unit_price) })
    window.history.pushState({}, '', `/warehouse/in?${query}`); window.dispatchEvent(new PopStateEvent('popstate'))
  }
}
onMounted(load)
</script>

<template>
  <div v-if="pageError" class="page-card table-empty" role="alert">{{ pageError }}<div style="margin-top:12px"><button class="ghost-action" type="button" @click="load">重新加载</button></div></div>
  <DataTablePage v-else export-resource="purchase-orders" title="采购明细" label="Purchase / Orders" description="采购审批不改变库存；到货核验后在同一事务生成库存事实与应付。" create-label="＋ 新建采购单" :kpis="kpis"
    :filters="[{ key: 'status', type: 'select', label: '全部业务状态', options: Object.entries(labels).map(([value, label]) => ({ value, label })) }, { key: 'name', type: 'search', placeholder: '搜索采购单 / 供应商 / 物料', wide: true }]"
    :columns="[{ key: 'code', label: '采购单号', type: 'title', sub: 'name' }, { key: 'supplier_name', label: '供应商' }, { key: 'material_name', label: '采购物料' }, { key: 'warehouse_name', label: '收货仓' }, { key: 'quantity', label: '数量', type: 'number' }, { key: 'received_quantity', label: '已到货', type: 'number' }, { key: 'total_amount', label: '金额', type: 'amount' }, { key: 'unpaid_amount', label: '待付', type: 'amount' }, { key: 'lifecycle_label', label: '状态', type: 'badge', tones }]"
    :rows="displayRows" action-test-id-prefix="purchase-action" server-side :total="pageMeta.total" :current-page="pageMeta.page" :page-size="pageMeta.page_size" :empty-text="loading ? '正在加载采购记录…' : '当前授权范围内暂无采购单'" @create="openForm()" @action="action" @query="queryOrders" />
  <Teleport to="body">
    <div v-if="formOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="采购单编辑"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">{{ editing ? 'Edit' : 'Create' }}</p><h2>{{ editing ? '编辑采购单' : '新增采购单' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="formOpen = false">×</button></div><p class="section-subtitle">提交后仍可编辑并递增版本；审批后业务字段只读。</p><div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))"><label v-for="field in fields" :key="field.key" class="modal-field" :for="`purchase-${field.key}`" :style="field.type === 'textarea' ? 'grid-column:1/-1' : ''"><span>{{ field.label }}{{ field.required ? ' *' : '' }}</span><textarea v-if="field.type === 'textarea'" :id="`purchase-${field.key}`" v-model="form[field.key]" rows="3" class="filter-input" style="width:100%;resize:vertical" /><select v-else-if="field.type === 'select'" :id="`purchase-${field.key}`" v-model="form[field.key]" class="filter-select" style="width:100%"><option value="" disabled>请选择{{ field.label }}</option><option v-for="item in field.options" :key="item.value" :value="item.value">{{ item.label }}</option></select><input v-else :id="`purchase-${field.key}`" v-model="form[field.key]" :type="field.type ?? 'text'" :min="field.type === 'number' ? 0 : undefined" class="filter-input" style="width:100%"></label></div><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="formOpen = false">取消</button><button class="primary-action" type="button" data-testid="purchase-save" :disabled="submitting" :aria-busy="submitting" @click="save">{{ submitting ? '保存中…' : '保存' }}</button></div></div></div>
    <div v-if="confirmAction && target" class="modal-overlay" role="dialog" aria-modal="true" aria-label="采购操作确认"><div class="modal-panel" style="width:min(500px,100%)"><div class="modal-panel__head"><div><p class="section-label">Confirm</p><h2>{{ confirmAction === 'approve' ? '审批采购单' : confirmAction === 'submit' ? '提交审批' : confirmAction === 'cancel' ? '取消采购单' : '删除草稿' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="confirmAction = null">×</button></div><p class="section-subtitle">{{ confirmAction === 'approve' ? '审批只确认采购，不会增加库存或生成应付。' : confirmAction === 'cancel' ? '取消将保留业务记录与原因；已有到货不能取消。' : confirmAction === 'submit' ? '提交后仍可编辑，审批待办跟随最新版本。' : '仅无引用的未提交草稿可以删除。' }}</p><label v-if="confirmAction === 'cancel'" class="modal-field" for="purchase-cancellation-reason"><span>取消原因 *</span><textarea id="purchase-cancellation-reason" v-model="cancellationReason" rows="3" class="filter-input" style="width:100%;resize:vertical" /></label><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="confirmAction = null">返回</button><button class="primary-action" type="button" data-testid="purchase-confirm" :disabled="submitting" :aria-busy="submitting" @click="confirm">{{ submitting ? '处理中…' : '确认' }}</button></div></div></div>
  </Teleport>
</template>
