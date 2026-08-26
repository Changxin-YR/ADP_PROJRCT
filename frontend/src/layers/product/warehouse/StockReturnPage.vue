<script setup lang="ts">
import WarehouseRecordsPage from './WarehouseRecordsPage.vue'
</script>
<template>
  <WarehouseRecordsPage resource="returns" title="退库管理" label="Warehouse / Returns"
    description="未使用物料按原出库单和原批次退回；累计退库不得超过原出库数量。" create-label="登记退库"
    :fields="[
      { key: 'code', label: '退库单号', required: true }, { key: 'name', label: '退库事项', required: true },
      { key: 'source_document_id', label: '原出库单 ID', type: 'number', required: true }, { key: 'warehouse_id', label: '退回仓库 ID', type: 'number', required: true },
      { key: 'material_id', label: '物料 ID', type: 'number', required: true }, { key: 'inventory_lot_id', label: '物料批次 ID', type: 'number', required: true },
      { key: 'quantity', label: '退库数量', type: 'number', required: true }, { key: 'reason', label: '退库原因', type: 'textarea', required: true },
    ]"
    :columns="[
      { key: 'code', label: '退库单号', type: 'title', sub: 'happened_at' }, { key: 'name', label: '退库事项' },
      { key: 'material_name', label: '物料' }, { key: 'inventory_lot_no', label: '批次' },
      { key: 'quantity', label: '数量', type: 'number' }, { key: 'source_document_id', label: '原出库单 ID', type: 'number' },
      { key: 'reason', label: '退库原因' }, { key: 'row_version', label: '版本', type: 'number' },
    ]" />
</template>
