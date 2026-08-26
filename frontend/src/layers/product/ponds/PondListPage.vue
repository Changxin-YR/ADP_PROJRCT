<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../../common/ui/AppShell.vue'
import RecordActions from '../../common/ui/RecordActions.vue'
import StatusBadge from '../../common/ui/StatusBadge.vue'
import { ApiError, submitErrorText } from '../../common/api/errors'
import { useSubmitGuard } from '../../common/ui/useSubmitGuard'
import type { MasterField, MasterRecord } from '../../common/api/master-data.models'
import type { RecordAction } from '../../common/api/lifecycle.models'
import { createMasterRecord, deleteMasterDraft, listMasterOptions, listMasterRecords, submitMasterRecord, updateMasterRecord, verifyMasterRecord } from '../../features/master-data/master-data.service'

type PondStatus = 'build' | 'stocked' | 'farming' | 'rest' | 'clean' | 'rebuild'
type PondRecord = MasterRecord & { pond_status?: PondStatus; area_id?: number; pond_group_id?: number; capacity_mu?: number; species?: string; location_text?: string }

const ponds = ref<PondRecord[]>([])
const search = ref('')
const pondStatus = ref<PondStatus | ''>('')
const areaId = ref('')
const loading = ref(true)
const pageError = ref('')
const dialogError = ref('')
const labels: Record<PondStatus, string> = { build: '筹建', stocked: '已放养', farming: '养殖中', rest: '轮休', clean: '清塘', rebuild: '改造' }
const tones: Record<PondStatus, 'teal' | 'blue' | 'amber' | 'slate'> = { build: 'slate', stocked: 'blue', farming: 'teal', rest: 'amber', clean: 'blue', rebuild: 'slate' }
const lifecycleNames: Record<string, string> = { draft: '草稿', submitted: '待核验', verified: '已核验', archived: '已归档' }
// 塘口扩展字段（BUG-007）：API 字段名与 backend-fixer 约定为 aerator_count/stocking_spec/current_spec/stock_quantity/stock_quantity_source
const STOCK_SOURCE_VALUES = ['system_estimated', 'manual_entry', 'field_measured', 'sampling', 'manual_correction']
const stockSourceOptions = [
  { value: 'system_estimated', label: '系统估算' },
  { value: 'manual_entry', label: '人工录入' },
  { value: 'field_measured', label: '现场实测' },
  { value: 'sampling', label: '抽样' },
  { value: 'manual_correction', label: '人工修正' },
]
const stockSourceLabels: Record<string, string> = Object.fromEntries(stockSourceOptions.map((item) => [item.value, item.label]))
const fields: MasterField[] = [
  { key: 'name', label: '塘口名称', required: true }, { key: 'code', label: '塘口编码', required: true },
  { key: 'area_id', label: '所属区域 ID', type: 'number', required: true }, { key: 'pond_group_id', label: '所属分组 ID', type: 'number' },
  { key: 'species', label: '养殖品种' }, { key: 'capacity_mu', label: '养殖面积（亩）', type: 'number' },
  { key: 'location_text', label: '位置说明' },
  { key: 'aerator_count', label: '增氧机数量（台）', type: 'number' },
  { key: 'stocking_spec', label: '投苗规格' }, { key: 'current_spec', label: '当前规格' },
  { key: 'stock_quantity', label: '当前存塘量（尾）', type: 'number' },
  { key: 'stock_quantity_source', label: '存塘量来源' },
]
const areaOptions = ref<MasterRecord[]>([])
const pondGroupOptions = ref<MasterRecord[]>([])
const filteredPonds = computed(() => ponds.value.filter((pond) =>
  (!pondStatus.value || pond.pond_status === pondStatus.value)
  && (!areaId.value || String(pond.area_id) === areaId.value)
  && (!search.value || `${pond.name}${pond.code}${pond.species ?? ''}${pond.location_text ?? ''}`.toLowerCase().includes(search.value.toLowerCase())),
))

const formOpen = ref(false)
const editing = ref<PondRecord | null>(null)
const form = reactive<Record<string, string | number>>({ pond_status: 'build' })
const availablePondGroups = computed(() => pondGroupOptions.value.filter((group) => Number(group.area_id) === Number(form.area_id)))
const confirmAction = ref<'delete' | 'submit' | 'verify' | null>(null)
const target = ref<PondRecord | null>(null)

