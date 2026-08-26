<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '../../common/ui/AppShell.vue'
import { confirmImport, downloadImportErrors, getExchangeTemplates, getImportBatches, previewImport, revokeImport, type ExchangeTemplate, type ImportBatch } from '../../features/data-exchange/data-exchange.service'

const templates = ref<ExchangeTemplate[]>([])
const rows = ref<ImportBatch[]>([])
const page = ref(1)
const hasNext = ref(false)
const dialog = ref(false)
const organizationId = ref(1)
const templateCode = ref('materials')
const file = ref<File | null>(null)
const preview = ref<ImportBatch | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const importableTemplates = computed(() => templates.value.filter((item) => item.importable !== false))
const totalRows = computed(() => rows.value.reduce((sum, item) => sum + item.total_rows, 0))
const importedRows = computed(() => rows.value.reduce((sum, item) => sum + (item.imported_count ?? 0), 0))
const statusLabel: Record<string, string> = { invalid: '校验失败', ready: '待确认', imported: '导入成功', undone: '已撤销' }
const statusTone: Record<string, string> = { invalid: 'status-badge--rose', ready: 'status-badge--amber', imported: 'status-badge--teal', undone: 'status-badge--slate' }

async function load() {
  error.value = ''
  try {
    const [templateResult, importResult] = await Promise.all([getExchangeTemplates(), getImportBatches(page.value)])
    templates.value = templateResult.items; rows.value = importResult.items; hasNext.value = importResult.has_next
    if (!importableTemplates.value.some((item) => item.code === templateCode.value)) templateCode.value = importableTemplates.value[0]?.code ?? ''
  } catch { error.value = '数据加载失败，请稍后重试' }
}
function open() { dialog.value = true; preview.value = null; file.value = null; error.value = ''; notice.value = '' }
function choose(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] ?? null; preview.value = null }
async function validate() {
  if (!file.value || !templateCode.value) { error.value = '请选择可导入模板和 Excel 文件'; return }
  busy.value = true; error.value = ''
  try { preview.value = (await previewImport(organizationId.value, templateCode.value, file.value)).batch }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '文件校验失败' }
  finally { busy.value = false }
}
async function commit() {
  if (!preview.value || preview.value.status !== 'ready') return
  busy.value = true; error.value = ''
  try {
    preview.value = (await confirmImport(preview.value.id)).batch
    notice.value = `导入成功：${preview.value.imported_count ?? preview.value.total_rows} 行已写入草稿台账`
    await load()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '确认导入失败' }
  finally { busy.value = false }
}
async function errors(batch: ImportBatch) {
  try { await downloadImportErrors(batch.id) } catch { error.value = '错误明细下载失败' }
}
async function revoke(batch: ImportBatch) {
  if (!window.confirm(`确认撤销导入批次 #${batch.id}？该批次创建的草稿将全部删除，且不可恢复。`)) return
  busy.value = true; error.value = ''
  try {
    await revokeImport(batch.id)
    notice.value = `导入批次 #${batch.id} 已撤销，草稿数据已删除`
    await load()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '撤销失败' }
  finally { busy.value = false }
}
onMounted(load)
async function movePage(next: number) { if (next < 1 || (next > page.value && !hasNext.value)) return; page.value = next; await load() }
</script>

