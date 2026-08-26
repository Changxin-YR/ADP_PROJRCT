<script setup lang="ts">
import WarehouseRecordsPage from './WarehouseRecordsPage.vue'
</script>
<template>
  <WarehouseRecordsPage resource="transfers" title="仓间调拨" label="Warehouse / Transfers"
    description="调拨按申请、发出、在途、接收闭环办理；在途库存不计入任一仓库可用量。" create-label="新建调拨"
    :fields="[
      { key: 'code', label: '调拨单号', required: true }, { key: 'name', label: '调拨事项', required: true },
      { key: 'warehouse_id', label: '调出仓 ID', type: 'number', required: true }, { key: 'target_warehouse_id', label: '调入仓 ID', type: 'number', required: true },
      { key: 'material_id', label: '物料 ID', type: 'number', required: true }, { key: 'quantity', label: '调拨数量', type: 'number', required: true },
      { key: 'inventory_lot_id', label: '指定物料批次 ID', type: 'number' }, { key: 'override_reason', label: '非近效期批次覆盖原因', type: 'textarea' },
      { key: 'reason', label: '调拨原因', type: 'textarea', required: true },
    ]"
    :columns="[
      { key: 'code', label: '调拨单号', type: 'title', sub: 'happened_at' }, { key: 'name', label: '调拨事项' },
      { key: 'warehouse_name', label: '调出仓' }, { key: 'target_warehouse_name', label: '调入仓' },
      { key: 'material_name', label: '物料' }, { key: 'quantity', label: '数量', type: 'number' },
      { key: 'reason', label: '调拨原因' }, { key: 'row_version', label: '版本', type: 'number' },
    ]" />
</template>
