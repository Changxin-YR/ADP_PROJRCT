<script setup lang="ts">
import MasterDataPage from '../master-data/MasterDataPage.vue'
</script>

<template>
  <MasterDataPage resource="pond-groups" title="塘口分组" label="Ponds / Groups"
    description="按区域和生产用途组织塘口，正式分组保留历史关联。" create-label="新增分组" unit="组"
    :fields="[
      { key: 'code', label: '分组编码', required: true }, { key: 'name', label: '分组名称', required: true },
      { key: 'description', label: '分组说明', type: 'textarea' },
    ]"
    :columns="[
      { key: 'code', label: '分组编码', type: 'title', sub: 'description' }, { key: 'name', label: '分组名称' },
      { key: 'area_id', label: '区域 ID', type: 'number' }, { key: 'row_version', label: '版本', type: 'number' },
    ]" />
</template>