<template>
  <AppShell title="批量导入">
    <div class="page-title"><div><p class="section-label">Data exchange / Imports</p><h1>批量导入</h1><p>上传 Excel 后先逐行校验；任一行失败时整批不写入，确认后仅形成可继续核验的草稿记录。</p></div><div class="page-title__actions"><button class="primary-action" type="button" data-testid="import-open" @click="open">＋ 上传文件导入</button></div></div>
    <div v-if="error" class="form-alert form-alert--error" role="alert">{{ error }}</div>
    <div v-if="notice" class="form-alert form-alert--success" aria-live="polite">{{ notice }}</div>
    <section class="kpi-grid" style="grid-template-columns:repeat(3,minmax(0,1fr))" aria-label="导入指标">
      <article class="page-card kpi-card"><div class="kpi-card__top"><span>导入批次</span></div><strong>{{ rows.length }}<small> 个</small></strong><small>全部保留处理历史</small></article>
      <article class="page-card kpi-card kpi--teal"><div class="kpi-card__top"><span>已写入草稿</span></div><strong>{{ importedRows }}<small> 行</small></strong><small>核验前可继续编辑</small></article>
      <article class="page-card kpi-card"><div class="kpi-card__top"><span>已校验数据</span></div><strong>{{ totalRows }}<small> 行</small></strong><small>失败批次未写入</small></article>
    </section>
    <section class="page-card data-table-card"><table class="data-table"><thead><tr><th>批次 / 文件</th><th>模板</th><th>总行数</th><th>通过</th><th>错误</th><th>结果</th><th style="width:1%">操作</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="row.id"><td><strong>#{{ row.id }}</strong><small>{{ row.file_name }}</small></td><td>{{ row.template_name }} {{ row.template_version }}</td><td style="text-align:right">{{ row.total_rows }}</td><td style="text-align:right">{{ row.passed_rows }}</td><td style="text-align:right">{{ row.failed_rows }}</td><td><span class="status-badge" :class="statusTone[row.status]"><i />{{ statusLabel[row.status] }}</span></td><td><button v-if="row.failed_rows" class="table-action-btn" type="button" @click="errors(row)">错误明细</button><button v-if="row.status === 'imported'" class="table-action-btn" type="button" data-testid="import-revoke" :disabled="busy" @click="revoke(row)">撤销</button></td></tr><tr v-if="!rows.length"><td colspan="7" class="table-empty">暂无导入记录</td></tr></tbody>
        <tfoot><tr><td colspan="7"><div class="pagination"><button type="button" class="ghost-action" :disabled="page <= 1 || busy" @click="movePage(page - 1)">上一页</button><span>第 {{ page }} 页</span><button type="button" class="ghost-action" :disabled="!hasNext || busy" @click="movePage(page + 1)">下一页</button></div></td></tr></tfoot>
    </table></section>

    <Teleport to="body"><div v-if="dialog" class="modal-overlay" role="dialog" aria-modal="true" aria-label="批量导入向导" @keydown.esc="dialog = false"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">Import wizard</p><h2>批量导入</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="dialog = false">×</button></div>
      <label class="modal-field"><span>所属企业 ID *</span><input v-model.number="organizationId" class="filter-input" type="number" min="1"></label>
      <label class="modal-field"><span>数据模板 *</span><select v-model="templateCode" class="filter-select" style="width:100%"><option v-for="item in importableTemplates" :key="item.code" :value="item.code">{{ item.name }} {{ item.version }}</option></select></label>
      <label class="modal-field"><span>Excel 文件 *</span><input class="filter-input" type="file" accept=".xlsx" data-testid="import-file" @change="choose"></label>
      <div v-if="preview" class="page-card" style="padding:14px;margin-top:14px"><strong>校验结果：{{ preview.passed_rows ?? preview.imported_count ?? 0 }}/{{ preview.total_rows ?? preview.imported_count ?? 0 }} 行通过</strong><p v-for="item in preview.errors?.slice(0, 5) ?? []" :key="`${item.row}-${item.column}`" class="modal-error">第 {{ item.row }} 行 · {{ item.column }}：{{ item.message }}</p><table v-if="preview.preview_rows?.length" class="data-table" style="margin-top:10px"><tbody><tr v-for="(item, index) in preview.preview_rows?.slice(0, 3) ?? []" :key="index"><td v-for="(value, key) in item" :key="key"><small>{{ key }}</small>{{ value }}</td></tr></tbody></table></div>
      <div class="modal-panel__foot"><button class="ghost-action" type="button" @click="dialog = false">取消</button><button class="primary-action" type="button" data-testid="import-preview" :disabled="busy" @click="validate">{{ busy ? '校验中…' : '开始校验' }}</button><button v-if="preview?.status === 'ready'" class="primary-action" type="button" data-testid="import-confirm" :disabled="busy" @click="commit">确认整批导入</button></div>
    </div></div></Teleport>
  </AppShell>
</template>