function errorMessage(error: unknown, fallback: string) { return error instanceof ApiError ? `${fallback}：${error.message}` : fallback }
async function load() {
  loading.value = true; pageError.value = ''
  try {
    const [pondPage, areaPage, groupPage] = await Promise.all([listMasterRecords('ponds'), listMasterOptions('areas'), listMasterOptions('pond-groups')])
    ponds.value = pondPage.items as PondRecord[]; areaOptions.value = areaPage.items; pondGroupOptions.value = groupPage.items
  }
  catch (error) { ponds.value = []; pageError.value = errorMessage(error, '塘口数据加载失败') }
  finally { loading.value = false }
}
function replace(row: MasterRecord) {
  const index = ponds.value.findIndex((item) => item.id === row.id)
  if (index < 0) ponds.value.unshift(row as PondRecord); else ponds.value[index] = row as PondRecord
}
function openForm(row?: PondRecord) {
  editing.value = row ?? null; dialogError.value = ''
  for (const field of fields) form[field.key] = (row?.[field.key] as string | number) ?? ''
  form.pond_status = row?.pond_status ?? 'build'; formOpen.value = true
}
function changeArea() {
  if (!availablePondGroups.value.some((group) => group.id === Number(form.pond_group_id))) form.pond_group_id = ''
}
function formPayload() {
  const body: Record<string, unknown> = editing.value ? {} : { pond_status: form.pond_status }
  for (const field of fields) {
    const value = form[field.key]
    if (field.required && !String(value ?? '').trim()) throw new Error(`请填写${field.label}`)
    if (value === '') continue
    if (field.key === 'aerator_count') {
      const count = Number(value)
      if (!Number.isInteger(count) || count < 0) throw new Error('增氧机数量必须为不小于 0 的整数')
      body[field.key] = count
    } else if (field.key === 'stock_quantity') {
      const quantity = Number(value)
      if (!Number.isFinite(quantity) || quantity < 0) throw new Error('当前存塘量必须为不小于 0 的数字')
      body[field.key] = quantity
    } else if (field.key === 'stock_quantity_source') {
      if (!STOCK_SOURCE_VALUES.includes(String(value))) throw new Error('存塘量来源取值无效')
      body[field.key] = String(value)
    } else {
      body[field.key] = field.type === 'number' ? Number(value) : String(value).trim()
    }
  }
  return body
}
const { busy: saving, run: runSave } = useSubmitGuard()
async function save() {
  dialogError.value = ''
  await runSave(async () => {
    try {
      const body = formPayload()
      const result = editing.value
        ? await updateMasterRecord('ponds', editing.value.id, { ...body, expected_version: editing.value.version })
        : await createMasterRecord('ponds', body)
      replace(result.record); formOpen.value = false
    } catch (error) { dialogError.value = error instanceof Error ? submitErrorText(error, error.message) : '塘口保存失败' }
  })
}
function handleAction(action: RecordAction, row: PondRecord) {
  if (action === 'edit') openForm(row)
  else if (action === 'delete' || action === 'submit' || action === 'verify') { target.value = row; confirmAction.value = action }
}
const { busy: confirming, run: runConfirm } = useSubmitGuard()
async function confirm() {
  if (!target.value || !confirmAction.value) return
  dialogError.value = ''
  await runConfirm(async () => {
    try {
      if (confirmAction.value === 'delete') { await deleteMasterDraft('ponds', target.value!.id); ponds.value = ponds.value.filter((item) => item.id !== target.value!.id) }
      else {
        const result = confirmAction.value === 'submit'
          ? await submitMasterRecord('ponds', target.value!.id, target.value!.version)
          : await verifyMasterRecord('ponds', target.value!.id, target.value!.version)
        replace(result.record)
      }
      confirmAction.value = null; target.value = null
    } catch (error) { dialogError.value = errorMessage(error, '操作失败') }
  })
}
onMounted(load)
</script>

