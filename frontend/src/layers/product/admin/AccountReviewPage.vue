<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AuthLayout from '../auth/AuthLayout.vue'
import BackButton from '../../common/ui/BackButton.vue'
import MultiCheckGrid, { type CheckOption } from '../../common/ui/MultiCheckGrid.vue'
import { approveApplication, getAdminOptions, getApplications, rejectApplication, type AdminOptions, type ReviewList } from '../../features/account-review/review.service'
import type { ApplicationSummary } from '../../common/api/models'
import { ApiError } from '../../common/api/errors'

const SCOPE_TYPE_LABEL: Record<string, string> = { farm: '全场', area: '区域', personal: '个人' }

const applications = ref<ApplicationSummary[]>([])
const selected = ref<ApplicationSummary | null>(null)
const rejectionReason = ref('')
const error = ref('')
const busy = ref(false)
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const options = ref<AdminOptions>({ roles: [], areas: [], data_scopes: [] })
const optionsError = ref('')
const roleIds = ref<number[]>([])
const scopeIds = ref<number[]>([])
const requestSequence = ref(0)
const success = ref('')

const roleChoices = computed<CheckOption[]>(() => options.value.roles.map((role) => ({ id: role.id, label: role.name })))
const scopeChoices = computed<CheckOption[]>(() => options.value.data_scopes.map((scope) => ({ id: scope.id, label: scope.name, hint: `${SCOPE_TYPE_LABEL[scope.scope_type] ?? scope.scope_type}数据` })))

async function loadOptions() {
  try { options.value = await getAdminOptions() } catch (reason) { optionsError.value = reason instanceof ApiError ? reason.message : '角色和数据范围加载失败' }
}

/** 按申请的岗位与数据范围类型，预填最终角色与范围 */
function prefill(application: ApplicationSummary | null) {
  if (!application) { roleIds.value = []; scopeIds.value = []; return }
  roleIds.value = [application.desired_role_id]
  const scopeType = application.desired_scope_type ?? 'area'
  const matched = options.value.data_scopes.find((scope) =>
    scopeType === 'area' ? scope.scope_type === 'area' && scope.area_id === application.area_id : scope.scope_type === scopeType)
  scopeIds.value = matched ? [matched.id] : []
}
watch(selected, prefill)

async function load(attempt = 0) {
  const sequence = ++requestSequence.value
  loading.value = true
  error.value = ''
  try {
    const result = await getApplications('pending', page.value, pageSize)
    if (sequence !== requestSequence.value) return
    const items = result.items ?? (result as ReviewList & { applications?: ApplicationSummary[] }).applications ?? []
    applications.value = items
    total.value = result.total ?? items.length
    selected.value = items.find((item) => item.id === selected.value?.id) ?? items[0] ?? null
  } catch (reason) {
    const transient = reason instanceof TypeError || (reason instanceof ApiError && reason.status >= 500)
    if (transient && attempt === 0) {
      await new Promise((resolve) => window.setTimeout(resolve, 120))
      return load(1)
    }
    if (sequence === requestSequence.value) error.value = reason instanceof ApiError ? reason.message : '申请列表加载失败，请点击重试'
  } finally {
    if (sequence === requestSequence.value) loading.value = false
  }
}
async function refreshList() { await load() }
onMounted(() => { void loadOptions(); void load() })
async function approve() {
  if (!selected.value) return
  if (optionsError.value || !options.value.roles.length) { error.value = optionsError.value || '授权配置尚未加载'; return }
  if (!roleIds.value.length || !scopeIds.value.length) { error.value = '通过审核前至少选择一个角色和一个数据范围'; return }
  busy.value = true; error.value = ''; success.value = ''
  try {
    await approveApplication(selected.value.id, roleIds.value, scopeIds.value)
    success.value = '申请已通过，账号权限已经生效（按申请的数据范围自动附加对应授权）。'
    await load()
  } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '审核操作失败' } finally { busy.value = false }
}
async function reject() { if (!selected.value || !rejectionReason.value.trim()) { error.value = '驳回时必须填写原因'; return }; busy.value = true; error.value = ''; success.value = ''; try { await rejectApplication(selected.value.id, rejectionReason.value); rejectionReason.value = ''; success.value = '申请已驳回，已记录审核原因。'; await load() } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '驳回操作失败' } finally { busy.value = false } }
function display(value: string | number | null | undefined): string { return value === null || value === undefined || value === '' ? '—' : String(value) }
function scopeTypeLabel(type: string | null | undefined): string { return type ? `${SCOPE_TYPE_LABEL[type] ?? type}数据` : '区域数据' }
</script>

