<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'

import type { AllocationRule, AllocationRuleVersion, CostCategorySummary, CostEntry, CostEntryPage, CostStructure, SaveAllocationRules } from '../../common/api/cost.models'
import ActionButton from '../../common/ui/ActionButton.vue'
import AppShell from '../../common/ui/AppShell.vue'
import StatusBadge from '../../common/ui/StatusBadge.vue'
import { hasPermission } from '../../common/security/access-control'
import { createSessionStore } from '../../common/session/session.store'
import { getAllocationRules, getCostEntries, getCostStructure, getLatestAllocationRules, saveAllocationRules } from '../../features/cost/cost.service'
import { DRIVER_LABELS, DRIVER_OPTIONS, downloadCostCsv, firstDayOfNextMonth, formatMoney, formatShare, localDate, manualRatios, safeBarWidth, trapFocus } from './cost-page.helpers'
import CostSummaryKpis from './CostSummaryKpis.vue'
const today = new Date()
const session = createSessionStore()
const canManageAllocation = computed(() => hasPermission(session.user.value, 'cost.allocation.manage'))
const periodStart = ref(`${today.getFullYear()}-01-01`)
const periodEnd = ref(localDate(today))
const structure = ref<CostStructure | null>(null)
const currentRules = ref<AllocationRuleVersion | null>(null)
const latestRules = ref<AllocationRuleVersion | null>(null)
const selectedEntries = ref<CostEntryPage | null>(null)
const selectedCategory = ref<CostCategorySummary | null>(null)
const loading = ref(true)
const loadError = ref('')
const detailLoading = ref(false)
const detailError = ref('')
const allocationModalOpen = ref(false)
const saveLoading = ref(false)
const saveError = ref('')
const changeReason = ref('')
const effectiveFrom = ref(firstDayOfNextMonth())
const ruleDraft = ref<AllocationRule[]>([])
const manualRatioText = ref<Record<number, string>>({})
const detailTrigger = ref<HTMLElement | null>(null)
const drawerPanel = ref<HTMLElement | null>(null)
const allocationTrigger = ref<HTMLElement | null>(null)
const allocationPanel = ref<HTMLElement | null>(null)
const allocationFirstInput = ref<HTMLInputElement | null>(null)
const toasts = ref<Array<{ id: number; text: string }>>([])
const rows = computed(() => structure.value?.categories ?? [])
const hasRows = computed(() => Boolean(structure.value?.has_data))
const displayRows = computed(() => hasRows.value ? rows.value : [])
const scheduledRules = computed(() => {
  if (!latestRules.value || !currentRules.value || latestRules.value.id === currentRules.value.id) return null
  return latestRules.value.effective_from > periodEnd.value ? latestRules.value : null
})
const effectiveDriverByCategory = computed(() => new Map(
  (currentRules.value?.rules ?? []).map((item) => [item.category_id, item.driver]),
))
const formatPeriod = computed(() => `${periodStart.value.split('-').join('.')}—${periodEnd.value.split('-').join('.')}`)
const minimumEffectiveFrom = computed(() => {
  const latestDate = latestRules.value ? new Date(`${latestRules.value.effective_from}T00:00:00`) : new Date()
  const afterLatest = firstDayOfNextMonth(latestDate)
  return afterLatest > firstDayOfNextMonth() ? afterLatest : firstDayOfNextMonth()
})
function toast(text: string) {
  const id = Date.now() + Math.random()
  toasts.value.push({ id, text })
  window.setTimeout(() => { toasts.value = toasts.value.filter((item) => item.id !== id) }, 3000)
}
function sourceDescription(entry: CostEntry) {
  if (entry.source_detail_json?.note) return String(entry.source_detail_json.note)
  if (entry.source_detail_json?.purchase_order_id) return `采购单 #${entry.source_detail_json.purchase_order_id} · 库存流水 #${entry.source_detail_json.inventory_ledger_id}`
  return '—'
}
async function loadPage() {
  loading.value = true
  loadError.value = ''
  try {
    ;[structure.value, currentRules.value, latestRules.value] = await Promise.all([
      getCostStructure(periodStart.value, periodEnd.value),
      getAllocationRules(periodEnd.value),
      getLatestAllocationRules(),
    ])
  } catch {
    structure.value = null
    currentRules.value = null
    latestRules.value = null
    loadError.value = '成本数据加载失败，请检查服务后重试'
  } finally {
    loading.value = false
  }
}
async function openEntries(category: CostCategorySummary, event: Event) {
  detailTrigger.value = event.currentTarget as HTMLElement
  selectedCategory.value = category
  selectedEntries.value = null
  detailLoading.value = true
  detailError.value = ''
  await nextTick()
  drawerPanel.value?.querySelector<HTMLElement>('button')?.focus()
  try {
    selectedEntries.value = await getCostEntries(category.code, periodStart.value, periodEnd.value)
  } catch {
    detailError.value = '来源明细加载失败，请稍后重试'
  } finally {
    detailLoading.value = false
  }
}
async function closeEntries() {
  selectedCategory.value = null
  selectedEntries.value = null
  await nextTick()
  detailTrigger.value?.focus()
}
async function openAllocation(event?: Event) {
  const draftSource = latestRules.value ?? currentRules.value
  if (!draftSource || !canManageAllocation.value) return
  allocationTrigger.value = event?.currentTarget as HTMLElement | null
  changeReason.value = ''
  effectiveFrom.value = minimumEffectiveFrom.value
  saveError.value = ''
  ruleDraft.value = draftSource.rules.map((item) => ({
    ...item,
    manual_ratio_json: item.manual_ratio_json ? { ...item.manual_ratio_json } : null,
  }))
  manualRatioText.value = Object.fromEntries(ruleDraft.value.map((item) => [
    item.category_id,
    item.manual_ratio_json ? JSON.stringify(item.manual_ratio_json, null, 2) : '',
  ]))
  allocationModalOpen.value = true
  await nextTick()
  allocationFirstInput.value?.focus()
}
async function closeAllocation() {
  allocationModalOpen.value = false
  await nextTick()
  allocationTrigger.value?.focus()
}
function trapAllocationFocus(event: KeyboardEvent) {
  trapFocus(allocationPanel.value, event)
}

