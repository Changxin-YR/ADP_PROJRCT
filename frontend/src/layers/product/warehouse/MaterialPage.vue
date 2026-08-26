<script setup lang="ts">
import MasterDataPage from '../master-data/MasterDataPage.vue'
</script>

<template>
  <MasterDataPage
    resource="materials" title="物料档案" label="Warehouse / Materials"
    description="鱼料、渔药、消毒用品、设备配件与养殖工具的统一受控档案。"
    create-label="新增物料" unit="种"
    :fields="[
      { key: 'code', label: '物料编号', required: true, placeholder: '例如：MAT-001' },
      { key: 'name', label: '物料名称', required: true },
      { key: 'category', label: '物料分类' }, { key: 'specification', label: '规格' },
      { key: 'unit', label: '计量单位' }, { key: 'safety_stock', label: '安全库存', type: 'number' },
      { key: 'shelf_life_days', label: '保质期（天）', type: 'number' },
    ]"
    :columns="[
      { key: 'code', label: '物料编号', type: 'title', sub: 'category' },
      { key: 'name', label: '物料名称' }, { key: 'specification', label: '规格' },
      { key: 'unit', label: '单位' }, { key: 'safety_stock', label: '安全库存', type: 'number' },
      { key: 'shelf_life_days', label: '保质期（天）', type: 'number' },
      { key: 'row_version', label: '版本', type: 'number' },
    ]"
  />
</template>
