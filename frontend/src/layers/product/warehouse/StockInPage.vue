<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { PurchaseOrder } from '../../common/api/purchase.models'
import { listAllMasterOptions } from '../../features/master-data/master-data.service'
import { listPurchaseOrders } from '../../features/purchase/purchase.service'
import { listWarehouseOptions } from '../../features/warehouse/warehouse.service'
import WarehouseRecordsPage from './WarehouseRecordsPage.vue'

const materials = ref<Array<{ id: number; code: string; name: string }>>([])
const warehouses = ref<Array<{ id: number; code: string; name: string }>>([])
const orders = ref<PurchaseOrder[]>([])
const optionError = ref('')
const query = new URLSearchParams(window.location.search)
const initialValues = {
  purchase_order_id: query.get('purchase_order_id') ?? '', warehouse_id: query.get('warehouse_id') ?? '',
  material_id: query.get('material_id') ?? '', unit_cost: query.get('unit_cost') ?? '',
}
const option = (row: { id: number; code: string; name: string }) => ({ value: row.id, label: `${row.code} · ${row.name}` })
const fields = computed(() => [
  { key: 'code', label: '入库单号', required: true }, { key: 'name', label: '入库事项', required: true },
  { key: 'warehouse_id', label: '仓库', type: 'select' as const, required: true, options: warehouses.value.map(option) },
  { key: 'material_id', label: '物料', type: 'select' as const, required: true, options: materials.value.map(option) },
  { key: 'quantity', label: '入库数量', type: 'number' as const, required: true }, { key: 'unit_cost', label: '单位成本', type: 'number' as const },
  { key: 'lot_no', label: '物料批次', required: true }, { key: 'production_date', label: '生产日期', type: 'date' as const },
  { key: 'expiry_date', label: '到期日期', type: 'date' as const }, { key: 'location', label: '存放位置' },
  { key: 'purchase_order_id', label: '来源采购单', type: 'select' as const, options: orders.value.map(option) },
  { key: 'note', label: '备注', type: 'textarea' as const },
])
onMounted(async () => {
  try {
    const [materialPage, warehousePage, approved, partial] = await Promise.all([
      listAllMasterOptions('materials'), listWarehouseOptions(), listPurchaseOrders({ page_size: 100, status: 'approved' }), listPurchaseOrders({ page_size: 100, status: 'partially_received' }),
    ])
    materials.value = materialPage; warehouses.value = warehousePage.items
    orders.value = [...new Map([...approved.items, ...partial.items].map((row) => [row.id, row])).values()]
  } catch { optionError.value = '仓储数据加载失败：入库关联选项加载失败，请重新进入页面' }
})
</script>
<template>
  <div v-if="optionError" class="page-card table-empty" role="alert">{{ optionError }}</div>
  <WarehouseRecordsPage v-else resource="receipts" title="入库管理" label="Warehouse / Stock in"
    description="采购到货与其他入库的受控单据；核验后创建物料批次并追加正式库存流水。" create-label="登记入库" evidence-required
    :fields="fields" :initial-values="initialValues"
    :columns="[
      { key: 'code', label: '入库单号', type: 'title', sub: 'happened_at' }, { key: 'name', label: '入库事项' },
      { key: 'material_name', label: '物料' }, { key: 'warehouse_name', label: '仓库' },
      { key: 'quantity', label: '数量', type: 'number' }, { key: 'lot_no', label: '批次', type: 'title', sub: 'expiry_date' },
      { key: 'location', label: '存放位置' }, { key: 'row_version', label: '版本', type: 'number' },
    ]" />
</template>