<template>
  <AuthLayout wide>
    <div class="admin-heading">
      <div>
        <p class="status-kicker">系统管理 / 账号准入</p>
        <h2>申请审核</h2>
        <p class="status-description">确认岗位与数据范围后，申请人才能进入正式工作区。</p>
      </div>
      <div class="admin-heading-actions"><BackButton /><button class="secondary-action compact-action" type="button" aria-label="刷新申请列表" :disabled="loading" @click="refreshList">{{ loading ? '刷新中…' : '刷新列表' }}</button></div>
    </div>

    <div class="review-stats">
      <div class="review-stat review-stat--amber"><strong>{{ total }}</strong><span>待审核申请</span></div>
      <div class="review-stat"><strong>{{ applications.length }}</strong><span>本页显示</span></div>
      <div class="review-stat"><strong>{{ selected ? scopeTypeLabel(selected.desired_scope_type) : '—' }}</strong><span>当前申请数据范围</span></div>
    </div>

    <p v-if="error" class="field-error" role="alert">{{ error }}</p>
    <p v-if="optionsError" class="field-error" role="alert">{{ optionsError }}</p>
    <p v-if="success" class="success-message" role="status">{{ success }}</p>
    <button v-if="error" class="secondary-action retry-action" type="button" aria-label="重试加载" :disabled="loading" @click="refreshList">重试加载</button>
    <p v-if="loading" class="page-notice" role="status">申请列表加载中…</p>

    <div class="review-layout">
      <aside class="review-list" aria-label="待审核申请">
        <p class="review-list__title">待审核申请 <small>按提交时间排序</small></p>
        <button v-for="item in applications" :key="item.id" type="button" class="applicant-card" :class="{ 'applicant-card--selected': selected?.id === item.id }" @click="selected = item">
          <span class="applicant-card__avatar" aria-hidden="true">{{ item.name.slice(0, 1) }}</span>
          <span class="applicant-card__body">
            <strong>{{ item.name }}</strong>
            <span>{{ display(item.desired_role_name) }}</span>
            <small>{{ display(item.area_name) }} · 第 {{ item.version_no }} 版</small>
          </span>
        </button>
        <p v-if="!applications.length && !loading" class="empty-state">暂无待审核申请</p>
        <div v-if="total > pageSize" class="pagination"><button type="button" :disabled="page <= 1 || loading" @click="page--; load()">上一页</button><span>第 {{ page }} 页 · 共 {{ total }} 条</span><button type="button" :disabled="applications.length < pageSize || loading" @click="page++; load()">下一页</button></div>
      </aside>

      <section v-if="selected" class="review-detail">
        <header class="review-detail__head">
          <span class="applicant-card__avatar applicant-card__avatar--lg" aria-hidden="true">{{ selected.name.slice(0, 1) }}</span>
          <div>
            <h3>{{ selected.name }}</h3>
            <p>{{ display(selected.desired_role_name) }} · {{ scopeTypeLabel(selected.desired_scope_type) }} · {{ display(selected.area_name) }}</p>
          </div>
          <span class="review-detail__badge">待审核</span>
        </header>

        <div class="review-section">
          <p class="review-section__title">申请人信息</p>
          <dl class="status-details">
            <div><dt>姓名</dt><dd>{{ selected.name }}</dd></div><div><dt>手机号</dt><dd>{{ display(selected.phone) }}</dd></div>
            <div><dt>申请岗位</dt><dd>{{ display(selected.desired_role_name) }}</dd></div><div><dt>申请数据范围</dt><dd>{{ scopeTypeLabel(selected.desired_scope_type) }}</dd></div>
            <div><dt>所属区域</dt><dd>{{ display(selected.area_name) }}</dd></div>
            <div><dt>提交时间</dt><dd>{{ display(selected.submitted_at || selected.created_at) }}</dd></div>
            <div><dt>申请说明</dt><dd>{{ selected.application_note || '未填写' }}</dd></div>
          </dl>
        </div>

        <div class="review-section">
          <p class="review-section__title">授权配置 <small>点击卡片选中/取消，选中项高亮显示</small></p>
          <div class="review-section__row">
            <div>
              <label class="field-label">最终角色（可多选）<em>已选 {{ roleIds.length }} 项</em></label>
              <MultiCheckGrid v-model="roleIds" name="最终角色" :options="roleChoices" />
            </div>
            <div>
              <label class="field-label">数据范围（可多选）<em>已选 {{ scopeIds.length }} 项</em></label>
              <MultiCheckGrid v-model="scopeIds" name="数据范围" :options="scopeChoices" />
            </div>
          </div>
        </div>

        <div class="review-section review-section--actions">
          <p class="review-section__title">审核操作</p>
          <button class="primary-button" type="button" :disabled="busy" @click="approve">{{ busy ? '处理中…' : '✓ 通过审核' }}</button>
          <div class="reject-card">
            <label class="field-label" for="rejection-reason">驳回原因（必填）</label>
            <textarea id="rejection-reason" v-model="rejectionReason" maxlength="500" placeholder="请填写具体原因，申请人可在驳回页看到" />
            <button class="secondary-action reject-card__btn" type="button" :disabled="busy" @click="reject">驳回申请</button>
          </div>
        </div>
      </section>
      <section v-else class="review-detail review-detail--empty">
        <p class="empty-state">请在左侧选择一条申请开始审核</p>
      </section>
    </div>
  </AuthLayout>
</template>
