<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { ColumnItem } from '../../common/ui/DataTablePage.vue'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import { submitErrorText, messageWithContext as message } from '../../common/api/errors'
import type { MasterField, MasterRecord, MasterResource } from '../../common/api/master-data.models'

// 写操作防重复提交：busy + disabled + 防抖（BUG-M2-05/BUG-M4-09）
const submitting = ref(false)
import { archiveMasterRecord, createMasterRecord, deleteMasterDraft, listMasterRecords, submitMasterRecord, updateMasterRecord, verifyMasterRecord } from '../../features/master-data/master-data.service'

const props = defineProps<{
  resource: MasterResource
  title: string
  label: string
  description: string
  createLabel: string
  unit: string
  fields: MasterField[]
  columns: ColumnItem[]
}>()

const rows = ref<MasterRecord[]>([])
const loading = ref(true)
const pageError = ref('')
const dialogError = ref('')
const formOpen = ref(false)
const editing = ref<MasterRecord | null>(null)
const form = reactive<Record<string, string | number>>({})
const confirmAction = ref<'delete' | 'submit' | 'verify' | 'archive' | null>(null)
const actionTarget = ref<MasterRecord | null>(null)
const lifecycleNames: Record<string, string> = { draft: '草稿', submitted: '待核验', verified: '已核验', archived: '已归档' }
const lifecycleTones = { 草稿: 'slate', 待核验: 'amber', 已核验: 'teal', 已归档: 'slate' } as const
const displayRows = computed(() => rows.value.map((row) => ({ ...row, lifecycle_label: lifecycleNames[row.status] ?? row.status })))
const tableColumns = computed<ColumnItem[]>(() => [...props.columns, { key: 'lifecycle_label', label: '录入状态', type: 'badge', tones: lifecycleTones }])
const kpis = computed(() => [
  { label: `${props.title}总数`, value: rows.value.length, unit: props.unit, hint: '来自当前授权数据范围' },
  { label: '待核验', value: rows.value.filter((row) => row.status === 'submitted').length, unit: '条', tone: 'amber' as const, hint: '提交后仍可编辑，核验使用最新版本' },
  { label: '正式档案', value: rows.value.filter((row) => row.status === 'verified').length, unit: '条', tone: 'teal' as const, hint: '核验后永久只读' },
])


async function load() {
  loading.value = true
  pageError.value = ''
  try { rows.value = (await listMasterRecords(props.resource)).items }
  catch (error) { rows.value = []; pageError.value = message(error, '主数据加载失败') }
  finally { loading.value = false }
}

function openForm(row?: MasterRecord) {
  editing.value = row ?? null
  dialogError.value = ''
  for (const field of props.fields) form[field.key] = (row?.[field.key] as string | number) ?? ''
  formOpen.value = true
}

function payload() {
  const result: Record<string, unknown> = {}
  for (const field of props.fields) {
    const value = form[field.key]
    if (field.required && !String(value ?? '').trim()) throw new Error(`请填写${field.label}`)
    if (value !== '') result[field.key] = field.type === 'number' ? Number(value) : String(value).trim()
  }
  return result
}

function replace(record: MasterRecord) {
  const index = rows.value.findIndex((item) => item.id === record.id)
  if (index < 0) rows.value.unshift(record)
  else rows.value[index] = record
}

async function save() {
  if (submitting.value) return
  submitting.value = true
  dialogError.value = ''
  try {
    const body = payload()
    const result = editing.value
      ? await updateMasterRecord(props.resource, editing.value.id, { ...body, expected_version: editing.value.version })
      : await createMasterRecord(props.resource, body)
    replace(result.record)
    formOpen.value = false
  } catch (error) { dialogError.value = error instanceof Error ? submitErrorText(error, error.message) : '主数据保存失败' }
  finally { submitting.value = false }
}

function ask(action: 'delete' | 'submit' | 'verify' | 'archive', row: MasterRecord) {
  actionTarget.value = row
  confirmAction.value = action
  dialogError.value = ''
}

async function confirm() {
  const row = actionTarget.value
  const action = confirmAction.value
  if (submitting.value) return
  submitting.value = true
  if (!row || !action) return
  dialogError.value = ''
  try {
    if (action === 'delete') {
      await deleteMasterDraft(props.resource, row.id)
      rows.value = rows.value.filter((item) => item.id !== row.id)
    } else {
      const result = action === 'submit'
        ? await submitMasterRecord(props.resource, row.id, row.version)
        : action === 'verify'
          ? await verifyMasterRecord(props.resource, row.id, row.version)
          : await archiveMasterRecord(props.resource, row.id, row.version)
      replace(result.record)
    }
    confirmAction.value = null
    actionTarget.value = null
  } catch (error) { dialogError.value = submitErrorText(error, '操作失败') }
  finally { submitting.value = false }
}

