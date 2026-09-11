import { computed, reactive, ref } from 'vue'
import { ApiError } from '../../common/api/errors'
import { createApiClient } from '../../common/api/client'
import type { WarehousePage } from '../../common/api/warehouse.models'
import { listPurchaseReturns, submitPurchaseReturn, verifyPurchaseReturn, cancelPurchaseReturn, deletePurchaseReturn } from '../../features/purchase/purchase.service'
import { listSalesReturns, submitSalesReturn, verifySalesReturn, cancelSalesReturn, deleteSalesReturn } from '../../features/sales/sales.service'
import { listWarehouseOptions } from '../../features/warehouse/warehouse.service'
import { RETURN_LABELS, RETURN_TONES, allowedActions, optionLabel, type ReturnMode, type ReturnRow, type SourceDoc } from './returnModel'

/** 已核验入库单：直接按后端支持的 status 过滤查询，避免改动共享的 warehouse.service（其它成员也在改） */
const listVerifiedReceipts = () => createApiClient().get<WarehousePage>('/api/v1/warehouse/receipts?page=1&page_size=100&status=verified')

/** 已核验交付单：后端 /sales/deliveries 支持 status 过滤，翻页拉全量供下拉选择 */
async function listVerifiedDeliveries(): Promise<SourceDoc[]> {
  const { listSalesDeliveries } = await import('../../features/sales/sales.service')
  const items: SourceDoc[] = []
  for (let page = 1; page <= 20; page += 1) {
    const result = await listSalesDeliveries({ page, page_size: 100, status: 'verified' })
    items.push(...(result.items as unknown as SourceDoc[]))
    if (!result.has_next || !result.items.length) break
  }
  return items
}

