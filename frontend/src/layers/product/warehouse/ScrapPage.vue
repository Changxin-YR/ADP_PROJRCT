<script setup lang="ts">
import WarehouseRecordsPage from './WarehouseRecordsPage.vue'
</script>
<template>
  <WarehouseRecordsPage resource="scraps" title="报损报废" label="Warehouse / Scrap"
    description="提交后隔离指定批次可用量，授权核验后追加核减流水，并进入库存损耗分析。" create-label="登记报损" evidence-required
    :fields="[
      { key: 'code', label: '报损单号', required: true }, { key: 'name', label: '报损事项', required: true },
      { key: 'warehouse_id', label: '仓库 ID', type: 'number', required: true }, { key: 'material_id', label: '物料 ID', type: 'number', required: true },
      { key: 'inventory_lot_id', label: '物料批次 ID', type: 'number', required: true }, { key: 'quantity', label: '报损数量', type: 'number', required: true },
      { key: 'reason', label: '报损原因与处理方式', type: 'textarea', required: true },
    ]"
    :columns="[
      { key: 'code', label: '报损单号', type: 'title', sub: 'happened_at' }, { key: 'name', label: '报损事项' },
      { key: 'warehouse_name', label: '仓库' }, { key: 'material_name', label: '物料' },
      { key: 'inventory_lot_no', label: '批次' }, { key: 'quantity', label: '数量', type: 'number' },
      { key: 'reason', label: '原因与处理' }, { key: 'row_version', label: '版本', type: 'number' },
    ]" />
</template>
