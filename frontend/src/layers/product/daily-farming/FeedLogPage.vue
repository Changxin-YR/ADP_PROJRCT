<script setup lang="ts">import ProductionRecordsPage from '../production/ProductionRecordsPage.vue'</script>
<template><ProductionRecordsPage resource="feed-logs" title="投喂记录" label="Daily farming / Feed logs" description="登记实际投喂事实，核验后关联物料领用和成本，原始记录不可覆盖。" create-label="录入投喂记录" :fields="[
  { key: 'code', label: '记录单号', required: true }, { key: 'name', label: '投喂事项', required: true }, { key: 'feed_task_id', label: '投喂任务 ID', type: 'number', required: true }, { key: 'material_issue_request_id', label: '领料申请 ID', type: 'number', required: true }, { key: 'batch_id', label: '批次 ID', type: 'number' },
  { key: 'pond_id', label: '塘口 ID', type: 'number', required: true }, { key: 'material_id', label: '物料 ID', type: 'number' }, { key: 'quantity', label: '实际投喂量', type: 'number' },
  { key: 'happened_at', label: '投喂时间', type: 'datetime-local' }, { key: 'note', label: '现场情况与偏差说明', type: 'textarea' },
]" :columns="[
  { key: 'code', label: '记录单号', type: 'title', sub: 'happened_at' }, { key: 'name', label: '投喂事项' }, { key: 'feed_task_id', label: '任务 ID', type: 'number' }, { key: 'material_issue_request_id', label: '领料申请 ID', type: 'number' }, { key: 'pond_id', label: '塘口 ID', type: 'number' },
  { key: 'batch_id', label: '批次 ID', type: 'number' }, { key: 'material_id', label: '物料 ID', type: 'number' }, { key: 'quantity', label: '实际量', type: 'number' }, { key: 'row_version', label: '版本', type: 'number' },
]" /></template>