export function useReturns(mode: () => ReturnMode) {
  const rows = ref<ReturnRow[]>([])
  const pageMeta = reactive({ page: 1, page_size: 20, total: 0 })
  const loading = ref(true)
  const pageError = ref('')
  const receipts = ref<SourceDoc[]>([])
  const deliveries = ref<SourceDoc[]>([])
  const warehouses = ref<Array<{ id: number; code: string; name: string }>>([])
  const optionsFailed = ref(false)

  const codeOf = (list: SourceDoc[], id: unknown) => {
    const hit = list.find((item) => Number(item.id) === Number(id))
    return hit ? String(hit.code ?? hit.id) : (id ? `#${id}` : '—')
  }
  const warehouseName = (id: unknown) =>
    warehouses.value.find((item) => Number(item.id) === Number(id))?.name ?? (id ? `#${id}` : '—')

  /** 来源单据下拉：已核验入库单（采购退货）/ 已核验交付单（销售退货），禁止手填 ID */
  const sourceOptions = computed(() => mode() === 'purchase'
    ? receipts.value.map((row) => ({ value: Number(row.id), label: `${optionLabel({ id: row.id, code: row.code, name: row.name })} · ${row.material_name ?? ''} · ${row.inventory_lot_no ?? ''}`.trim() }))
    : deliveries.value.map((row) => ({ value: Number(row.id), label: `${optionLabel({ id: row.id, code: row.code, name: row.name })} · ${row.customer_name ?? ''}`.trim() })))

  const sourceOf = (form: Record<string, unknown>) => {
    const id = mode() === 'purchase' ? form.source_receipt_id : form.source_delivery_id
    const list = mode() === 'purchase' ? receipts.value : deliveries.value
    return list.find((row) => Number(row.id) === Number(id)) ?? null
  }

  const displayRows = computed(() => rows.value.map((row) => ({
    ...row,
    status_label: RETURN_LABELS[row.status] ?? row.status,
    source_code: mode() === 'purchase' ? codeOf(receipts.value, row.source_receipt_id) : codeOf(deliveries.value, row.source_delivery_id),
    warehouse_label: mode() === 'purchase' ? warehouseName(row.warehouse_id) : '—',
    allowed_actions: allowedActions(row),
  })))
  const columns = computed(() => mode() === 'purchase'
    ? [
        { key: 'code', label: '退货单号', type: 'title' as const, sub: 'name' },
        { key: 'source_code', label: '来源入库单' },
        { key: 'material_id', label: '物料' },
        { key: 'inventory_lot_id', label: '物料批次' },
        { key: 'warehouse_label', label: '所在仓库' },
        { key: 'quantity', label: '数量', type: 'number' as const },
        { key: 'amount', label: '冲减金额', type: 'amount' as const },
        { key: 'row_version', label: '版本', type: 'number' as const },
        { key: 'status_label', label: '状态', type: 'badge' as const, tones: RETURN_TONES },
      ]
    : [
        { key: 'code', label: '退货单号', type: 'title' as const, sub: 'name' },
        { key: 'source_code', label: '来源交付单' },
        { key: 'quantity', label: '数量', type: 'number' as const },
        { key: 'amount', label: '退货金额', type: 'amount' as const },
        { key: 'refund_amount', label: '退款金额', type: 'amount' as const },
        { key: 'row_version', label: '版本', type: 'number' as const },
        { key: 'status_label', label: '状态', type: 'badge' as const, tones: RETURN_TONES },
      ])
  const kpis = computed(() => [
    { label: mode() === 'purchase' ? '供应商退货' : '客户退货', value: pageMeta.total, unit: '张', hint: '当前授权范围' },
    { label: '待核验', value: rows.value.filter((row) => row.status === 'submitted').length, unit: '张', tone: 'amber' as const, hint: '核验后冲减应付/应收与库存' },
    { label: '已核验', value: rows.value.filter((row) => row.status === 'verified').length, unit: '张', tone: 'teal' as const, hint: '已核验记录只读' },
  ])

  function fail(error: unknown) {
    rows.value = []
    pageMeta.total = 0
    pageError.value = error instanceof ApiError ? `退货数据加载失败：${error.message}` : '退货数据加载失败'
  }

  async function load() {
    loading.value = true
    pageError.value = ''
    optionsFailed.value = false
    try {
      if (mode() === 'purchase') {
        const [returnPage, receiptPage, warehousePage] = await Promise.all([
          listPurchaseReturns({ page: pageMeta.page, page_size: pageMeta.page_size }),
          listVerifiedReceipts().catch(() => { optionsFailed.value = true; return { items: [] } as unknown as WarehousePage }),
          listWarehouseOptions().catch(() => { optionsFailed.value = true; return { items: [] as Array<{ id: number; code: string; name: string }> } }),
        ])
        rows.value = returnPage.items as unknown as ReturnRow[]
        Object.assign(pageMeta, returnPage)
        receipts.value = receiptPage.items
        warehouses.value = warehousePage.items
        deliveries.value = []
      } else {
        const [returnPage, deliveryItems] = await Promise.all([
          listSalesReturns({ page: pageMeta.page, page_size: pageMeta.page_size }),
          listVerifiedDeliveries().catch(() => { optionsFailed.value = true; return [] as SourceDoc[] }),
        ])
        rows.value = returnPage.items as unknown as ReturnRow[]
        Object.assign(pageMeta, returnPage)
        deliveries.value = deliveryItems
        receipts.value = []
      }
    } catch (error) {
      fail(error)
    } finally {
      loading.value = false
    }
  }

  async function queryReturns(query: Record<string, string | number>) {
    loading.value = true
    pageError.value = ''
    try {
      const common = { page: Number(query.page), page_size: Number(query.page_size), status: String(query.status ?? ''), search: String(query.code ?? '') }
      const result = mode() === 'purchase' ? await listPurchaseReturns(common) : await listSalesReturns(common)
      rows.value = result.items as unknown as ReturnRow[]
      Object.assign(pageMeta, result)
    } catch (error) {
      fail(error)
    } finally {
      loading.value = false
    }
  }

  function replace(row: ReturnRow) {
    const index = rows.value.findIndex((item) => item.id === row.id)
    if (index < 0) rows.value.unshift(row); else rows.value[index] = row
  }

  /** 提交 / 核验 / 取消：动作名与后端路由一一对应，不使用前端自造动作 */
  async function transition(action: 'submit' | 'verify' | 'cancel', row: ReturnRow, reason = ''): Promise<ReturnRow> {
    const purchase = mode() === 'purchase'
    const result = action === 'submit'
      ? (purchase ? await submitPurchaseReturn(row.id, row.version) : await submitSalesReturn(row.id, row.version))
      : action === 'verify'
        ? (purchase ? await verifyPurchaseReturn(row.id, row.version) : await verifySalesReturn(row.id, row.version))
        : (purchase ? await cancelPurchaseReturn(row.id, row.version, reason) : await cancelSalesReturn(row.id, row.version, reason))
    return result.record as unknown as ReturnRow
  }

  async function remove(row: ReturnRow) {
    if (mode() === 'purchase') await deletePurchaseReturn(row.id); else await deleteSalesReturn(row.id)
    rows.value = rows.value.filter((item) => item.id !== row.id)
    pageMeta.total = Math.max(0, pageMeta.total - 1)
  }

  function reset() {
    pageMeta.page = 1
    pageMeta.total = 0
  }

  return {
    rows, pageMeta, loading, pageError, receipts, deliveries, warehouses, optionsFailed,
    sourceOptions, sourceOf, displayRows, columns, kpis,
    load, queryReturns, replace, transition, remove, reset,
  }
}