function trapDrawerFocus(event: KeyboardEvent) {
  trapFocus(drawerPanel.value, event)
}
async function submitRules() {
  if (!changeReason.value.trim()) {
    saveError.value = '请填写修改原因'
    return
  }
  let payload: SaveAllocationRules
  try {
    payload = {
      effective_from: effectiveFrom.value,
      change_reason: changeReason.value.trim(),
      rules: ruleDraft.value.map((item) => ({
        category_id: item.category_id,
        driver: item.driver,
        manual_ratio_json: manualRatios(item, manualRatioText.value[item.category_id]),
      })),
    }
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : '手工比例格式无效'
    return
  }
  saveLoading.value = true
  saveError.value = ''
  try {
    latestRules.value = await saveAllocationRules(payload)
    toast(`规则版本 v${latestRules.value.version_no} 已保存`)
    await closeAllocation()
  } catch {
    saveError.value = '分摊规则保存失败，请修正后重试'
  } finally {
    saveLoading.value = false
  }
}
function exportCost() {
  if (!structure.value) return
  downloadCostCsv(structure.value, displayRows.value, effectiveDriverByCategory.value, periodEnd.value)
  toast(`已导出 ${displayRows.value.length} 个成本类别的明细`)
}
onMounted(loadPage)
</script>