function handleAction(action: string, raw: Record<string, unknown>) {
  const row = rows.value.find((item) => item.id === Number(raw.id))
  if (!row) return
  if (action === 'edit') openForm(row)
  else if (action === 'delete' || action === 'submit' || action === 'verify' || action === 'archive') ask(action, row)
}

onMounted(load)
</script>

<template>
  <div v-if="pageError" class="page-card table-empty" role="alert">{{ pageError }}<div style="margin-top:12px"><button class="ghost-action" type="button" @click="load">重新加载</button></div></div>
  <DataTablePage
    v-else
    :title="title"
    :label="label"
    :description="description"
    :create-label="createLabel"
    :kpis="kpis"
    :filters="[
      { key: 'status', type: 'select', label: '全部录入状态', options: Object.entries(lifecycleNames).map(([value, label]) => ({ value, label })) },
      { key: 'name', type: 'search', placeholder: `搜索${title}名称 / 编码`, wide: true },
    ]"
    :columns="tableColumns"
    :rows="displayRows"
    :empty-text="loading ? '正在加载主数据…' : '当前授权范围内暂无记录'"
    @create="openForm()"
    @action="handleAction"
  />

  <Teleport to="body">
    <div v-if="formOpen" class="modal-overlay" role="dialog" aria-modal="true" :aria-label="editing ? `编辑${title}` : `新增${title}`" @click.self="formOpen = false" @keydown.esc="formOpen = false">
      <div class="modal-panel">
        <div class="modal-panel__head"><div><p class="section-label">{{ editing ? 'Edit' : 'Create' }}</p><h2>{{ editing ? `编辑 · ${title}` : `新增 · ${title}` }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="formOpen = false">×</button></div>
        <p class="section-subtitle">草稿可修改；提交后仍可修改并保留版本；核验后永久只读。</p>
        <div class="modal-row" style="grid-template-columns:repeat(2,minmax(0,1fr))">
          <label v-for="field in fields" :key="field.key" class="modal-field" :style="field.type === 'textarea' ? 'grid-column:1/-1' : ''"><span>{{ field.label }}{{ field.required ? ' *' : '' }}</span><textarea v-if="field.type === 'textarea'" :id="`master-${field.key}`" v-model="form[field.key]" rows="3" class="filter-input" style="width:100%;resize:vertical" :placeholder="field.placeholder" /><input v-else :id="`master-${field.key}`" v-model="form[field.key]" :type="field.type === 'number' ? 'number' : 'text'" :min="field.type === 'number' ? 0 : undefined" class="filter-input" style="width:100%" :placeholder="field.placeholder"></label>
        </div>
        <p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p>
        <div class="modal-panel__foot"><button class="ghost-action" type="button" @click="formOpen = false">取消</button><button class="primary-action" type="button" data-testid="master-save" :disabled="submitting" :aria-busy="submitting" @click="save">{{ submitting ? '保存中…' : '保存' }}</button></div>
      </div>
    </div>

    <div v-if="confirmAction && actionTarget" class="modal-overlay" role="dialog" aria-modal="true" aria-label="主数据操作确认" @click.self="confirmAction = null" @keydown.esc="confirmAction = null">
      <div class="modal-panel" style="width:min(480px,100%)">
        <div class="modal-panel__head"><div><p class="section-label">Confirm</p><h2>{{ confirmAction === 'verify' ? '核验并锁定' : confirmAction === 'submit' ? '提交核验' : confirmAction === 'archive' ? '归档主数据' : '删除草稿' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="confirmAction = null">×</button></div>
        <p class="section-subtitle">{{ confirmAction === 'verify' ? `核验「${actionTarget.name}」后将永久只读，只能查看。` : confirmAction === 'submit' ? `提交「${actionTarget.name}」后仍可编辑，待办将跟随最新版本。` : confirmAction === 'archive' ? `归档「${actionTarget.name}」后将停止作为新业务的可选主数据，历史单据仍会保留。` : `仅在「${actionTarget.name}」未提交且无业务引用时允许删除。` }}</p>
        <p v-if="dialogError" class="modal-error" role="alert">{{ dialogError }}</p>
        <div class="modal-panel__foot"><button class="ghost-action" type="button" @click="confirmAction = null">取消</button><button class="primary-action" type="button" data-testid="master-confirm" :disabled="submitting" :aria-busy="submitting" @click="confirm">{{ submitting ? '处理中…' : '确认' }}</button></div>
      </div>
    </div>
  </Teleport>
</template>