<template>
  <AppShell title="塘口档案">
    <div class="page-title"><div><p class="section-label">Ponds / Registry</p><h1>塘口档案</h1><p>一塘一档；养殖状态与录入核验状态分开管理，正式记录永久留痕。</p></div><button class="primary-action" type="button" @click="openForm()">新增塘口</button></div>
    <section class="kpi-grid"><article class="page-card kpi-card"><div class="kpi-card__top"><span>塘口总数</span></div><strong>{{ ponds.length }}<small> 口</small></strong><small>当前授权范围</small></article><article class="page-card kpi-card kpi--teal"><div class="kpi-card__top"><span>养殖中</span></div><strong>{{ ponds.filter((p) => p.pond_status === 'farming').length }}<small> 口</small></strong><small>运营状态</small></article><article class="page-card kpi-card kpi--amber"><div class="kpi-card__top"><span>待核验</span></div><strong>{{ ponds.filter((p) => p.status === 'submitted').length }}<small> 条</small></strong><small>提交后仍可编辑</small></article></section>
    <div class="filter-bar"><input v-model="search" data-testid="pond-search" class="filter-input" style="width:300px" placeholder="搜索塘口名称 / 编码 / 品种"><select v-model="pondStatus" class="filter-select"><option value="">全部养殖状态</option><option v-for="(label, key) in labels" :key="key" :value="key">{{ label }}</option></select><select v-model="areaId" class="filter-select"><option value="">全部区域</option><option v-for="area in areaOptions" :key="area.id" :value="String(area.id)">{{ area.name }}</option></select></div>
    <div v-if="pageError" class="page-card table-empty" role="alert">{{ pageError }}<div style="margin-top:12px"><button class="ghost-action" type="button" @click="load">重新加载</button></div></div>
    <section v-else class="page-card data-table-card"><table class="data-table"><thead><tr><th>塘口</th><th>区域</th><th>分组</th><th>养殖品种</th><th>面积</th><th>养殖状态</th><th>录入状态</th><th>操作</th></tr></thead><tbody><tr v-for="pond in filteredPonds" :key="pond.id"><td><RouterLink class="table-link" :to="`/ponds/${pond.id}`"><strong>{{ pond.name }}</strong></RouterLink><small>{{ pond.code }}</small></td><td>区域 {{ pond.area_id ?? '—' }}</td><td>{{ pond.pond_group_id ? `分组 ${pond.pond_group_id}` : '未分组' }}</td><td>{{ pond.species || '待定' }}</td><td><span class="table-number">{{ pond.capacity_mu ?? 0 }} 亩</span></td><td><StatusBadge :label="labels[pond.pond_status ?? 'build']" :tone="tones[pond.pond_status ?? 'build']" /></td><td>{{ lifecycleNames[pond.status] ?? pond.status }} · v{{ pond.version }}</td><td><div class="table-actions"><RouterLink :to="`/ponds/${pond.id}`">查看</RouterLink><RecordActions :actions="pond.allowed_actions.filter((action) => action !== 'view')" @action="handleAction($event, pond)" /></div></td></tr><tr v-if="!filteredPonds.length"><td colspan="8" class="table-empty">{{ loading ? '正在加载塘口档案…' : '没有符合条件的塘口' }}</td></tr></tbody></table></section>
    <div class="pagination-bar"><span>共 {{ filteredPonds.length }} 个塘口 · 当前页展示授权范围</span></div>

    <Teleport to="body">
      <div v-if="formOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="塘口资料编辑" @click.self="formOpen = false" @keydown.esc="formOpen = false"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">{{ editing ? 'Edit' : 'Create' }}</p><h2>{{ editing ? '编辑 · 塘口档案' : '新增 · 塘口档案' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="formOpen = false">×</button></div><p class="section-subtitle">提交后仍可修改并保留版本；核验后永久只读。扩展字段（增氧机/规格/存塘量）随档案一起保存。</p><div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))"><label v-for="field in fields" :key="field.key" class="modal-field"><span>{{ field.label }}{{ field.required ? ' *' : '' }}</span><select v-if="field.key === 'area_id'" v-model="form[field.key]" data-testid="pond-area" class="filter-select" style="width:100%" @change="changeArea"><option value="" disabled>请选择已核验区域</option><option v-for="area in areaOptions" :key="area.id" :value="area.id">{{ area.name }}（{{ area.code }}）</option></select><select v-else-if="field.key === 'pond_group_id'" v-model="form[field.key]" data-testid="pond-group" class="filter-select" style="width:100%"><option value="">不分组</option><option v-for="group in availablePondGroups" :key="group.id" :value="group.id">{{ group.name }}（{{ group.code }}）</option></select><select v-else-if="field.key === 'stock_quantity_source'" v-model="form[field.key]" data-testid="pond-stock_quantity_source" class="filter-select" style="width:100%"><option value="">未标注</option><option v-for="item in stockSourceOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select><input v-else v-model="form[field.key]" :data-testid="`pond-${field.key}`" :type="field.type === 'number' ? 'number' : 'text'" :min="field.key === 'aerator_count' || field.key === 'stock_quantity' ? 0 : undefined" :step="field.key === 'aerator_count' ? 1 : undefined" class="filter-input" style="width:100%"></label><label v-if="!editing" class="modal-field"><span>初始养殖状态</span><select v-model="form.pond_status" class="filter-select" style="width:100%"><option v-for="(label, key) in labels" :key="key" :value="key">{{ label }}</option></select></label></div><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="formOpen = false">取消</button><button class="primary-action" type="button" data-testid="pond-save" :disabled="saving" :aria-busy="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button></div></div></div>
      <div v-if="confirmAction && target" class="modal-overlay" role="dialog" aria-modal="true" aria-label="塘口操作确认"><div class="modal-panel" style="width:min(480px,100%)"><div class="modal-panel__head"><div><p class="section-label">Confirm</p><h2>{{ confirmAction === 'verify' ? '核验并锁定' : confirmAction === 'submit' ? '提交核验' : '删除草稿' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="confirmAction = null">×</button></div><p class="section-subtitle">{{ confirmAction === 'verify' ? '核验后永久只读，只能查看。' : confirmAction === 'submit' ? '提交后仍可修改，待办跟随最新版本。' : '只有未提交且无引用的草稿可以删除。' }}</p><p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="confirmAction = null">取消</button><button class="primary-action" type="button" :disabled="confirming" :aria-busy="confirming" @click="confirm">{{ confirming ? '处理中…' : '确认' }}</button></div></div></div>
    </Teleport>
  </AppShell>
</template>
