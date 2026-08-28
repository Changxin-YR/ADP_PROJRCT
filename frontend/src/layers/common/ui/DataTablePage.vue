<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { RecordAction } from '../api/lifecycle.models'
import { ApiError } from '../api/errors'
import { exportData, resolveOrganizationId } from '../../features/data-exchange/data-exchange.service'
import AppShell from './AppShell.vue'
import RecordActions from './RecordActions.vue'
import StatusBadge from './StatusBadge.vue'

export interface KpiItem { label: string; value: string | number; unit?: string; hint?: string; tone?: 'teal' | 'blue' | 'amber' | 'rose' | 'slate' }
export interface FilterItem { key: string; type: 'search' | 'select'; placeholder?: string; label?: string; options?: { value: string; label: string }[]; wide?: boolean; testId?: string }
export interface ColumnItem { key: string; label: string; type?: 'text' | 'title' | 'badge' | 'number' | 'amount' | 'strong'; sub?: string; tones?: Record<string, 'teal' | 'blue' | 'amber' | 'rose' | 'slate'> }

const props = withDefaults(defineProps<{
  title: string
  label?: string
  description?: string
  createLabel?: string
  kpis?: KpiItem[]
  filters?: FilterItem[]
  columns: ColumnItem[]
  rows: object[]
  rowKey?: string
  actions?: string[]
  emptyText?: string
  exportable?: boolean
  exportResource?: string
  createMode?: 'form' | 'custom'
  persistLocal?: boolean
  readOnly?: boolean
  actionTestIdPrefix?: string
  serverSide?: boolean
  total?: number
  currentPage?: number
  pageSize?: number
}>(), {
  label: 'ADP / OPERATIONS', rowKey: 'id', emptyText: '当前筛选条件下没有结果',
  exportable: true, createMode: 'form', persistLocal: false, readOnly: false, actionTestIdPrefix: 'master-action',
  serverSide: false, total: 0, currentPage: 1, pageSize: 10,
})
const emit = defineEmits<{ create: []; action: [name: string, row: Record<string, unknown>]; query: [query: Record<string, string | number>] }>()
const records = computed(() => props.rows as Record<string, unknown>[])
const filterState = ref<Record<string, string>>({})
const sortKey = ref('')
const sortDir = ref<'asc' | 'desc'>('asc')
const page = ref(1)
const detailRow = ref<Record<string, unknown> | null>(null)
const hasFilter = computed(() => Object.values(filterState.value).some(Boolean))

const filteredRows = computed(() => props.serverSide ? records.value : records.value.filter((row) => (props.filters ?? []).every((filter) => {
  const value = filterState.value[filter.key] ?? ''
  if (!value) return true
  if (filter.type === 'search') return Object.values(row).join(' ').toLowerCase().includes(value.toLowerCase())
  return String(row[filter.key] ?? '') === value
})))
const sortedRows = computed(() => {
  if (!sortKey.value) return filteredRows.value
  const column = props.columns.find((item) => item.key === sortKey.value)
  const numeric = column?.type === 'number' || column?.type === 'amount'
  return [...filteredRows.value].sort((left, right) => {
    const a = left[sortKey.value]
    const b = right[sortKey.value]
    const result = numeric
      ? Number(String(a ?? '').replace(/[^\d.-]/g, '') || 0) - Number(String(b ?? '').replace(/[^\d.-]/g, '') || 0)
      : String(a ?? '').localeCompare(String(b ?? ''), 'zh-CN')
    return sortDir.value === 'asc' ? result : -result
  })
})
const activePage = computed(() => props.serverSide ? props.currentPage : page.value)
const resultTotal = computed(() => props.serverSide ? props.total : filteredRows.value.length)
const totalPages = computed(() => Math.max(1, Math.ceil(resultTotal.value / props.pageSize)))
const pagedRows = computed(() => props.serverSide ? sortedRows.value : sortedRows.value.slice((page.value - 1) * props.pageSize, page.value * props.pageSize))
const pageButtons = computed<(number | '…')[]>(() => {
  if (totalPages.value <= 5) return Array.from({ length: totalPages.value }, (_, index) => index + 1)
  if (activePage.value <= 3) return [1, 2, 3, 4, '…', totalPages.value]
  if (activePage.value >= totalPages.value - 2) return [1, '…', totalPages.value - 3, totalPages.value - 2, totalPages.value - 1, totalPages.value]
  return [1, '…', activePage.value - 1, activePage.value, activePage.value + 1, '…', totalPages.value]
})
watch([filteredRows, totalPages], () => { if (!props.serverSide && page.value > totalPages.value) page.value = totalPages.value })
function query(value: number) { emit('query', { ...filterState.value, page: value, page_size: props.pageSize }) }
watch(filterState, () => { if (props.serverSide) query(1); else page.value = 1 }, { deep: true })

