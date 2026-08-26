<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { ColumnItem } from '../../common/ui/DataTablePage.vue'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import { listMasterOptions } from '../../features/master-data/master-data.service'
import { createWarehouse, listWarehouseMasters, updateWarehouse, type WarehouseMaster } from '../../features/warehouse/warehouse.service'
import { messageWithContext as message } from '../../common/api/errors'
import { createSessionStore } from '../../common/session/session.store'
import { hasPermission } from '../../common/security/access-control'

const rows = ref<WarehouseMaster[]>([])
const farms = ref<Array<{ id: number; name: string }>>([])
const areas = ref<Array<{ id: number; name: string }>>([])
const open = ref(false)
const saving = ref(false)
const error = ref('')
const editing = ref<WarehouseMaster | null>(null)
const session = createSessionStore()
const canManage = computed(() => hasPermission(session.user.value, 'warehouse.manage'))
const form = reactive<Record<string, string>>({ code: '', name: '', farm_id: '', area_id: '', location: '', status: 'active' })
const columns: ColumnItem[] = [
  { key: 'code', label: '仓库编码', type: 'title', sub: 'name' },
  { key: 'farm_id', label: '基地', type: 'number' }, { key: 'area_id', label: '区域', type: 'number' },
  { key: 'location', label: '位置' }, { key: 'status', label: '状态', type: 'badge', tones: { active: 'teal', disabled: 'slate' } },
]
const displayRows = computed(() => rows.value.map((row) => ({ ...row, farm_id: farms.value.find((item) => item.id === row.farm_id)?.name ?? row.farm_id, area_id: areas.value.find((item) => item.id === row.area_id)?.name ?? row.area_id, allowed_actions: canManage.value ? ['edit'] : [] })))

async function load() {
  try {
    const [warehousePage, farmPage, areaPage] = await Promise.all([listWarehouseMasters(), listMasterOptions('farms'), listMasterOptions('areas')])
    rows.value = warehousePage.items
    farms.value = farmPage.items as Array<{ id: number; name: string }>
    areas.value = areaPage.items as Array<{ id: number; name: string }>
  } catch (cause) { error.value = message(cause, '仓库档案加载失败') }
}
function openForm(row?: WarehouseMaster) {
  editing.value = row ?? null
  Object.assign(form, { code: row?.code ?? '', name: row?.name ?? '', farm_id: row?.farm_id ? String(row.farm_id) : '', area_id: row?.area_id ? String(row.area_id) : '', location: row?.location ?? '', status: row?.status ?? 'active' })
  error.value = ''; open.value = true
}
async function save() {
  if (saving.value) return
  saving.value = true; error.value = ''
  try {
    const payload = { ...form, farm_id: Number(form.farm_id), ...(form.area_id ? { area_id: Number(form.area_id) } : { area_id: null }) }
    const result = editing.value ? await updateWarehouse(editing.value.id, payload) : await createWarehouse(payload)
    const index = rows.value.findIndex((row) => row.id === result.warehouse.id)
    if (index < 0) rows.value.unshift(result.warehouse)
    else rows.value[index] = result.warehouse
    open.value = false
  }
  catch (cause) { error.value = message(cause, '仓库档案保存失败') }
  finally { saving.value = false }
}
onMounted(load)
</script>

<template>
  <DataTablePage title="仓库档案" label="Warehouse / Master Data" description="维护采购、入库、领用与调拨使用的企业仓库。" :create-label="canManage ? '新增仓库' : undefined" :columns="columns" :rows="displayRows" :kpis="[{ label: '仓库总数', value: rows.length, unit: '个', hint: '当前企业仓库（含停用）' }]" action-test-id-prefix="warehouse-master-action" @create="openForm()" @action="(action, row) => action === 'edit' && openForm(rows.find((item) => item.id === Number(row.id)))" />
  <Teleport to="body"><div v-if="open" class="modal-overlay" role="dialog" aria-modal="true" :aria-label="editing ? '编辑仓库' : '新增仓库'" @click.self="open = false"><div class="modal-panel"><div class="modal-panel__head"><h2>{{ editing ? '编辑仓库' : '新增仓库' }}</h2><button class="modal-close" type="button" aria-label="关闭" @click="open = false">×</button></div><div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))"><label class="modal-field"><span>仓库编码 *</span><input v-model="form.code" class="filter-input" /></label><label class="modal-field"><span>仓库名称 *</span><input v-model="form.name" class="filter-input" /></label><label class="modal-field"><span>所属基地 *</span><select v-model="form.farm_id" class="filter-select"><option value="" disabled>请选择基地</option><option v-for="item in farms" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label class="modal-field"><span>所属区域</span><select v-model="form.area_id" class="filter-select"><option value="">不指定区域</option><option v-for="item in areas" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label class="modal-field"><span>仓库状态 *</span><select id="warehouse-status" v-model="form.status" class="filter-select"><option value="active">启用</option><option value="disabled">停用</option></select></label><label class="modal-field" style="grid-column:1/-1"><span>位置</span><input v-model="form.location" class="filter-input" /></label></div><p v-if="error" class="modal-error" role="alert">{{ error }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="open = false">取消</button><button class="primary-action" type="button" data-testid="warehouse-master-save" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button></div></div></div></Teleport>
</template>
