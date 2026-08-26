<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../../common/ui/AppShell.vue'
import StatusBadge from '../../common/ui/StatusBadge.vue'
import { ApiError, submitErrorText } from '../../common/api/errors'
import { useSubmitGuard } from '../../common/ui/useSubmitGuard'
import { getPond } from '../../features/workbench/workbench.service'
import { requestPondStatusChange, updateMasterRecord, verifyPondStatusChange } from '../../features/master-data/master-data.service'
import type { PondDetail, PondStatus } from '../../common/api/workbench.models'

const route = useRoute()
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
const stockSourceLabels: Record<string, string> = { system_estimated: '系统估算', manual_entry: '人工录入', field_measured: '现场实测', sampling: '抽样', manual_correction: '人工修正' }
const stockSourceLabel = computed(() => pond.value?.stock_quantity_source ? (stockSourceLabels[pond.value.stock_quantity_source] ?? pond.value.stock_quantity_source) : '未标注')
const stockQuantityText = computed(() => (pond.value?.stock_quantity ?? '') === '' || pond.value?.stock_quantity == null ? '—' : `${Number(pond.value.stock_quantity).toLocaleString()} 尾`)

async function load() {
  loading.value = true; pageError.value = ''
  try { pond.value = await getPond(Number(route.params.id)) }
  catch (error) { pageError.value = error instanceof ApiError ? error.message : '塘口详情加载失败，请稍后重试' }
  finally { loading.value = false }
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
      <div class="page-title"><div><p class="section-label">Pond detail / {{ pond.pond_code }}</p><h1>{{ pond.name }}</h1><p>{{ pond.area_name }} · {{ pond.group_name }} · 最近更新 {{ pond.updated_at }}</p></div><div v-if="canEdit || canRequestStatus || canVerifyStatus" style="display:flex;gap:8px"><button v-if="canEdit" class="ghost-action" type="button" @click="openEditModal">编辑塘口</button><button v-if="canRequestStatus" class="primary-action" data-testid="request-pond-status" type="button" @click="openStatusModal">申请状态变更</button><button v-if="canVerifyStatus" class="primary-action" data-testid="verify-pond-status" type="button" @click="verifyModalOpen = true">核验状态变更</button></div></div>
      <p v-if="pageNotice" class="success-message" role="status">{{ pageNotice }}</p>
      <section v-if="pond.pending_status_change" class="page-card" style="margin-bottom:18px;padding:18px"><strong>待核验状态变更：{{ labels[pond.pending_status_change.from_status] }} → {{ labels[pond.pending_status_change.to_status] }}</strong><p class="section-subtitle">原因：{{ pond.pending_status_change.reason }}</p></section>
      <div class="detail-grid"><section class="page-card detail-card"><div class="detail-status"><div><h1>当前状态</h1><p>养殖状态与录入核验状态分开管理，核验后资料只读。</p></div><StatusBadge :label="labels[pond.status]" :tone="statusTones[pond.status]" /></div><dl class="detail-meta"><div><dt>塘口编码</dt><dd>{{ pond.pond_code }}</dd></div><div><dt>录入状态</dt><dd>{{ formalLabels[pond.lifecycle_status] }} · v{{ pond.version }}</dd></div><div><dt>养殖面积</dt><dd>{{ pond.capacity_mu }} 亩</dd></div><div><dt>养殖品种</dt><dd>{{ pond.species }}</dd></div><div><dt>活跃批次</dt><dd>{{ pond.active_batch_count }} 个</dd></div><div><dt>所属区域</dt><dd>{{ pond.area_name }}</dd></div><div><dt>增氧机数量</dt><dd>{{ pond.aerator_count ?? '—' }} 台</dd></div><div><dt>投苗规格</dt><dd>{{ pond.stocking_spec || '—' }}</dd></div><div><dt>当前规格</dt><dd>{{ pond.current_spec || '—' }}</dd></div></dl><div style="margin-top:28px" class="section-head"><div><p class="section-label">Lifecycle timeline</p><h2 class="section-title">生命周期时间线</h2><p class="section-subtitle">状态变更与资料修改均由服务端审计记录生成</p></div></div><div class="timeline-list"><div v-for="event in pond.timeline_preview" :key="event.id" class="timeline-event"><strong>{{ event.title }}</strong><p>{{ event.description }}</p><small>{{ event.happened_at }} · {{ event.operator_name }}</small></div><div v-if="!pond.timeline_preview.length" class="table-empty">暂无可显示的历史事件</div></div></section><aside class="page-card detail-card"><div class="section-head"><div><p class="section-label">Basic profile</p><h2 class="section-title">基础资料</h2></div><StatusBadge :label="formalLabels[pond.lifecycle_status]" :tone="pond.lifecycle_status === 'verified' ? 'teal' : 'amber'" /></div><dl class="info-list"><div><dt>塘口位置</dt><dd>{{ pond.location }}</dd></div><div><dt>水源</dt><dd>{{ pond.water_source }}</dd></div><div><dt>负责人</dt><dd>{{ pond.manager_name }}</dd></div><div><dt>当前分组</dt><dd>{{ pond.group_name }}</dd></div><div><dt>当前存塘量</dt><dd data-testid="pond-stock-quantity">{{ stockQuantityText }}</dd></div><div><dt>存塘量来源</dt><dd data-testid="pond-stock-source">{{ stockSourceLabel }}</dd></div><div><dt>备注</dt><dd>{{ pond.notes }}</dd></div></dl></aside></div>
    </div>
    <div v-else class="page-card table-empty">塘口不存在或无权访问，<RouterLink class="table-link" to="/ponds">返回塘口列表</RouterLink></div>

    <Teleport to="body">
      <div v-if="statusModalOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="塘口状态变更"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">Status change request</p><h2>申请塘口状态变更</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="statusModalOpen = false">×</button></div><p class="section-subtitle">当前状态：{{ pond ? labels[pond.status] : '—' }} · 仅允许：{{ allowedTargets.map((item) => labels[item]).join(' / ') }}。提交后由另一名核验人员确认才会生效。</p><label class="modal-field"><span>变更后状态 *</span><select v-model="statusForm.next" class="filter-select" style="width:100%"><option value="">请选择状态</option><option v-for="target in allowedTargets" :key="target" :value="target">{{ labels[target] }}</option></select></label><label class="modal-field"><span>变更原因 *</span><textarea v-model="statusForm.note" class="filter-input" style="width:100%;min-height:84px;resize:vertical" /></label><p v-if="statusError" class="modal-error" role="alert">{{ statusError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="statusModalOpen = false">取消</button><button class="primary-action" data-testid="submit-pond-status" type="button" :disabled="statusSubmitting" :aria-busy="statusSubmitting" @click="submitStatus">{{ statusSubmitting ? '提交中…' : '提交核验' }}</button></div></div></div>
      <div v-if="verifyModalOpen && pond?.pending_status_change" class="modal-overlay" role="dialog" aria-modal="true" aria-label="核验塘口状态变更"><div class="modal-panel" style="width:min(500px,100%)"><div class="modal-panel__head"><div><p class="section-label">Verify status change</p><h2>核验塘口状态变更</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="verifyModalOpen = false">×</button></div><p class="section-subtitle">{{ labels[pond.pending_status_change.from_status] }} → {{ labels[pond.pending_status_change.to_status] }}<br>原因：{{ pond.pending_status_change.reason }}</p><p v-if="verifyError" class="modal-error" role="alert">{{ verifyError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="verifyModalOpen = false">取消</button><button class="primary-action" type="button" :disabled="verifySubmitting" :aria-busy="verifySubmitting" @click="submitStatusVerification">{{ verifySubmitting ? '提交中…' : '确认核验并生效' }}</button></div></div></div>
      <div v-if="editModalOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="编辑塘口资料"><div class="modal-panel"><div class="modal-panel__head"><div><p class="section-label">Edit profile</p><h2>编辑塘口资料</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="editModalOpen = false">×</button></div><label class="modal-field"><span>塘口名称 *</span><input v-model="editForm.name" class="filter-input" style="width:100%"></label><div class="modal-row"><label class="modal-field"><span>养殖品种</span><input v-model="editForm.species" class="filter-input" style="width:100%"></label><label class="modal-field"><span>养殖面积（亩）</span><input v-model.number="editForm.capacity_mu" type="number" min="0" step="0.1" class="filter-input" style="width:100%"></label><label class="modal-field"><span>增氧机数量（台）</span><input v-model.number="editForm.aerator_count" type="number" min="0" step="1" data-testid="pond-detail-aerator" class="filter-input" style="width:100%"></label><label class="modal-field"><span>投苗规格</span><input v-model="editForm.stocking_spec" class="filter-input" style="width:100%"></label><label class="modal-field"><span>当前规格</span><input v-model="editForm.current_spec" class="filter-input" style="width:100%"></label><label class="modal-field"><span>当前存塘量（尾）</span><input v-model.number="editForm.stock_quantity" type="number" min="0" data-testid="pond-detail-stock-quantity" class="filter-input" style="width:100%"></label><label class="modal-field"><span>存塘量来源</span><select v-model="editForm.stock_quantity_source" data-testid="pond-detail-stock-source" class="filter-select" style="width:100%"><option value="">未标注</option><option v-for="(label, value) in stockSourceLabels" :key="value" :value="value">{{ label }}</option></select></label></div><label class="modal-field"><span>负责人</span><input v-model="editForm.manager_name" class="filter-input" style="width:100%"></label><label class="modal-field"><span>备注</span><textarea v-model="editForm.notes" class="filter-input" style="width:100%;min-height:70px;resize:vertical" /></label><p v-if="editError" class="modal-error" role="alert">{{ editError }}</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="editModalOpen = false">取消</button><button class="primary-action" type="button" :disabled="editSubmitting" :aria-busy="editSubmitting" @click="submitEdit">{{ editSubmitting ? '保存中…' : '保存修改' }}</button></div></div></div>
    </Teleport>
  </AppShell>
</template>
