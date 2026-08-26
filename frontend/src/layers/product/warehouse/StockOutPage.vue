<script setup lang="ts">
import { computed, ref } from 'vue'
import type { WarehouseField, WarehouseResource } from '../../common/api/warehouse.models'
import WarehouseRecordsPage from './WarehouseRecordsPage.vue'

const mode = ref<'request' | 'issue'>('issue')
const resource = computed<WarehouseResource>(() => mode.value === 'request' ? 'issue-requests' : 'issues')
const fields = computed<WarehouseField[]>(() => [
  { key: 'code', label: mode.value === 'request' ? '申请单号' : '出库单号', required: true },
  { key: 'name', label: '领用事项', required: true },
  { key: 'warehouse_id', label: '仓库 ID', type: 'number', required: true },
  { key: 'material_id', label: '物料 ID', type: 'number', required: true },
  { key: 'quantity', label: mode.value === 'request' ? '申请数量' : '实际出库数量', type: 'number', required: true },
  { key: 'scene', label: '场景（feed / medicine / maintenance）', required: true },
  { key: 'pond_id', label: '塘口 ID', type: 'number' },
  { key: 'batch_id', label: '养殖批次 ID', type: 'number' },
  { key: 'task_id', label: '作业任务 ID', type: 'number' },
  ...(mode.value === 'issue' ? [
    { key: 'source_document_id', label: '已核验领用申请 ID', type: 'number' as const, required: true },
    { key: 'inventory_lot_id', label: '指定物料批次 ID', type: 'number' as const },
    { key: 'override_reason', label: '非近效期批次覆盖原因', type: 'textarea' as const },
  ] : []),
  { key: 'note', label: '备注', type: 'textarea' },
])
</script>
<template>
  <div class="filter-bar" aria-label="出库业务模式">
    <button class="ghost-action" :class="{ 'is-active': mode === 'request' }" type="button" data-testid="warehouse-mode-request" @click="mode = 'request'">领用申请</button>
    <button class="ghost-action" :class="{ 'is-active': mode === 'issue' }" type="button" data-testid="warehouse-mode-issue" @click="mode = 'issue'">实际出库</button>
  </div>
  <WarehouseRecordsPage :key="resource" :resource="resource" :title="mode === 'request' ? '领用申请' : '实际出库'" label="Warehouse / Stock out"
    :description="mode === 'request' ? '作业员先按任务和塘口提交领用申请，仓储核验后才能办理实际出库。' : '实际出库必须关联已核验申请，按近效期优先分配且禁止负库存。'"
    :create-label="mode === 'request' ? '发起申请' : '办理出库'" :fields="fields"
    :columns="[
      { key: 'code', label: '出库单号', type: 'title', sub: 'happened_at' }, { key: 'name', label: '领用事项' },
      { key: 'material_name', label: '物料' }, { key: 'warehouse_name', label: '仓库' },
      { key: 'quantity', label: '数量', type: 'number' }, { key: 'scene', label: '场景' },
      { key: 'pond_id', label: '塘口 ID', type: 'number' }, { key: 'row_version', label: '版本', type: 'number' },
    ]" />
</template>