const rowId = (row: Record<string, unknown>) => String(row[props.rowKey] ?? JSON.stringify(row))
const sortable = (column: ColumnItem) => column.type !== 'badge'
function toggleSort(column: ColumnItem) {
  if (!sortable(column)) return
  if (sortKey.value === column.key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else { sortKey.value = column.key; sortDir.value = 'asc' }
  if (props.serverSide) emit('query', { ...filterState.value, page: 1, page_size: props.pageSize, sort_by: sortKey.value, sort_dir: sortDir.value })
}
const toneOf = (column: ColumnItem, row: Record<string, unknown>) => column.tones?.[String(row[column.key])] ?? 'slate'
const allowedActions = (row: Record<string, unknown>) => Array.isArray(row.allowed_actions) ? row.allowed_actions as RecordAction[] : []
function runAction(name: string, row: Record<string, unknown>) {
  if (name === '详情' || name === 'view') detailRow.value = row
  else emit('action', name, row)
}
function goto(value: number) {
  const target = Math.min(totalPages.value, Math.max(1, value))
  if (props.serverSide) query(target); else page.value = target
}
const csvValue = (value: unknown) => {
  const raw = String(value ?? '')
  const text = /^[=+\-@]/.test(raw) ? `'${raw}` : raw
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}
function exportCsv() {
  const lines = [props.columns.map((item) => csvValue(item.label)).join(','), ...sortedRows.value.map((row) => props.columns.map((item) => csvValue(row[item.key])).join(','))]
  const url = URL.createObjectURL(new Blob([`\uFEFF${lines.join('\n')}`], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${props.title}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
const exporting = ref(false)
const exportNotice = ref('')
async function exportRange() {
  if (!props.exportResource || exporting.value) return
  exporting.value = true; exportNotice.value = ''
  try {
    const aliases: Record<string, string> = { name: 'search', code: 'search', supplier_name: 'search', material_name: 'search', period: 'search', batch_status: 'status' }
    const filters: Record<string, string> = {}
    for (const [key, value] of Object.entries(filterState.value)) if (value) filters[aliases[key] ?? key] = value
    await exportData({ organization_id: resolveOrganizationId(), resource: props.exportResource, format: 'xlsx', filters })
    exportNotice.value = '已导出当前范围（Excel，含生成时间/导出人/筛选条件元数据）'
  } catch (error) {
    exportNotice.value = error instanceof ApiError ? `导出失败：${error.message}` : '导出失败，请稍后重试'
  } finally { exporting.value = false }
}
const kpiToneClass = { teal: 'kpi--teal', blue: 'kpi--blue', amber: 'kpi--amber', rose: 'kpi--rose', slate: 'kpi--slate' }
// ===== 移动卡片模式（≤768px 用卡片列表替代表格，关键字段前置） =====
const titleColumn = computed(() => props.columns.find((column) => column.type === 'title') ?? props.columns[0])
const badgeColumns = computed(() => props.columns.filter((column) => column.type === 'badge'))
const cardFields = computed(() => props.columns.filter((column) => column !== titleColumn.value && column.type !== 'badge').slice(0, 4))
function cellText(row: Record<string, unknown>, column: ColumnItem): string {
  const value = row[column.key]
  if (column.type === 'amount') return `¥${Number(value ?? 0).toLocaleString()}`
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}
</script>

<template>
  <AppShell :title="title">
    <div class="page-title">
      <div><p class="section-label">{{ label }}</p><h1>{{ title }}</h1><p>{{ description }}</p></div>
      <div v-if="createLabel || exportable" class="page-title__actions"><button v-if="exportable && exportResource" class="ghost-action" type="button" data-testid="table-export-xlsx" :disabled="exporting" @click="exportRange">{{ exporting ? '导出中…' : '导出当前范围' }}</button><button v-else-if="exportable" class="ghost-action" type="button" data-testid="table-export-csv" @click="exportCsv">导出当前范围</button><button v-if="createLabel && !readOnly" class="primary-action" type="button" @click="emit('create')">{{ createLabel }}</button></div>
    </div>
    <slot name="tabs" />
    <section v-if="kpis?.length" class="kpi-grid" :class="kpis.length === 3 ? 'kpi-grid--3' : kpis.length === 2 ? 'kpi-grid--2' : ''" aria-label="模块指标">
      <article v-for="kpi in kpis" :key="kpi.label" class="page-card kpi-card" :class="kpi.tone ? kpiToneClass[kpi.tone] : ''"><div class="kpi-card__top"><span>{{ kpi.label }}</span></div><strong>{{ kpi.value }}<small v-if="kpi.unit"> {{ kpi.unit }}</small></strong><small>{{ kpi.hint }}</small></article>
    </section>
    <div v-if="filters?.length" class="filter-bar">
      <template v-for="filter in filters" :key="filter.key"><input v-if="filter.type === 'search'" v-model="filterState[filter.key]" class="filter-input" :style="filter.wide ? 'width:300px' : ''" :placeholder="filter.placeholder" :aria-label="filter.label ?? filter.placeholder" :data-testid="filter.testId"><select v-else v-model="filterState[filter.key]" class="filter-select" :aria-label="filter.label" :data-testid="filter.testId"><option value="">{{ filter.label ?? '全部' }}</option><option v-for="option in filter.options" :key="option.value" :value="option.value">{{ option.label }}</option></select></template>
      <span class="spacer" /><span v-if="exportNotice" class="form-error" role="status">{{ exportNotice }}</span><button v-if="hasFilter" class="ghost-action" type="button" @click="filterState = {}">清除筛选</button>
    </div>
    <section class="page-card data-table-card">
      <table class="data-table">
        <thead><tr><th v-for="column in columns" :key="column.key" :class="{ 'th-sortable': sortable(column) }" @click="toggleSort(column)">{{ column.label }}<span v-if="sortKey === column.key" class="sort-mark">{{ sortDir === 'asc' ? '▲' : '▼' }}</span></th><th v-if="actions?.length || pagedRows.some((row) => allowedActions(row).length)" style="width:1%">操作</th></tr></thead>
        <tbody>
          <tr v-for="row in pagedRows" :key="rowId(row)"><td v-for="column in columns" :key="column.key" :style="(column.type === 'amount' || column.type === 'number') ? 'text-align:right' : ''"><template v-if="column.type === 'title'"><strong>{{ row[column.key] }}</strong><small v-if="column.sub && row[column.sub]">{{ row[column.sub] }}</small></template><StatusBadge v-else-if="column.type === 'badge'" :label="String(row[column.key] ?? '—')" :tone="toneOf(column, row)" /><span v-else-if="column.type === 'amount'" class="table-number">¥{{ Number(row[column.key] ?? 0).toLocaleString() }}</span><strong v-else-if="column.type === 'strong'">{{ row[column.key] }}</strong><template v-else>{{ row[column.key] }}</template></td><td v-if="actions?.length || allowedActions(row).length"><RecordActions v-if="allowedActions(row).length" :actions="allowedActions(row)" :test-id-prefix="actionTestIdPrefix" @action="runAction($event, row)" /><div v-else class="table-actions"><button v-for="action in actions" :key="action" class="table-action-btn" type="button" @click="runAction(action, row)">{{ action }}</button></div></td></tr>
          <tr v-if="!filteredRows.length"><td :colspan="columns.length + (actions?.length ? 1 : 0)" class="table-empty">{{ emptyText }}</td></tr>
        </tbody>
      </table>
      <div class="data-table-cards" aria-label="记录卡片列表">
        <article v-for="row in pagedRows" :key="`card-${rowId(row)}`" class="table-card">
          <header class="table-card__head">
            <div class="table-card__title">
              <strong v-if="titleColumn">{{ cellText(row, titleColumn) }}</strong>
              <small v-if="titleColumn?.sub && row[titleColumn.sub]">{{ row[titleColumn.sub] }}</small>
            </div>
            <div v-if="badgeColumns.length" class="table-card__badges">
              <StatusBadge v-for="column in badgeColumns.slice(0, 2)" :key="column.key" :label="String(row[column.key] ?? '—')" :tone="toneOf(column, row)" />
            </div>
          </header>
          <dl v-if="cardFields.length" class="table-card__fields">
            <div v-for="column in cardFields" :key="column.key"><dt>{{ column.label }}</dt><dd>{{ cellText(row, column) }}</dd></div>
          </dl>
          <footer v-if="actions?.length || allowedActions(row).length" class="table-card__actions">
            <RecordActions v-if="allowedActions(row).length" :actions="allowedActions(row)" :test-id-prefix="actionTestIdPrefix" @action="runAction($event, row)" />
            <div v-else class="table-actions"><button v-for="action in actions" :key="action" class="table-action-btn" type="button" @click="runAction(action, row)">{{ action }}</button></div>
          </footer>
        </article>
        <p v-if="!filteredRows.length" class="table-empty">{{ emptyText }}</p>
      </div>
    </section>
    <div class="pagination-bar"><span>共 {{ resultTotal }} 条记录 · 每页 {{ pageSize }} 条</span><div class="pagination-actions"><button type="button" :disabled="activePage <= 1" data-testid="table-previous-page" @click="goto(activePage - 1)">‹</button><template v-for="(item, index) in pageButtons" :key="`${item}-${index}`"><button v-if="item === '…'" type="button" disabled>…</button><button v-else type="button" :class="{ 'is-active': item === activePage }" @click="goto(item)">{{ item }}</button></template><button type="button" :disabled="activePage >= totalPages" data-testid="table-next-page" @click="goto(activePage + 1)">›</button></div></div>
    <Teleport to="body"><div v-if="detailRow" class="modal-overlay" role="dialog" aria-modal="true" aria-label="记录详情" @click.self="detailRow = null" @keydown.esc="detailRow = null"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">Detail</p><h2>详情 · {{ title }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="detailRow = null">×</button></div><dl class="detail-pairs"><div v-for="column in columns" :key="column.key"><dt>{{ column.label }}</dt><dd>{{ detailRow[column.key] ?? '—' }}</dd></div></dl></div></div></Teleport>
  </AppShell>
</template>
