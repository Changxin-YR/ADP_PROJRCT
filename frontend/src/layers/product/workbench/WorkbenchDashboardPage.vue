<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '../../common/ui/AppShell.vue'
import StatusBadge from '../../common/ui/StatusBadge.vue'
import { getWorkbenchSummary, getWorkItems } from '../../features/workbench/workbench.service'
import type { WorkbenchSummary } from '../../common/api/workbench.models'
import { ApiError } from '../../common/api/errors'

const summary = ref<WorkbenchSummary>()
const loading = ref(true)
const error = ref('')
const overdueCount = ref<number | null>(null)
const statusColors: Record<string, string> = { farming: '#6ba593', stocked: '#a3c9b7', build: '#8dbbb0', rest: '#c4b89a', clean: '#9ab4c2', rebuild: '#b0a498' }
const statusTones: Record<string, 'teal' | 'blue' | 'amber' | 'slate' | 'rose'> = { farming: 'teal', stocked: 'blue', build: 'slate', rest: 'amber', clean: 'blue', rebuild: 'slate' }
const productionAvailable = computed(() => summary.value?.availability?.production !== false)
const totalPonds = computed(() => productionAvailable.value ? summary.value?.pond_status.reduce((total, item) => total + item.count, 0) ?? summary.value?.kpis.ponds ?? 0 : null)
const metric = (value: number | null) => value === null ? '--' : value.toLocaleString()
// 待办超时提示：以工作项接口真实统计（消息口径见 section 标注），不再硬编码"其中 1 项"
const overdueHint = computed(() => {
  if (overdueCount.value === null) return '待办时限以列表为准'
  if (overdueCount.value > 0) return `其中 ${overdueCount.value} 项已超过处理时限`
  return '暂无超过处理时限的待办'
})

onMounted(async () => {
  try { summary.value = await getWorkbenchSummary() }
  catch (reason) { error.value = reason instanceof ApiError ? reason.message : '工作台服务暂时不可用，请稍后重试' }
  try {
    const page = await getWorkItems(false)
    overdueCount.value = page.items.filter((item) => (item as { overdue?: boolean }).overdue).length
  } catch { overdueCount.value = null }
  finally { loading.value = false }
})
</script>

