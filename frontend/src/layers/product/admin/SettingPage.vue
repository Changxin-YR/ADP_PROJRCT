<script setup lang="ts">
import MasterDataPage from '../master-data/MasterDataPage.vue'
</script>

<template>
  <MasterDataPage resource="settings" title="业务参数" label="System / Settings"
    description="品种、计量单位、预警阈值等全局参数的受控版本。" create-label="新增参数" unit="项"
    :fields="[
      { key: 'code', label: '参数编码', required: true }, { key: 'name', label: '参数名称', required: true },
      { key: 'group_code', label: '参数分组', required: true }, { key: 'value_text', label: '参数值', required: true },
      { key: 'note', label: '用途与影响', type: 'textarea' },
    ]"
    :columns="[
      { key: 'code', label: '参数编码', type: 'title', sub: 'group_code' }, { key: 'name', label: '参数名称' },
      { key: 'value_text', label: '参数值', type: 'strong' }, { key: 'note', label: '用途与影响' },
      { key: 'row_version', label: '版本', type: 'number' },
    ]" />
</template>
