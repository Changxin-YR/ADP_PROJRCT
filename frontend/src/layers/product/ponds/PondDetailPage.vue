<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../../common/ui/AppShell.vue'
import StatusBadge from '../../common/ui/StatusBadge.vue'
import { ApiError, isNetworkError, messageWithContext, submitErrorText } from '../../common/api/errors'
import { useSubmitGuard } from '../../common/ui/useSubmitGuard'
import { getPond, getPondStockSummary } from '../../features/workbench/workbench.service'
import type { PondStockSummary } from '../../common/api/workbench.models'
import { requestPondStatusChange, updateMasterRecord, verifyPondStatusChange } from '../../features/master-data/master-data.service'
import type { PondDetail, PondStatus } from '../../common/api/workbench.models'

const route = useRoute()

// 汇总数值统一按服务端字符串口径渲染（DECIMAL(18,3) → 本地千分位）
function numberText(value?: string | number | null) {
  if (value == null || value === '') return '0'
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric.toLocaleString() : String(value)
}

const pond = ref<PondDetail>()
const loading = ref(true)
const pageError = ref('')
const labels: Record<PondStatus, string> = { build: '筹建', stocked: '已放养', farming: '养殖中', rest: '轮休', clean: '清塘', rebuild: '改造' }
const formalLabels = { draft: '草稿', submitted: '待核验', verified: '已核验', archived: '已归档' } as const
const statusTones: Record<PondStatus, 'teal' | 'blue' | 'amber' | 'slate'> = { farming: 'teal', stocked: 'blue', build: 'slate', rest: 'amber', clean: 'blue', rebuild: 'slate' }
const transitions: Record<PondStatus, PondStatus[]> = { build: ['stocked'], stocked: ['farming'], farming: ['rest', 'clean'], rest: ['stocked', 'rebuild'], clean: ['rest', 'rebuild'], rebuild: ['build'] }
const canEdit = computed(() => pond.value?.allowed_actions.includes('edit') ?? false)
const allowedTargets = computed(() => pond.value?.status_change_targets ?? (pond.value ? transitions[pond.value.status] : []))
const canRequestStatus = computed(() => pond.value?.can_request_status_change ?? false)
const canVerifyStatus = computed(() => pond.value?.can_verify_status_change ?? false)
const pageNotice = ref('')
// 塘口扩展字段（BUG-007）：存塘量来源标识
const stockSourceLabels: Record<string, string> = { estimated: '系统估算', manual: '人工录入', measured: '现场实测', sampled: '抽样', corrected: '人工修正' }
const stockSourceLabel = computed(() => pond.value?.stock_quantity_source ? (stockSourceLabels[pond.value.stock_quantity_source] ?? pond.value.stock_quantity_source) : '未标注')
const stockQuantityText = computed(() => (pond.value?.stock_quantity ?? '') === '' || pond.value?.stock_quantity == null ? '—' : `${Number(pond.value.stock_quantity).toLocaleString()} 尾`)

// 存塘量（生产事实汇总）：只读展示，失败时明确提示，绝不用档案手工值冒充批次流水
const stockSummary = ref<PondStockSummary | null>(null)
const stockLoading = ref(false)
const stockError = ref('')
const stockDataSourceLabels: Record<string, string> = { batch_ledger: '批次流水（生产事实）', manual: '档案手工值（无批次流水兜底）', none: '暂无数据' }
const batchStatusLabels: Record<string, string> = { stocked: '已放养', farming: '养殖中', pending_settlement: '待结算', closed: '已关闭' }
const dataSourceLabel = computed(() => stockDataSourceLabels[stockSummary.value?.data_source ?? 'none'] ?? '暂无数据')
const ledgerQuantityText = computed(() => `${numberText(stockSummary.value?.batch_stock?.quantity)} 尾`)
const ledgerWeightText = computed(() => `${numberText(stockSummary.value?.batch_stock?.weight_kg)} kg`)
const manualStockText = computed(() => {
  const manual = stockSummary.value?.manual_stock?.quantity
  if (manual == null || manual === '') return pond.value?.stock_quantity == null ? '—' : `${Number(pond.value.stock_quantity).toLocaleString()} 尾`
  return `${numberText(manual)} 尾`
})
// 差异只做克制提示：档案手工值与批次流水口径不同，不代表任一方错误
const stockMismatch = computed(() => {
  const summary = stockSummary.value
  const manual = summary?.manual_stock?.quantity
  if (!summary || summary.data_source !== 'batch_ledger' || manual == null || manual === '') return false
  return Math.abs(Number(manual) - Number(summary.batch_stock?.quantity ?? 0)) > 0.0005
})

