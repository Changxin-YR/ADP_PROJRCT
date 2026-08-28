<script setup lang="ts">import ProductionRecordsPage from '../production/ProductionRecordsPage.vue'</script>
<template><ProductionRecordsPage resource="daily-operations" title="日常作业" label="Daily farming / Operations" description="统一记录巡塘、水质、消毒、换水、维修和异常处理事实。" create-label="登记日常作业" :fields="[
  { key: 'code', label: '作业单号', required: true }, { key: 'name', label: '作业名称', required: true }, { key: 'operation_type', label: '作业类型', type: 'select', required: true, options: [
    { value: 'patrol', label: '巡塘' }, { value: 'water_change', label: '换水' }, { value: 'medicine', label: '用药' }, { value: 'aeration', label: '增氧' }, { value: 'water_quality', label: '水质检测' }, { value: 'equipment_maintenance', label: '设备维护' }, { value: 'other', label: '其他' },
  ] }, { key: 'batch_id', label: '批次 ID', type: 'number' },
  { key: 'pond_id', label: '塘口 ID', type: 'number', required: true }, { key: 'material_id', label: '关联物料 ID', type: 'number' },
  { key: 'happened_at', label: '作业时间', type: 'datetime-local' }, { key: 'payload', label: '结构化参数 JSON', type: 'json', required: true }, { key: 'note', label: '结果与异常说明', type: 'textarea' },
]" :columns="[
  { key: 'code', label: '作业单号', type: 'title', sub: 'happened_at' }, { key: 'name', label: '作业类型' }, { key: 'pond_id', label: '塘口 ID', type: 'number' },
  { key: 'batch_id', label: '批次 ID', type: 'number' }, { key: 'material_id', label: '物料 ID', type: 'number' }, { key: 'note', label: '结果与异常' }, { key: 'row_version', label: '版本', type: 'number' },
]" /></template>