<template>
  <AppShell title="成本构成">
    <div class="page-title cost-title">
      <div>
        <p class="section-label">Cost &amp; operations / Structure</p>
        <h1>成本构成</h1>
        <p>九类成本统一归集、来源可追溯，公共成本按版本规则流向塘口与批次。</p>
      </div>
      <div class="page-title__actions">
        <ActionButton icon="download" :disabled="!hasRows" @click="exportCost">导出明细</ActionButton>
        <ActionButton v-if="canManageAllocation" data-testid="open-allocation-rules" variant="primary" icon="edit" :disabled="!currentRules" @click="openAllocation">调整分摊规则</ActionButton>
        <StatusBadge v-else label="仅查看" tone="blue" />
      </div>
    </div>

    <p v-if="loadError" class="cost-feedback cost-feedback--error" role="alert">
      {{ loadError }}
      <button type="button" @click="loadPage">重新加载</button>
    </p>
    <p v-else-if="loading" class="cost-feedback" role="status">正在读取成本数据…</p>

    <template v-else-if="structure">
      <div class="cost-context">
        <span>{{ formatPeriod }}</span>
        <StatusBadge :label="structure.source_quality === 'legacy_import' ? '初始化数据 · 待核验' : '来源已核验'" :tone="structure.source_quality === 'legacy_import' ? 'amber' : 'teal'" />
        <span v-if="currentRules" class="cost-context__rules">当前规则 v{{ currentRules.version_no }} · {{ currentRules.change_reason }} · {{ currentRules.created_by_name || '系统初始化' }}</span>
        <span v-if="scheduledRules" class="cost-context__scheduled">待生效规则 v{{ scheduledRules.version_no }} · {{ scheduledRules.effective_from }} 生效 · {{ scheduledRules.created_by_name || '系统' }}</span>
      </div>

      <CostSummaryKpis :structure="structure" />

      <section class="page-card cost-breakdown">
        <div class="section-head">
          <div>
            <p class="section-label">Cost breakdown</p>
            <h2 class="section-title">类别构成与分摊规则</h2>
            <p class="section-subtitle">条形按服务端占比等比例展示；点击类别查看来源凭证。</p>
          </div>
          <StatusBadge label="口径：已确认记录" tone="blue" />
        </div>

        <div class="cost-table-head" aria-hidden="true"><span>类别</span><span>构成占比</span><span>金额</span><span>分摊依据</span></div>
        <button
          v-for="item in displayRows"
          :key="item.code"
          :data-testid="`cost-row-${item.code}`"
          class="cost-row"
          type="button"
          @click="openEntries(item, $event)"
        >
          <span class="cost-row__name"><i :class="`cost-nature cost-nature--${item.nature}`" />{{ item.name }}<small>{{ item.nature === 'direct' ? '直接' : '公共' }}</small></span>
          <span class="cost-row__bar"><i :class="`cost-row__fill cost-row__fill--${item.nature}`" :style="{ width: safeBarWidth(item.share) }" /></span>
          <span class="cost-row__amount"><strong>{{ formatMoney(item.amount) }}</strong><small>{{ formatShare(item.share) }}</small></span>
          <span class="cost-row__driver">{{ DRIVER_LABELS[effectiveDriverByCategory.get(item.id) ?? item.allocation_driver] }}<small>零基数时平均分摊</small></span>
        </button>
        <p v-if="!hasRows" class="cost-feedback">当前期间暂无已确认成本记录。</p>
      </section>
    </template>

    <Teleport to="body">
      <div v-if="allocationModalOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="allocation-title" @keydown.esc.stop.prevent="closeAllocation">
        <div ref="allocationPanel" class="modal-panel allocation-panel" @keydown.tab="trapAllocationFocus">
          <div class="modal-panel__head">
            <div><p class="section-label">Allocation rules</p><h2 id="allocation-title">分摊规则版本调整</h2></div>
            <ActionButton variant="quiet" compact icon="close" label="关闭分摊规则" @click="closeAllocation" />
          </div>
          <p class="section-subtitle">新规则从未来月份首日生效；历史期间保留原版本，不回溯覆盖。</p>
          <div class="allocation-meta">
            <label><span>生效日期</span><input id="allocation-effective-date" ref="allocationFirstInput" v-model="effectiveFrom" class="filter-input" type="date" :min="minimumEffectiveFrom" /></label>
            <label><span>修改原因</span><input id="allocation-reason" v-model="changeReason" class="filter-input" maxlength="500" placeholder="说明本次调整依据" /></label>
          </div>
          <div class="allocation-rules">
            <div v-for="rule in ruleDraft" :key="rule.category_id" class="allocation-rule">
              <label><span>{{ rule.category_name }}</span><select v-model="rule.driver" class="filter-select"><option v-for="option in DRIVER_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
              <label v-if="rule.driver === 'manual_ratio'" class="allocation-rule__manual"><span>比例 JSON（键为目标编号，值合计为 1）</span><textarea v-model="manualRatioText[rule.category_id]" placeholder='{"pond-1":"0.6","pond-2":"0.4"}' /></label>
            </div>
          </div>
          <p v-if="saveError" data-testid="allocation-error" class="cost-feedback cost-feedback--error" role="alert">{{ saveError }}</p>
          <div class="modal-panel__foot">
            <ActionButton :disabled="saveLoading" @click="closeAllocation">取消</ActionButton>
            <ActionButton data-testid="save-allocation-rules" variant="primary" icon="save" :loading="saveLoading" @click="submitRules">保存新版本</ActionButton>
          </div>
        </div>
      </div>

      <div v-if="selectedCategory" class="cost-drawer-overlay" @click.self="closeEntries">
        <aside ref="drawerPanel" data-testid="cost-entry-drawer" class="cost-drawer" role="dialog" aria-modal="true" :aria-label="`${selectedCategory.name}来源明细`" @keydown.esc.stop.prevent="closeEntries" @keydown.tab="trapDrawerFocus">
          <header><div><p class="section-label">Source trace</p><h2>{{ selectedCategory.name }}来源明细</h2></div><ActionButton variant="quiet" compact icon="close" label="关闭来源明细" @click="closeEntries" /></header>
          <p class="section-subtitle">仅展示当前期间已确认、参与成本核算的记录。</p>
          <p v-if="detailLoading" class="cost-feedback" role="status">正在读取来源明细…</p>
          <p v-else-if="detailError" class="cost-feedback cost-feedback--error" role="alert">{{ detailError }}</p>
          <p v-else-if="!selectedEntries?.items.length" class="cost-feedback">暂无来源记录。</p>
          <article v-for="entry in selectedEntries?.items ?? []" :key="entry.id" class="source-entry">
            <div><strong>{{ formatMoney(entry.amount) }}</strong><span>{{ entry.occurred_on }}</span></div>
            <dl><div><dt>来源类型</dt><dd>{{ entry.source_type }}</dd></div><div><dt>来源编号</dt><dd>{{ entry.source_ref }}</dd></div><div><dt>归集期间</dt><dd>{{ entry.period_start }}—{{ entry.period_end }}</dd></div><div><dt>来源说明</dt><dd>{{ sourceDescription(entry) }}</dd></div></dl>
          </article>
        </aside>
      </div>

      <div class="toast-stack" aria-live="polite"><div v-for="item in toasts" :key="item.id" class="toast-item">{{ item.text }}</div></div>
    </Teleport>
  </AppShell>