const STOCK_LOAD_FAILED = '存塘量（批次流水）加载失败'
// 失败文案必须是通俗中文：服务端 5xx 会带 request_id（技术标识），这里统一换成「请稍后重试」；
// 403（无权限）等业务提示保留原文，方便用户知道该找谁开权限。
function stockErrorText(error: unknown) {
  if (error instanceof ApiError && (error.status >= 500 || isNetworkError(error))) return `${STOCK_LOAD_FAILED}，请稍后重试`
  return messageWithContext(error, STOCK_LOAD_FAILED)
}

async function loadStock() {
  stockLoading.value = true; stockError.value = ''
  try { stockSummary.value = await getPondStockSummary(Number(route.params.id)) }
  catch (error) { stockSummary.value = null; stockError.value = stockErrorText(error) }
  finally { stockLoading.value = false }
}

async function load() {
  loading.value = true; pageError.value = ''
  try { pond.value = await getPond(Number(route.params.id)) }
  catch (error) { pageError.value = error instanceof ApiError ? error.message : '塘口详情加载失败，请稍后重试'; stockSummary.value = null; stockError.value = ''; return }
  finally { loading.value = false }
  await loadStock()
}
onMounted(load)

const statusModalOpen = ref(false)
const statusForm = reactive<{ next: PondStatus | ''; note: string }>({ next: '', note: '' })
const statusError = ref('')
function openStatusModal() { if (!canRequestStatus.value) return; statusForm.next = ''; statusForm.note = ''; statusError.value = ''; statusModalOpen.value = true }
const { busy: statusSubmitting, run: runStatusSubmit } = useSubmitGuard()
async function submitStatus() {
  if (!pond.value || !statusForm.next) { statusError.value = '请选择变更后的状态'; return }
  if (!allowedTargets.value.includes(statusForm.next)) { statusError.value = '该流转路径不符合状态规则'; return }
  if (!statusForm.note.trim()) { statusError.value = '请填写变更原因，便于后续追溯'; return }
  statusError.value = ''
  await runStatusSubmit(async () => {
    try {
      await requestPondStatusChange(pond.value!.id, { to_status: statusForm.next, reason: statusForm.note.trim(), expected_version: pond.value!.version })
      statusModalOpen.value = false; pageNotice.value = '状态变更已提交，需由另一名核验人员确认后生效。'; await load()
    } catch (error) { statusError.value = submitErrorText(error, '状态变更失败，请刷新后重试') }
  })
}

const verifyModalOpen = ref(false)
const verifyError = ref('')
const { busy: verifySubmitting, run: runVerifySubmit } = useSubmitGuard()
async function submitStatusVerification() {
  const change = pond.value?.pending_status_change
  if (!pond.value || !change || !canVerifyStatus.value) return
  verifyError.value = ''
  await runVerifySubmit(async () => {
    try {
      await verifyPondStatusChange(pond.value!.id, change.id, change.row_version, pond.value!.version)
      verifyModalOpen.value = false; pageNotice.value = '状态变更核验完成，塘口当前状态已更新。'; await load()
    } catch (error) { verifyError.value = submitErrorText(error, '状态核验失败，请刷新后重试') }
  })
}

