<script setup lang="ts">
import MasterDataPage from '../master-data/MasterDataPage.vue'
</script>

<template>
  <MasterDataPage resource="customers" title="客户档案" label="Sales / Customers"
    description="客户、账期与信用额度的统一受控档案。" create-label="新增客户" unit="家"
    :fields="[
      { key: 'code', label: '客户编号', required: true }, { key: 'name', label: '客户名称', required: true },
      { key: 'contact_name', label: '联系人' }, { key: 'phone', label: '联系电话' },
      { key: 'settlement_days', label: '账期（天）', type: 'number' }, { key: 'credit_limit', label: '信用额度', type: 'number' },
      { key: 'address', label: '地址' }, { key: 'note', label: '备注', type: 'textarea' },
    ]"
    :columns="[
      { key: 'code', label: '编号', type: 'title', sub: 'phone' }, { key: 'name', label: '客户名称' },
      { key: 'contact_name', label: '联系人' }, { key: 'settlement_days', label: '账期（天）', type: 'number' },
      { key: 'credit_limit', label: '信用额度', type: 'amount' }, { key: 'row_version', label: '版本', type: 'number' },
    ]" />
</template>
