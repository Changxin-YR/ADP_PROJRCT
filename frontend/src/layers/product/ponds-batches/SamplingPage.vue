<script setup lang="ts">import ProductionRecordsPage from '../production/ProductionRecordsPage.vue'</script>
<template><ProductionRecordsPage resource="samplings" title="规格抽样" label="Ponds & batches / Sampling" description="登记实测规格与存塘估算，保留每次抽样来源和版本。" create-label="登记抽样" :fields="[
  { key: 'code', label: '抽样单号', required: true }, { key: 'name', label: '抽样名称', required: true }, { key: 'batch_id', label: '批次 ID', type: 'number', required: true },
  { key: 'pond_id', label: '塘口 ID', type: 'number', required: true }, { key: 'quantity', label: '样本数量', type: 'number' }, { key: 'weight_kg', label: '样本重量（kg）', type: 'number' },
  { key: 'happened_at', label: '抽样时间', type: 'datetime-local' }, { key: 'note', label: '测量方法与现场情况', type: 'textarea' },
]" :columns="[
  { key: 'code', label: '单号', type: 'title', sub: 'happened_at' }, { key: 'name', label: '抽样名称' }, { key: 'batch_id', label: '批次 ID', type: 'number' },
  { key: 'pond_id', label: '塘口 ID', type: 'number' }, { key: 'quantity', label: '样本数量', type: 'number' }, { key: 'weight_kg', label: '样本重量（kg）', type: 'number' }, { key: 'row_version', label: '版本', type: 'number' },
]" /></template>