const editModalOpen = ref(false)
const editForm = reactive({ name: '', species: '', capacity_mu: 0, manager_name: '', notes: '', aerator_count: 0, stocking_spec: '', current_spec: '', stock_quantity: 0, stock_quantity_source: '' })
const editError = ref('')
function openEditModal() {
  if (!pond.value || !canEdit.value) return
  Object.assign(editForm, {
    name: pond.value.name, species: pond.value.species, capacity_mu: pond.value.capacity_mu, manager_name: pond.value.manager_name, notes: pond.value.notes,
    aerator_count: Number(pond.value.aerator_count ?? 0), stocking_spec: pond.value.stocking_spec ?? '', current_spec: pond.value.current_spec ?? '',
    stock_quantity: Number(pond.value.stock_quantity ?? 0), stock_quantity_source: pond.value.stock_quantity_source ?? '',
  })
  editError.value = ''; editModalOpen.value = true
}
const { busy: editSubmitting, run: runEditSubmit } = useSubmitGuard()
async function submitEdit() {
  if (!pond.value || !editForm.name.trim()) { editError.value = '请填写塘口名称'; return }
  const aeratorCount = Number(editForm.aerator_count)
  if (!Number.isInteger(aeratorCount) || aeratorCount < 0) { editError.value = '增氧机数量必须为不小于 0 的整数'; return }
  const stockQuantity = Number(editForm.stock_quantity)
  if (!Number.isFinite(stockQuantity) || stockQuantity < 0) { editError.value = '当前存塘量必须为不小于 0 的数字'; return }
  editError.value = ''
  await runEditSubmit(async () => {
    try {
      await updateMasterRecord('ponds', pond.value!.id, {
        name: editForm.name.trim(), species: editForm.species.trim(), capacity_mu: editForm.capacity_mu, manager_name: editForm.manager_name.trim(), description: editForm.notes.trim(),
        aerator_count: aeratorCount, stocking_spec: editForm.stocking_spec.trim(), current_spec: editForm.current_spec.trim(),
        stock_quantity: stockQuantity, stock_quantity_source: editForm.stock_quantity_source,
        expected_version: pond.value!.version,
      })
      editModalOpen.value = false; await load()
    } catch (error) { editError.value = submitErrorText(error, '塘口保存失败，请刷新后重试') }
  })
}
</script>

