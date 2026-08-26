<script setup lang="ts">
import MasterDataPage from '../master-data/MasterDataPage.vue'
</script>

<template>
  <MasterDataPage resource="suppliers" title="供应商档案" label="Purchase / Suppliers"
    description="供应商、账期和联系方式的统一受控档案。" create-label="新增供应商" unit="家"
    :fields="[
      { key: 'code', label: '供应商编号', required: true }, { key: 'name', label: '供应商名称', required: true },
      { key: 'contact_name', label: '联系人' }, { key: 'phone', label: '联系电话' },
      { key: 'settlement_days', label: '账期（天）', type: 'number' }, { key: 'address', label: '地址' },
      { key: 'note', label: '备注', type: 'textarea' },
    ]"
    :columns="[
      { key: 'code', label: '编号', type: 'title', sub: 'phone' }, { key: 'name', label: '供应商名称' },
      { key: 'contact_name', label: '联系人' }, { key: 'settlement_days', label: '账期（天）', type: 'number' },
      { key: 'address', label: '地址' }, { key: 'row_version', label: '版本', type: 'number' },
    ]" />
</template>
