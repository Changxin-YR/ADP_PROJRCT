<script setup lang="ts">import ProductionRecordsPage from '../production/ProductionRecordsPage.vue'</script>
<template><ProductionRecordsPage resource="transfers" title="转塘管理" label="Ponds & batches / Transfers" description="转塘核验后在同一事务内形成来源塘负流水和目标塘正流水。" create-label="新建转塘单" high-risk :fields="[
  { key: 'code', label: '转塘单号', required: true }, { key: 'name', label: '转塘事项', required: true }, { key: 'batch_id', label: '批次 ID', type: 'number', required: true },
  { key: 'pond_id', label: '来源塘口 ID', type: 'number', required: true }, { key: 'target_pond_id', label: '目标塘口 ID', type: 'number', required: true },
  { key: 'quantity', label: '转塘数量', type: 'number' }, { key: 'weight_kg', label: '转塘重量（kg）', type: 'number' },
  { key: 'happened_at', label: '转塘时间', type: 'datetime-local' }, { key: 'note', label: '原因与现场说明', type: 'textarea' },
]" :columns="[
  { key: 'code', label: '单号', type: 'title', sub: 'happened_at' }, { key: 'name', label: '事项' }, { key: 'batch_id', label: '批次 ID', type: 'number' },
  { key: 'pond_id', label: '来源塘', type: 'number' }, { key: 'target_pond_id', label: '目标塘', type: 'number' },
  { key: 'quantity', label: '数量', type: 'number' }, { key: 'weight_kg', label: '重量（kg）', type: 'number' }, { key: 'row_version', label: '版本', type: 'number' },
]" /></template>