<template>
  <AppShell title="塘口档案" :breadcrumbs="['塘口详情']">
    <div v-if="loading" class="page-card table-empty">正在加载塘口详情…</div>
    <div v-else-if="pageError" class="page-card table-empty" role="alert">{{ pageError }}<div style="margin-top:12px"><button class="ghost-action" type="button" @click="load">重新加载</button></div></div>
    <div v-else-if="pond">
      <div class="page-title"><div><p class="section-label">Pond detail / {{ pond.pond_code }}</p><h1>{{ pond.name }}</h1><p>{{ pond.area_name }} · {{ pond.group_name }} · 最近更新 {{ pond.updated_at }}</p></div><div v-if="canEdit || canRequestStatus || canVerifyStatus" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><button v-if="canEdit" class="ghost-action" type="button" @click="openEditModal">编辑塘口</button><button v-if="canRequestStatus" class="primary-action" data-testid="request-pond-status" type="button" @click="openStatusModal">申请状态变更</button><button v-if="canVerifyStatus" class="primary-action" data-testid="verify-pond-status" type="button" @click="verifyModalOpen = true">核验状态变更</button></div></div>
      <p v-if="pageNotice" class="success-message" role="status">{{ pageNotice }}</p>
      <section v-if="pond.pending_status_change" class="page-card" style="margin-bottom:18px;padding:18px"><strong>待核验状态变更：{{ labels[pond.pending_status_change.from_status] }} → {{ labels[pond.pending_status_change.to_status] }}</strong><p class="section-subtitle">原因：{{ pond.pending_status_change.reason }}</p></section>
      <div class="detail-grid"><section class="page-card detail-card"><div class="detail-status"><div><h1>当前状态</h1><p>养殖状态与录入核验状态分开管理，核验后资料只读。</p></div><StatusBadge :label="labels[pond.status]" :tone="statusTones[pond.status]" /></div><dl class="detail-meta"><div><dt>塘口编码</dt><dd>{{ pond.pond_code }}</dd></div><div><dt>录入状态</dt><dd>{{ formalLabels[pond.lifecycle_status] }} · v{{ pond.version }}</dd></div><div><dt>养殖面积</dt><dd>{{ pond.capacity_mu }} 亩</dd></div><div><dt>养殖品种</dt><dd>{{ pond.species }}</dd></div><div><dt>活跃批次</dt><dd>{{ pond.active_batch_count }} 个</dd></div><div><dt>所属区域</dt><dd>{{ pond.area_name }}</dd></div><div><dt>增氧机数量</dt><dd>{{ pond.aerator_count ?? '—' }} 台</dd></div><div><dt>投苗规格</dt><dd>{{ pond.stocking_spec || '—' }}</dd></div><div><dt>当前规格</dt><dd>{{ pond.current_spec || '—' }}</dd></div></dl><div style="margin-top:28px" class="section-head"><div><p class="section-label">Lifecycle timeline</p><h2 class="section-title">生命周期时间线</h2><p class="section-subtitle">状态变更与资料修改均由服务端审计记录生成</p></div></div><div class="timeline-list"><div v-for="event in pond.timeline_preview" :key="event.id" class="timeline-event"><strong>{{ event.title }}</strong><p>{{ event.description }}</p><small>{{ event.happened_at }} · {{ event.operator_name }}</small></div><div v-if="!pond.timeline_preview.length" class="table-empty">暂无可显示的历史事件</div></div></section><aside class="page-card detail-card"><div class="section-head"><div><p class="section-label">Basic profile</p><h2 class="section-title">基础资料</h2></div><StatusBadge :label="formalLabels[pond.lifecycle_status]" :tone="pond.lifecycle_status === 'verified' ? 'teal' : 'amber'" /></div><dl class="info-list"><div><dt>塘口位置</dt><dd>{{ pond.location }}</dd></div><div><dt>水源</dt><dd>{{ pond.water_source }}</dd></div><div><dt>负责人</dt><dd>{{ pond.manager_name }}</dd></div><div><dt>当前分组</dt><dd>{{ pond.group_name }}</dd></div><div><dt>档案手工存塘量</dt><dd data-testid="pond-stock-quantity">{{ stockQuantityText }}</dd></div><div><dt>存塘量来源</dt><dd data-testid="pond-stock-source">{{ stockSourceLabel }}</dd></div><div><dt>备注</dt><dd>{{ pond.notes }}</dd></div></dl>
        <section class="page-card pond-stock-card" aria-label="存塘量生产事实汇总">
          <div class="section-head"><div><p class="section-label">Stock ledger</p><h2 class="section-title">存塘量（批次流水）</h2>
            <p class="section-subtitle">由批次生产事实（放养/转塘/损耗/出塘核验）与已核验抽样汇总得出，只读；塘口档案的手工值不会被回写。</p></div>
            <StatusBadge :label="dataSourceLabel" :tone="stockSummary?.data_source === 'batch_ledger' ? 'teal' : stockSummary?.data_source === 'manual' ? 'amber' : 'slate'" /></div>
          <p v-if="stockError" class="stock-notice" role="alert" data-testid="pond-stock-error">{{ stockError }}<button class="ghost-action" type="button" data-testid="pond-stock-retry" @click="loadStock">重新加载存塘量</button></p>
          <template v-else>
            <dl class="detail-meta pond-stock-metrics">
              <div><dt>存塘量（批次流水）</dt><dd data-testid="pond-stock-ledger-quantity">{{ stockLoading ? '加载中…' : ledgerQuantityText }}</dd></div>
              <div><dt>存塘重量（批次流水）</dt><dd data-testid="pond-stock-ledger-weight">{{ stockLoading ? '加载中…' : ledgerWeightText }}</dd></div>
              <div><dt>档案手工值（仅供参考）</dt><dd data-testid="pond-stock-manual-quantity">{{ manualStockText }}</dd></div>
              <div><dt>档案规格 / 规格来源</dt><dd>{{ stockSummary?.manual_stock?.current_spec || pond.current_spec || '—' }} · {{ stockSourceLabel }}</dd></div>
              <div><dt>在塘批次</dt><dd data-testid="pond-stock-batch-count">{{ stockSummary ? (stockSummary.batches ?? []).length : '—' }} 个</dd></div>
            </dl>
            <p v-if="stockMismatch" class="stock-notice stock-notice--hint" role="status" data-testid="pond-stock-mismatch">档案手工值（{{ manualStockText }}）与批次流水（{{ ledgerQuantityText }}）不一致，建议以批次流水为准。</p>
            <h3 class="section-title pond-stock-subtitle">批次分布</h3>
            <table class="data-table"><thead><tr><th>批次</th><th>状态</th><th>存塘量</th><th>存塘重量</th><th>折算均重</th></tr></thead><tbody>
              <tr v-for="batch in stockSummary?.batches ?? []" :key="batch.batch_id"><td><strong>{{ batch.code || '—' }}</strong><small>{{ batch.name }}</small></td><td>{{ batchStatusLabels[batch.batch_status ?? ''] ?? batch.batch_status ?? '—' }}</td><td><span class="table-number">{{ numberText(batch.quantity) }} 尾</span></td><td><span class="table-number">{{ numberText(batch.weight_kg) }} kg</span></td><td><span class="table-number">{{ batch.avg_weight_kg ? `${numberText(batch.avg_weight_kg)} kg/尾` : '—' }}</span></td></tr>
              <tr v-if="!(stockSummary?.batches ?? []).length"><td colspan="5" class="table-empty">该塘口暂无批次流水（无放养/转塘/损耗/出塘核验事实）。</td></tr>
            </tbody></table>
            <h3 class="section-title pond-stock-subtitle">最近一次抽样</h3>
            <dl v-if="stockSummary?.latest_sampling" class="detail-meta pond-stock-metrics" data-testid="pond-stock-sampling">
              <div><dt>抽样时间</dt><dd>{{ stockSummary.latest_sampling.occurred_at || '—' }}</dd></div>
              <div><dt>样本数量</dt><dd>{{ numberText(stockSummary.latest_sampling.quantity) }} 尾</dd></div>
              <div><dt>样本重量</dt><dd>{{ numberText(stockSummary.latest_sampling.weight_kg) }} kg</dd></div>
              <div><dt>折算平均体重</dt><dd>{{ stockSummary.latest_sampling.avg_weight_kg ? `${numberText(stockSummary.latest_sampling.avg_weight_kg)} kg/尾` : '—' }}</dd></div>
            </dl>
            <p v-else class="table-empty" data-testid="pond-stock-sampling">暂无已核验抽样记录（仅已核验抽样计入规格事实）。</p>
          </template>
        </section></aside></div>
    </div>
    <div v-else class="page-card table-empty">塘口不存在或无权访问，<RouterLink class="table-link" to="/ponds">返回塘口列表</RouterLink></div>

    <Teleport to="body">
      <div v-if="statusModalOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="塘口状态变更"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">Status change request</p><h2>申请塘口状态变更</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="statusModalOpen = false">×</button></div><p class="section-subtitle">当前状态：{{ pond ? labels[pond.status] : '—' }} · 仅允许：{{ allowedTargets.map((item) => labels[item]).join(' / ') }}。提交后由另一名核验人员确认才会生效。</p><label class="modal-field"><span>变更后状态 *</span><select v-model="statusForm.next" class="filter-select" style="width:100%"><option value="">请选择状态</option><option v-for="target in allowedTargets" :key="target" :value="target">{{ labels[target] }}</option></select></label><label class="modal-field"><span>变更原因 *</span><textarea v-model="statusForm.note" class="filter-input" style="width:100%;min-height:84px;resize:vertical" /></label><p v-if="statusError" class="modal-error" role="alert">{{ statusError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="statusModalOpen = false">取消</button><button class="primary-action" data-testid="submit-pond-status" type="button" :disabled="statusSubmitting" :aria-busy="statusSubmitting" @click="submitStatus">{{ statusSubmitting ? '提交中…' : '提交核验' }}</button></div></div></div>
      <div v-if="verifyModalOpen && pond?.pending_status_change" class="modal-overlay" role="dialog" aria-modal="true" aria-label="核验塘口状态变更"><div class="modal-panel" style="width:min(500px,100%)"><div class="modal-panel__head"><div><p class="section-label">Verify status change</p><h2>核验塘口状态变更</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="verifyModalOpen = false">×</button></div><p class="section-subtitle">{{ labels[pond.pending_status_change.from_status] }} → {{ labels[pond.pending_status_change.to_status] }}<br>原因：{{ pond.pending_status_change.reason }}</p><p v-if="verifyError" class="modal-error" role="alert">{{ verifyError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="verifyModalOpen = false">取消</button><button class="primary-action" type="button" :disabled="verifySubmitting" :aria-busy="verifySubmitting" @click="submitStatusVerification">{{ verifySubmitting ? '提交中…' : '确认核验并生效' }}</button></div></div></div>
      <div v-if="editModalOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="编辑塘口资料"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">Edit profile</p><h2>编辑塘口资料</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="editModalOpen = false">×</button></div><label class="modal-field"><span>塘口名称 *</span><input v-model="editForm.name" class="filter-input" style="width:100%"></label><div class="modal-row"><label class="modal-field"><span>养殖品种</span><input v-model="editForm.species" class="filter-input" style="width:100%"></label><label class="modal-field"><span>养殖面积（亩）</span><input v-model.number="editForm.capacity_mu" type="number" min="0" step="0.1" class="filter-input" style="width:100%"></label><label class="modal-field"><span>增氧机数量（台）</span><input v-model.number="editForm.aerator_count" type="number" min="0" step="1" data-testid="pond-detail-aerator" class="filter-input" style="width:100%"></label><label class="modal-field"><span>投苗规格</span><input v-model="editForm.stocking_spec" class="filter-input" style="width:100%"></label><label class="modal-field"><span>当前规格</span><input v-model="editForm.current_spec" class="filter-input" style="width:100%"></label><label class="modal-field"><span>当前存塘量（尾，手工兜底）</span><input v-model.number="editForm.stock_quantity" type="number" min="0" data-testid="pond-detail-stock-quantity" class="filter-input" style="width:100%"><small class="stock-source-tag">仅供无批次流水时兜底，实际以批次流水与抽样事实为准</small></label><label class="modal-field"><span>存塘量来源</span><select v-model="editForm.stock_quantity_source" data-testid="pond-detail-stock-source" class="filter-select" style="width:100%"><option value="">未标注</option><option v-for="(label, value) in stockSourceLabels" :key="value" :value="value">{{ label }}</option></select></label></div><label class="modal-field"><span>负责人</span><input v-model="editForm.manager_name" class="filter-input" style="width:100%"></label><label class="modal-field"><span>备注</span><textarea v-model="editForm.notes" class="filter-input" style="width:100%;min-height:70px;resize:vertical" /></label><p v-if="editError" class="modal-error" role="alert">{{ editError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="editModalOpen = false">取消</button><button class="primary-action" type="button" :disabled="editSubmitting" :aria-busy="editSubmitting" @click="submitEdit">{{ editSubmitting ? '保存中…' : '保存修改' }}</button></div></div></div>
    </Teleport>
  </AppShell>
</template>

<style scoped>
.pond-stock-card { grid-column: 1 / -1; }
.pond-stock-card .pond-stock-metrics { margin-bottom: 12px; }
.pond-stock-subtitle { margin: 18px 0 8px; }
.stock-notice { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px; margin: 0 0 10px; color: #8a6d1f; background: #fdf6e3; border-radius: 8px; }
.stock-notice--hint { color: #7a6a3a; font-size: 13px; }
.stock-source-tag { display: block; color: #64748b; font-size: 11px; }
</style>
