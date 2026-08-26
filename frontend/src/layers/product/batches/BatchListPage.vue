<script setup lang="ts">
import ProductionRecordsPage from '../production/ProductionRecordsPage.vue'

const batchStatusTones = { 已放养: 'blue', 养殖中: 'teal', 待结算: 'amber', 已关闭: 'slate' } as const
</script>

<template>
  <ProductionRecordsPage resource="batches" title="养殖批次" label="Ponds & batches / Batches"
    description="批次存量由投苗、转塘、损耗和出塘的不可变流水汇总，页面不能直接覆盖。"
    create-label="新建投苗批次"
    :extra-filters="[{ key: 'batch_status', type: 'select', label: '全部批次状态', testId: 'batch-status', options: [{ value: 'stocked', label: '已放养' }, { value: 'farming', label: '养殖中' }, { value: 'pending_settlement', label: '待结算' }, { value: 'closed', label: '已关闭' }] }]"
    :fields="[
      { key: 'code', label: '批次编号', required: true }, { key: 'name', label: '批次名称', required: true },
      { key: 'pond_id', label: '初始塘口 ID', type: 'number', required: true }, { key: 'species', label: '养殖品种', required: true },
      { key: 'initial_quantity', label: '初始数量', type: 'number' }, { key: 'initial_weight_kg', label: '初始重量（kg）', type: 'number' },
      { key: 'stocked_at', label: '投苗时间', type: 'datetime-local' }, { key: 'expected_harvest_date', label: '预计出塘日期' },
      { key: 'batch_status', label: '批次状态', required: true }, { key: 'note', label: '批次说明', type: 'textarea' },
    ]"
    :columns="[
      { key: 'code', label: '批次', type: 'title', sub: 'name' }, { key: 'species', label: '品种' },
      { key: 'pond_id', label: '初始塘口 ID', type: 'number' }, { key: 'batch_status_label', label: '批次状态', type: 'badge', tones: batchStatusTones },
      { key: 'current_quantity', label: '当前存量', type: 'number' }, { key: 'current_weight_kg', label: '当前重量（kg）', type: 'number' },
      { key: 'initial_quantity', label: '初始数量', type: 'number' }, { key: 'row_version', label: '版本', type: 'number' },
    ]" />
</template>
