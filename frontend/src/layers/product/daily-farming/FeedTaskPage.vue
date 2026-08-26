<script setup lang="ts">import ProductionRecordsPage from '../production/ProductionRecordsPage.vue'</script>
<template><ProductionRecordsPage resource="feed-tasks" title="投喂任务" label="Daily farming / Feed tasks" description="把投喂计划转为指定塘口、时间和作业人员的执行任务。" create-label="新建投喂任务" :fields="[
  { key: 'code', label: '任务单号', required: true }, { key: 'name', label: '任务名称', required: true }, { key: 'feed_plan_id', label: '投喂计划 ID', type: 'number' }, { key: 'batch_id', label: '批次 ID', type: 'number' },
  { key: 'pond_id', label: '塘口 ID', type: 'number', required: true }, { key: 'assigned_user_id', label: '作业员 ID', type: 'number' }, { key: 'quantity', label: '要求投喂量', type: 'number' },
  { key: 'planned_at', label: '要求时间', type: 'datetime-local' }, { key: 'note', label: '执行要求', type: 'textarea' },
]" :columns="[
  { key: 'code', label: '任务单号', type: 'title', sub: 'planned_at' }, { key: 'name', label: '任务名称' }, { key: 'feed_plan_id', label: '计划 ID', type: 'number' }, { key: 'pond_id', label: '塘口 ID', type: 'number' },
  { key: 'assigned_user_id', label: '作业员 ID', type: 'number' }, { key: 'quantity', label: '要求量', type: 'number' }, { key: 'row_version', label: '版本', type: 'number' },
]" /></template>
