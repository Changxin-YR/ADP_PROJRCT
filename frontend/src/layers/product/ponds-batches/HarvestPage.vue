<script setup lang="ts">import ProductionRecordsPage from '../production/ProductionRecordsPage.vue'</script>
<template><ProductionRecordsPage resource="harvests" title="出塘记录" label="Ponds & batches / Harvests" description="记录实际起捕事实；核验后减少批次存量，并可由销售交付关联。" create-label="登记出塘" high-risk :fields="[
  { key: 'code', label: '出塘单号', required: true }, { key: 'name', label: '出塘事项', required: true }, { key: 'batch_id', label: '批次 ID', type: 'number', required: true },
  { key: 'pond_id', label: '塘口 ID', type: 'number', required: true }, { key: 'quantity', label: '出塘数量', type: 'number' }, { key: 'weight_kg', label: '出塘重量（kg）', type: 'number' },
  { key: 'happened_at', label: '起捕时间', type: 'datetime-local' }, { key: 'note', label: '去向、损耗与现场说明', type: 'textarea' },
]" :columns="[
  { key: 'code', label: '单号', type: 'title', sub: 'happened_at' }, { key: 'name', label: '事项' }, { key: 'batch_id', label: '批次 ID', type: 'number' },
  { key: 'pond_id', label: '塘口 ID', type: 'number' }, { key: 'quantity', label: '数量', type: 'number' }, { key: 'weight_kg', label: '重量（kg）', type: 'number' }, { key: 'row_version', label: '版本', type: 'number' },
]" /></template>
