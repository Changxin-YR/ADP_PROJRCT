<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '../../common/ui/AppShell.vue'
import { downloadTemplate, getExchangeTemplates, type ExchangeTemplate } from '../../features/data-exchange/data-exchange.service'

const templates = ref<ExchangeTemplate[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const group = ref('')
const notice = ref('')
const groups = computed(() => [...new Set(templates.value.map((item) => item.group))])
const rows = computed(() => templates.value.filter((item) => (!group.value || item.group === group.value) && (!search.value || `${item.name} ${item.code}`.toLowerCase().includes(search.value.toLowerCase()))))
const fieldCount = computed(() => templates.value.reduce((sum, item) => sum + item.fields.length, 0))

async function load() {
  loading.value = true; error.value = ''
  try { templates.value = (await getExchangeTemplates()).items }
  catch { error.value = '数据加载失败，请稍后重试' }
  finally { loading.value = false }
}
async function download(row: ExchangeTemplate) {
  try { await downloadTemplate(row.code); notice.value = `已生成 ${row.name} ${row.version} 模板` }
  catch { error.value = '模板下载失败，请稍后重试' }
}
onMounted(load)
</script>

<template>
  <AppShell title="导入模板">
    <div class="page-title"><div><p class="section-label">Data exchange / Templates</p><h1>导入模板</h1><p>标准模板按版本生成，列定义、格式、必填项与示例均由服务端统一维护。</p></div></div>
    <div v-if="error" class="form-alert form-alert--error" role="alert">{{ error }}</div>
    <div v-if="notice" class="form-alert form-alert--success" aria-live="polite">{{ notice }}</div>
    <section class="kpi-grid" style="grid-template-columns:repeat(3,minmax(0,1fr))" aria-label="模板指标">
      <article class="page-card kpi-card"><div class="kpi-card__top"><span>模板总数</span></div><strong>{{ templates.length }}<small> 个</small></strong><small>覆盖 {{ groups.length }} 个业务域</small></article>
      <article class="page-card kpi-card kpi--teal"><div class="kpi-card__top"><span>可直接导入</span></div><strong>{{ templates.filter((item) => item.importable).length }}<small> 个</small></strong><small>其余模板用于标准化采集</small></article>
      <article class="page-card kpi-card"><div class="kpi-card__top"><span>字段总数</span></div><strong>{{ fieldCount }}<small> 个</small></strong><small>含格式与示例说明</small></article>
    </section>
    <div class="filter-bar"><select v-model="group" class="filter-select" aria-label="全部业务域"><option value="">全部业务域</option><option v-for="item in groups" :key="item" :value="item">{{ item }}</option></select><input v-model="search" class="filter-input" placeholder="搜索模板名称 / 编码" aria-label="搜索模板名称 / 编码"></div>
    <section class="page-card data-table-card">
      <table class="data-table"><thead><tr><th>模板名称</th><th>版本</th><th>字段数</th><th>导入状态</th><th>最近更新</th><th style="width:1%">操作</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="row.code"><td><strong>{{ row.name }}</strong><small>{{ row.group }} · {{ row.code }}</small></td><td>{{ row.version }}</td><td style="text-align:right">{{ row.fields.length }}</td><td><span class="status-badge" :class="row.importable ? 'status-badge--teal' : 'status-badge--slate'"><i />{{ row.importable ? '可导入' : '仅下载' }}</span><small v-if="!row.importable">库存流水为系统只追加账本</small></td><td>{{ row.updated_at }}</td><td><button class="table-action-btn" type="button" :data-testid="`template-download-${row.code}`" @click="download(row)">下载</button></td></tr>
          <tr v-if="!loading && !rows.length"><td colspan="6" class="table-empty">没有符合条件的模板</td></tr><tr v-if="loading"><td colspan="6" class="table-empty">正在加载模板…</td></tr></tbody>
      </table>
    </section>
  </AppShell>
</template>
