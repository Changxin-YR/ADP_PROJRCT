<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ApiError } from '../../common/api/errors'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import type { WarehouseLedgerRow } from '../../common/api/warehouse.models'
import { listWarehouseLedger } from '../../features/warehouse/warehouse.service'

const rows = ref<WarehouseLedgerRow[]>([])
const loading = ref(true)
const error = ref('')
const page = ref(1)
const total = ref(0)
const pageSize = 50
const labels: Record<string, string> = { receipt: '入库', issue: '出库', return: '退库', transfer_out: '调拨发出', transfer_in: '调拨接收', stocktake: '盘点差异', scrap: '报损报废', correction: '关联更正' }
const displayRows = computed(() => rows.value.map((row) => ({ ...row, source_label: labels[row.source_type] ?? row.source_type })))
async function loadLedger(targetPage = 1) {
  loading.value = true; error.value = ''
  try { const result = await listWarehouseLedger({ page: targetPage, page_size: pageSize }); rows.value = result.items; total.value = result.total; page.value = result.page }
  catch (reason) { error.value = reason instanceof ApiError ? `仓储台账加载失败：${reason.message}` : '仓储台账加载失败' }
  finally { loading.value = false }
}
onMounted(() => { void loadLedger() })
function queryLedger(query: Record<string, string | number>) { void loadLedger(Number(query.page ?? 1)) }
</script>

<template>
  <div v-if="error" class="page-card table-empty" role="alert">{{ error }}</div>
  <DataTablePage v-else export-resource="inventory-ledger" title="仓储台账" label="Warehouse / Ledger"
    description="不可修改的库存事实流水；每笔变化均可追溯到原仓储单据、物料批次和经办人。"
    :kpis="[
      { label: '流水笔数', value: rows.length, unit: '笔', hint: '当前授权范围' },
      { label: '可追溯率', value: rows.length ? '100%' : '—', tone: 'teal', hint: '单据 / 批次 / 时间齐备' },
      { label: '入库流水', value: rows.filter((row) => Number(row.quantity_delta) > 0).length, unit: '笔', hint: '正向变化' },
      { label: '出库流水', value: rows.filter((row) => Number(row.quantity_delta) < 0).length, unit: '笔', hint: '负向变化' },
    ]"
    :filters="[{ key: 'material_name', type: 'search', placeholder: '搜索物料 / 批次 / 仓库', wide: true }]"
    :columns="[
      { key: 'happened_at', label: '发生时间', type: 'strong' }, { key: 'material_name', label: '物料', type: 'title', sub: 'lot_no' },
      { key: 'warehouse_name', label: '仓库' }, { key: 'source_label', label: '业务类型', type: 'badge', tones: { '入库': 'teal', '退库': 'blue', '调拨接收': 'teal', '出库': 'amber', '调拨发出': 'slate', '报损报废': 'rose', '盘点差异': 'blue', '关联更正': 'blue' } },
      { key: 'quantity_delta', label: '数量变化', type: 'number' }, { key: 'source_id', label: '来源单据 ID', type: 'number' },
    ]"
    :rows="displayRows" server-side :total="total" :current-page="page" :page-size="pageSize" :empty-text="loading ? '正在加载仓储台账…' : '当前授权范围内暂无库存流水'" @query="queryLedger" />
</template>