<template>
  <AppShell title="工作台">
    <div class="page-title"><div><p class="section-label">Operations overview</p><h1>今日工作台</h1><p>欢迎回来，先从今天最重要的养殖动作开始。</p></div><span class="page-title__date">{{ summary?.date_label ?? '正在同步工作区…' }}</span></div>
    <div v-if="loading" class="page-card table-empty" role="status">正在加载工作台数据…</div>
    <div v-else-if="error" class="page-card table-empty" role="alert">{{ error }}</div>
    <template v-else-if="summary">
      <section class="kpi-grid" aria-label="工作台指标">
        <article class="page-card kpi-card" data-testid="kpi-ponds"><div class="kpi-card__top"><span>塘口总数</span><b class="kpi-card__icon">▦</b></div><strong>{{ metric(summary.kpis.ponds) }}</strong><small>{{ productionAvailable ? '已纳入当前数据范围' : '无养殖数据权限' }}</small></article>
        <article class="page-card kpi-card"><div class="kpi-card__top"><span>养殖中批次</span><b class="kpi-card__icon">◌</b></div><strong>{{ metric(summary.kpis.active_batches) }}</strong><small>{{ productionAvailable ? '需要持续关注的生产批次' : '无养殖数据权限' }}</small></article>
        <article class="page-card kpi-card"><div class="kpi-card__top"><span>当前存量</span><b class="kpi-card__icon">⌁</b></div><strong>{{ metric(summary.kpis.current_stock) }}</strong><small>{{ productionAvailable ? '单位：尾 · 以流水汇总为准' : '无养殖数据权限' }}</small></article>
        <article class="page-card kpi-card"><div class="kpi-card__top"><span>我的待办</span><b class="kpi-card__icon">✓</b></div><strong>{{ summary.kpis.todo_open }}</strong><small>{{ overdueHint }}</small></article>
        <article v-if="summary.operating_metrics" class="page-card kpi-card"><div class="kpi-card__top"><span>今日作业</span><b class="kpi-card__icon">◷</b></div><strong>{{ metric(summary.operating_metrics.feed_today) }}</strong><small>已核验投喂与日常作业</small></article>
        <article v-if="summary.operating_metrics" class="page-card kpi-card"><div class="kpi-card__top"><span>待付金额</span><b class="kpi-card__icon">￥</b></div><strong>{{ metric(summary.operating_metrics.payable_open) }}</strong><small>采购应付未结余额</small></article>
        <article v-if="summary.operating_metrics" class="page-card kpi-card"><div class="kpi-card__top"><span>待收金额</span><b class="kpi-card__icon">￥</b></div><strong>{{ metric(summary.operating_metrics.receivable_open) }}</strong><small>销售应收未结余额</small></article>
        <article v-if="summary.operating_metrics" class="page-card kpi-card"><div class="kpi-card__top"><span>本期成本</span><b class="kpi-card__icon">∑</b></div><strong>{{ metric(summary.operating_metrics.confirmed_cost) }}</strong><small>本月已确认成本</small></article>
      </section>
      <div class="dashboard-grid">
        <section v-if="productionAvailable" class="page-card dashboard-card"><div class="section-head"><div><p class="section-label">Pond status</p><h2 class="section-title">塘口状态分布</h2><p class="section-subtitle">当前状态与生命周期状态分开管理</p></div><RouterLink class="ghost-action" to="/ponds">查看全部塘口</RouterLink></div><div class="status-distribution"><div class="donut"><div class="donut__label"><strong>{{ totalPonds }}</strong><span>个塘口</span></div></div><div class="status-legend"><div v-for="item in summary.pond_status" :key="item.status" class="legend-item"><i :style="{ background: statusColors[item.status] }" /><span>{{ item.label }}</span><strong>{{ item.count }}</strong></div></div></div></section>
        <section v-else class="page-card dashboard-card table-empty">当前账号无养殖数据权限</section>
        <section class="page-card dashboard-card"><div class="section-head"><div><p class="section-label">Action queue</p><h2 class="section-title">我的待办</h2><p class="section-subtitle">优先处理带有红色标记的事项</p></div><RouterLink class="ghost-action" to="/todos">全部待办</RouterLink></div><div class="todo-list"><div v-for="todo in summary.todos" :key="todo.id" class="todo-item"><span class="todo-item__mark" :class="{ 'is-overdue': todo.overdue }">{{ todo.overdue ? '!' : '·' }}</span><div class="todo-item__content"><strong>{{ todo.title }}</strong><small>{{ todo.due_at }}</small></div><span class="todo-item__type">{{ todo.type }}</span></div></div></section>
      </div>
      <section v-if="productionAvailable" class="page-card batch-strip"><div class="section-head"><div><p class="section-label">Production pulse</p><h2 class="section-title">近期批次</h2><p class="section-subtitle">批次存量来自 batch_stock_records 流水汇总</p></div><RouterLink class="ghost-action" to="/batches">批次管理</RouterLink></div><table class="batch-table"><thead><tr><th>批次</th><th>塘口</th><th>状态</th><th>当前存量</th><th>预计出塘</th></tr></thead><tbody><tr v-for="batch in summary.recent_batches" :key="batch.id"><td><RouterLink class="table-link" :to="`/batches/${batch.id}`"><strong>{{ batch.batch_code }}</strong></RouterLink><small>{{ batch.name }}</small></td><td>{{ batch.pond_names.join('、') }}</td><td><StatusBadge :label="batch.status_label" :tone="statusTones[batch.status]" /></td><td class="table-number">{{ batch.current_stock.toLocaleString() }} {{ batch.stock_unit }}</td><td>{{ batch.expected_harvest_date }}</td></tr></tbody></table></section>
      <section class="dashboard-grid" style="margin-top: 18px"><div class="page-card dashboard-card"><div class="section-head"><div><p class="section-label">Alerts</p><h2 class="section-title">预警与消息</h2><p class="section-subtitle">口径：消息中心汇总。库存类预警数量以仓储预警页（/warehouse/alerts）实时计算为准。</p></div><RouterLink class="ghost-action" to="/messages">查看消息</RouterLink></div><div class="alert-list"><div v-for="alert in summary.alerts" :key="alert.id" class="alert-item"><i class="alert-item__dot" :class="{ 'is-high': alert.level === 'high' }" /><div class="alert-item__content"><strong>{{ alert.title }}</strong><small>{{ alert.created_at }}</small></div><StatusBadge :label="alert.level === 'high' ? '高' : '中'" :tone="alert.level === 'high' ? 'rose' : 'amber'" /></div></div></div><div class="page-card dashboard-card"><div class="section-head"><div><p class="section-label">Next modules</p><h2 class="section-title">业务快捷入口</h2></div></div><div class="stack-list"><RouterLink class="management-link" to="/ponds"><span><strong>塘口档案</strong><small>状态、生命周期与时间线</small></span><b>→</b></RouterLink><RouterLink class="management-link" to="/batches"><span><strong>养殖批次</strong><small>批次状态与当前存量</small></span><b>→</b></RouterLink></div></div></section>
    </template>
  </AppShell>
</template>
