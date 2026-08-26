<script setup lang="ts">
import ProductionRecordsPage from '../production/ProductionRecordsPage.vue'
</script>

<template>
  <ProductionRecordsPage resource="losses" title="损耗记录" label="Ponds & batches / Losses"
    description="死亡、逃逸、疾病等批次存量减少事实；核验后通过追加式流水入账。"
    create-label="登记损耗" high-risk
    :fields="[
      { key: 'code', label: '损耗单号', required: true }, { key: 'name', label: '损耗类型', required: true },
      { key: 'batch_id', label: '批次 ID', type: 'number', required: true }, { key: 'pond_id', label: '塘口 ID', type: 'number', required: true },
      { key: 'quantity', label: '损耗数量', type: 'number' }, { key: 'weight_kg', label: '损耗重量（kg）', type: 'number' },
      { key: 'happened_at', label: '发生时间', type: 'datetime-local' }, { key: 'note', label: '原因与处理措施', type: 'textarea' },
    ]"
    :columns="[
      { key: 'code', label: '单号', type: 'title', sub: 'happened_at' }, { key: 'name', label: '损耗类型' },
      { key: 'batch_id', label: '批次 ID', type: 'number' }, { key: 'pond_id', label: '塘口 ID', type: 'number' },
      { key: 'quantity', label: '数量', type: 'number' }, { key: 'weight_kg', label: '重量（kg）', type: 'number' },
      { key: 'note', label: '原因与措施' }, { key: 'row_version', label: '版本', type: 'number' },
    ]" />
</template>
