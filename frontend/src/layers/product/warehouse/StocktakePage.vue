<script setup lang="ts">
import WarehouseRecordsPage from './WarehouseRecordsPage.vue'
</script>
<template>
  <WarehouseRecordsPage resource="stocktakes" title="库存盘点" label="Warehouse / Stocktakes"
    description="核验时按账面余额与实盘数量的差额追加调整流水，不删除或覆盖原库存事实。" create-label="发起盘点" evidence-required
    :fields="[
      { key: 'code', label: '盘点单号', required: true }, { key: 'name', label: '盘点事项', required: true },
      { key: 'warehouse_id', label: '仓库 ID', type: 'number', required: true }, { key: 'material_id', label: '物料 ID', type: 'number', required: true },
      { key: 'inventory_lot_id', label: '物料批次 ID', type: 'number', required: true }, { key: 'quantity', label: '实盘数量', type: 'number', required: true },
      { key: 'reason', label: '差异原因', type: 'textarea', required: true },
    ]"
    :columns="[
      { key: 'code', label: '盘点单号', type: 'title', sub: 'happened_at' }, { key: 'name', label: '盘点事项' },
      { key: 'warehouse_name', label: '仓库' }, { key: 'material_name', label: '物料' },
      { key: 'inventory_lot_no', label: '批次' }, { key: 'quantity', label: '实盘数量', type: 'number' },
      { key: 'reason', label: '差异原因' }, { key: 'row_version', label: '版本', type: 'number' },
    ]" />
</template>
