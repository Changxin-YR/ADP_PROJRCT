<script setup lang="ts">import ProductionRecordsPage from '../production/ProductionRecordsPage.vue'</script>
<template><ProductionRecordsPage resource="feed-plans" title="投喂计划" label="Daily farming / Feed plans" description="按塘口和批次建立可核验、可追溯的投喂标准。" create-label="新建投喂计划" :fields="[
  { key: 'code', label: '计划单号', required: true }, { key: 'name', label: '计划名称', required: true }, { key: 'batch_id', label: '批次 ID', type: 'number' },
  { key: 'pond_id', label: '塘口 ID', type: 'number', required: true }, { key: 'material_id', label: '饲料物料 ID', type: 'number' }, { key: 'quantity', label: '计划投喂量', type: 'number' },
  { key: 'planned_at', label: '计划时间', type: 'datetime-local' }, { key: 'note', label: '投喂要求', type: 'textarea' },
]" :columns="[
  { key: 'code', label: '计划单号', type: 'title', sub: 'planned_at' }, { key: 'name', label: '计划名称' }, { key: 'pond_id', label: '塘口 ID', type: 'number' },
  { key: 'batch_id', label: '批次 ID', type: 'number' }, { key: 'material_id', label: '物料 ID', type: 'number' }, { key: 'quantity', label: '计划量', type: 'number' }, { key: 'row_version', label: '版本', type: 'number' },
]" /></template>