</template>

<style scoped>
.cost-title{align-items:center}.cost-context{display:flex;align-items:center;gap:10px;min-height:38px;margin:-10px 0 16px;color:var(--wb-muted);font-size:12px}.cost-context>span:last-child{margin-left:auto}.cost-feedback{padding:18px;border:1px dashed var(--wb-line);border-radius:12px;color:var(--wb-muted);background:rgba(255,255,255,.72)}.cost-feedback--error{border-color:#efcfcc;color:#a64f4a;background:#fff8f7}.cost-feedback button{margin-left:10px;border:0;color:var(--wb-teal);background:transparent;font-weight:750;cursor:pointer}.kpi-card::after{display:none}.kpi-card__icon--amber{color:#b97735;background:#fff4e7}.cost-breakdown{padding:24px}.cost-table-head,.cost-row{display:grid;grid-template-columns:minmax(110px,.65fr) minmax(220px,1.7fr) minmax(150px,.8fr) minmax(170px,1fr);gap:20px;align-items:center}.cost-table-head{padding:0 14px 10px;color:#8a9996;font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.cost-row{width:100%;padding:15px 14px;border:0;border-top:1px solid #eaf1ef;color:inherit;background:transparent;text-align:left;cursor:pointer;transition:background .16s,transform .16s}.cost-row:hover{background:#f6fbfa}.cost-row:focus-visible{position:relative;outline:2px solid #73bcb1;outline-offset:-2px}.cost-row__name{display:flex;align-items:center;gap:8px;font-weight:800}.cost-row__name small{padding:2px 6px;border-radius:999px;color:#708c87;background:#eef6f4;font-size:10px}.cost-nature{width:8px;height:8px;border-radius:50%}.cost-nature--direct{background:#cf8b45}.cost-nature--public{background:#348c83}.cost-row__bar{height:10px;overflow:hidden;border-radius:999px;background:#edf3f2}.cost-row__fill{display:block;height:100%;min-width:3px;border-radius:inherit}.cost-row__fill--direct{background:#cf8b45}.cost-row__fill--public{background:#348c83}.cost-row__amount,.cost-row__driver{display:flex;flex-direction:column;gap:3px}.cost-row__amount strong{font-variant-numeric:tabular-nums}.cost-row__amount small,.cost-row__driver small{color:var(--wb-muted);font-size:11px}.allocation-panel{width:min(760px,100%)}.allocation-meta{display:grid;grid-template-columns:190px 1fr;gap:14px;margin:18px 0}.allocation-meta label,.allocation-rule label{display:grid;gap:7px;color:#506763;font-size:12px;font-weight:750}.allocation-rules{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.allocation-rule{padding:12px;border:1px solid #e3efec;border-radius:10px;background:#f9fcfb}.allocation-rule .filter-select{width:100%}.allocation-rule__manual{margin-top:10px}.allocation-rule__manual textarea{min-height:76px;padding:9px;border:1px solid var(--wb-line);border-radius:8px;resize:vertical}.cost-drawer-overlay{position:fixed;z-index:65;inset:0;background:rgba(23,46,44,.34)}.cost-drawer{position:absolute;inset:0 0 0 auto;width:min(520px,100%);overflow-y:auto;padding:26px;background:#fff;box-shadow:-20px 0 56px rgba(20,50,48,.2)}.cost-drawer header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.cost-drawer h2{margin:4px 0 0}.source-entry{margin-top:16px;padding:16px;border:1px solid var(--wb-line);border-radius:12px;background:#fbfdfd}.source-entry>div{display:flex;align-items:center;justify-content:space-between}.source-entry dl{display:grid;gap:9px;margin:14px 0 0}.source-entry dl div{display:grid;grid-template-columns:76px 1fr;gap:10px}.source-entry dt{color:var(--wb-muted);font-size:12px}.source-entry dd{margin:0;overflow-wrap:anywhere;font-size:13px}@media(max-width:1100px){.cost-table-head,.cost-row{grid-template-columns:110px 1fr 140px}.cost-table-head span:last-child,.cost-row__driver{display:none}}@media(max-width:760px){.cost-context{align-items:flex-start;flex-direction:column}.cost-context>span:last-child{margin-left:0}.cost-table-head{display:none}.cost-row{grid-template-columns:1fr auto;gap:8px}.cost-row__bar{grid-column:1/-1;grid-row:2}.cost-row__amount{text-align:right}.allocation-meta,.allocation-rules{grid-template-columns:1fr}.cost-breakdown{padding:18px}}
</style>
