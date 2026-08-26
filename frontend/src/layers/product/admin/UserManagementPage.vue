<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AuthLayout from '../auth/AuthLayout.vue'
import BackButton from '../../common/ui/BackButton.vue'
import FormField from '../../common/ui/FormField.vue'
import MultiCheckGrid from '../../common/ui/MultiCheckGrid.vue'
import { createManagedUser, getAdminOptions, getUsers, resetUserPassword, retireUserAccount, updateUserGrants, updateUserStatus, type AdminOptions } from '../../features/account-review/public'
import type { ManagedUser } from '../../common/api/models'
import { ApiError } from '../../common/api/errors'

const SCOPE_TYPE_LABEL: Record<string, string> = { farm: '全场', area: '区域', personal: '个人' }

const form = reactive({ phone: '', name: '', login_name: '', temporary_password: '', role_ids: [] as number[], data_scope_ids: [] as number[] })
const options = ref<AdminOptions>({ roles: [], areas: [], data_scopes: [] })
const users = ref<ManagedUser[]>([])
const error = ref(''); const success = ref(''); const submitting = ref(false); const loading = ref(false); const busyUserId = ref<number | null>(null)
const statusFilter = ref(''); const keyword = ref('')

async function loadOptions() {
  try { options.value = await getAdminOptions() } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '角色和数据范围加载失败' }
}
async function loadUsers() {
  loading.value = true
  try { users.value = (await getUsers(statusFilter.value, keyword.value)).items } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '用户列表加载失败' } finally { loading.value = false }
}
onMounted(() => { void loadOptions(); void loadUsers() })

async function submit() {
  error.value = ''; success.value = ''; submitting.value = true
  try {
    if (!options.value.roles.length || !options.value.data_scopes.length) { error.value = '企业角色或数据范围尚未加载，不能创建账号'; return }
    if (!form.role_ids.length || !form.data_scope_ids.length) { error.value = '至少选择一个角色和一个数据范围'; return }
    await createManagedUser({ phone: form.phone, name: form.name, login_name: form.login_name, temporary_password: form.temporary_password, role_ids: form.role_ids, data_scopes: form.data_scope_ids.map((id) => ({ type: options.value.data_scopes.find((scope) => scope.id === id)?.scope_type ?? 'area', id })) })
    success.value = '账号已创建，用户首次登录必须修改密码。'; Object.assign(form, { phone: '', name: '', login_name: '', temporary_password: '' }); await loadUsers()
  } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '账号创建失败' } finally { submitting.value = false }
}
async function toggleStatus(user: ManagedUser) {
  busyUserId.value = user.id; error.value = ''; success.value = ''
  try { await updateUserStatus(user.id, user.status === 'disabled' ? 'active' : 'disabled'); success.value = '账号状态已更新'; await loadUsers() } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '账号状态更新失败' } finally { busyUserId.value = null }
}
async function resetPassword(user: ManagedUser) {
  const temporary = window.prompt(`请输入 ${user.name} 的临时密码（至少 8 位，含字母和数字）`)
  if (!temporary) return
  busyUserId.value = user.id; error.value = ''; success.value = ''
  try { await resetUserPassword(user.id, temporary); success.value = '密码已重置，用户下次登录必须修改。'; await loadUsers() } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '密码重置失败' } finally { busyUserId.value = null }
}

// ===== 编辑权限（角色/数据范围）：移除权限需两轮确认 =====
const grantsOpen = ref(false)
const grantsStage = ref<1 | 2>(1)
const grantsTarget = ref<ManagedUser>()
const grantsDraft = reactive({ role_ids: [] as number[], scope_ids: [] as number[] })
const grantsSaving = ref(false)

function scopeLabel(scope: { name: string; scope_type?: string; area_name?: string | null }): string {
  const type = scope.scope_type ? `[${SCOPE_TYPE_LABEL[scope.scope_type] ?? scope.scope_type}] ` : ''
  return `${type}${scope.name}`
}

const roleChoices = computed(() => options.value.roles.map((role) => ({ id: role.id, label: role.name })))
const scopeChoices = computed(() => options.value.data_scopes.map((scope) => ({ id: scope.id, label: scope.name, hint: `${SCOPE_TYPE_LABEL[scope.scope_type] ?? scope.scope_type}数据` })))

function openGrants(user: ManagedUser) {
  grantsTarget.value = user
  grantsDraft.role_ids = user.roles.map((role) => role.id)
  grantsDraft.scope_ids = user.data_scopes.map((scope) => scope.id)
  grantsStage.value = 1
  grantsOpen.value = true
}

const grantsRemovalCount = computed(() => {
  const target = grantsTarget.value
  if (!target) return 0
  const removedRoles = target.roles.filter((role) => !grantsDraft.role_ids.includes(role.id)).length
  const removedScopes = target.data_scopes.filter((scope) => !grantsDraft.scope_ids.includes(scope.id)).length
  return removedRoles + removedScopes
})

async function confirmGrants() {
  const target = grantsTarget.value
  if (!target) { grantsOpen.value = false; return }
  if (!grantsDraft.role_ids.length || !grantsDraft.scope_ids.length) { error.value = '至少保留一个角色和一个数据范围'; return }
  if (grantsRemovalCount.value > 0 && grantsStage.value === 1) { grantsStage.value = 2; return }
  grantsSaving.value = true; error.value = ''; success.value = ''
  try {
    await updateUserGrants(target.id, grantsDraft.role_ids, grantsDraft.scope_ids)
    grantsOpen.value = false
    success.value = `权限已更新：「${target.name}」的角色/数据范围已按最终集合同步${grantsRemovalCount.value > 0 ? `（移除 ${grantsRemovalCount.value} 项，两轮确认通过）` : ''}`
    await loadUsers()
  } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '权限更新失败' } finally { grantsSaving.value = false }
}

// ===== 删除账号：两轮确认 =====
const deleteOpen = ref(false)
const deleteStage = ref<1 | 2>(1)
const deleteTarget = ref<ManagedUser>()

function askDelete(user: ManagedUser) { deleteTarget.value = user; retireReason.value = ''; deleteStage.value = 1; deleteOpen.value = true }

const retireReason = ref('')

async function confirmRetireUser() {
  const target = deleteTarget.value
  if (!target) { deleteOpen.value = false; return }
  if (deleteStage.value === 1) { deleteStage.value = 2; return }
  if (!retireReason.value.trim()) { error.value = '注销账号必须填写原因'; return }
  busyUserId.value = target.id; error.value = ''; success.value = ''
  try {
    await retireUserAccount(target.id, retireReason.value.trim())
    deleteOpen.value = false
    success.value = `账号已注销：「${target.name}」（${target.phone}），历史记录已保留`
    await loadUsers()
  } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '账号注销失败' } finally { busyUserId.value = null }
}

function labels(values: Array<{ name: string }>): string { return values.map((item) => item.name).join('、') || '未分配' }
function statusLabel(status: string): string { return ({ active: '正常', disabled: '已停用', must_change_password: '待首次改密', pending: '审核中', rejected: '已驳回', retired: '已注销' } as Record<string, string>)[status] || status }
</script>

<template>
  <AuthLayout wide>
    <div class="admin-heading"><div><p class="status-kicker">系统管理</p><h2>账号管理</h2><p class="status-description">创建后的账号进入首次改密状态；注销只改变生命周期状态，申请、授权和业务台账始终保留。</p></div><BackButton /></div>
    <p v-if="error" class="field-error" role="alert">{{ error }}</p><p v-if="success" class="success-message" role="status">{{ success }}</p>
    <form class="management-form" @submit.prevent="submit">
      <FormField id="managed-name" label="姓名"><input id="managed-name" v-model="form.name" autocomplete="name" /></FormField>
      <FormField id="managed-phone" label="手机号"><input id="managed-phone" v-model="form.phone" inputmode="tel" autocomplete="tel" /></FormField>
      <FormField id="managed-login" label="系统账号" hint="选填，内部账号可用手机号或系统账号登录"><input id="managed-login" v-model="form.login_name" autocomplete="username" /></FormField>
      <FormField id="temporary-password" label="初始密码" hint="只在创建表单中暂存，提交后立即清空"><input id="temporary-password" v-model="form.temporary_password" type="password" autocomplete="new-password" /></FormField>
      <FormField id="managed-role" label="角色（可多选，7 类岗位，选中项高亮）"><MultiCheckGrid v-model="form.role_ids" name="角色" :options="roleChoices" /></FormField>
      <FormField id="managed-scope" label="数据范围（可多选，全场/区域/个人）"><MultiCheckGrid v-model="form.data_scope_ids" name="数据范围" :options="scopeChoices" /></FormField>
      <button class="primary-button" type="submit" :disabled="submitting">{{ submitting ? '创建中…' : '创建账号' }}</button>
    </form>
    <section class="user-management-list" aria-labelledby="user-list-title">
      <div class="list-heading"><h3 id="user-list-title">现有账号</h3><div><input v-model="keyword" aria-label="搜索姓名、手机号或账号" placeholder="搜索姓名/手机号/账号" @keyup.enter="loadUsers" /><select v-model="statusFilter" aria-label="按状态筛选" @change="loadUsers"><option value="">全部状态</option><option value="active">正常</option><option value="disabled">已停用</option><option value="must_change_password">待首次改密</option><option value="retired">已注销</option></select><button type="button" class="secondary-action compact-action" @click="loadUsers">查询</button></div></div>
      <p v-if="loading" class="page-notice">账号加载中…</p>
      <div v-for="user in users" :key="user.id" class="user-row">
        <div class="user-identity"><strong>{{ user.name }}</strong><span>{{ user.phone }}<template v-if="user.login_name"> · {{ user.login_name }}</template></span></div>
        <div class="user-meta"><span>{{ statusLabel(user.status) }}</span><small>角色：{{ labels(user.roles) }} · 范围：{{ labels(user.data_scopes) }}</small></div>
        <div class="user-actions">
          <template v-if="user.status !== 'retired'">
            <button type="button" class="secondary-action compact-action" :disabled="busyUserId === user.id" @click="openGrants(user)">编辑权限</button>
            <button type="button" class="secondary-action compact-action" :disabled="busyUserId === user.id" @click="toggleStatus(user)">{{ user.status === 'disabled' ? '启用' : '停用' }}</button>
            <button type="button" class="secondary-action compact-action" :disabled="busyUserId === user.id || !['active', 'must_change_password'].includes(user.status)" @click="resetPassword(user)">重置密码</button>
            <button type="button" class="secondary-action compact-action" style="color:#c25450" :disabled="busyUserId === user.id" @click="askDelete(user)">注销</button>
          </template>
          <span v-else class="muted-action">历史只读</span>
        </div>
      </div>
      <p v-if="!users.length && !loading" class="empty-state">暂无账号</p>
    </section>

    <Teleport to="body">
      <!-- 编辑权限弹窗：涉及移除权限时进入两轮确认 -->
      <div v-if="grantsOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="编辑权限" @click.self="grantsOpen = false" @keydown.esc="grantsOpen = false">
        <div class="modal-panel" style="width:min(560px,100%)">
          <div class="modal-panel__head"><div><p class="section-label">Grants · {{ grantsRemovalCount > 0 ? `第 ${grantsStage} / 2 轮确认` : '编辑' }}</p><h2>编辑权限：{{ grantsTarget?.name }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="grantsOpen = false">✕</button></div>
          <template v-if="grantsStage === 1">
            <div style="display:grid;gap:12px;margin:16px 0">
              <div>
                <label class="field-label">角色（再次点击卡片即取消，取消将移除该权限）</label>
                <MultiCheckGrid v-model="grantsDraft.role_ids" name="编辑权限 · 角色" :options="roleChoices" />
              </div>
              <div>
                <label class="field-label">数据范围（全场/区域/个人）</label>
                <MultiCheckGrid v-model="grantsDraft.scope_ids" name="编辑权限 · 数据范围" :options="scopeChoices" />
              </div>
            </div>
            <div class="modal-panel__foot"><button class="ghost-action" type="button" @click="grantsOpen = false">取消</button><button class="primary-action" type="button" :disabled="grantsSaving" @click="confirmGrants">{{ grantsRemovalCount > 0 ? `下一步（将移除 ${grantsRemovalCount} 项权限）` : '保存权限' }}</button></div>
          </template>
          <template v-else>
            <p class="modal-error" style="line-height:1.8">⚠ 第二轮确认：即将移除「{{ grantsTarget?.name }}」的 {{ grantsRemovalCount }} 项权限（角色/数据范围），移除后该账号将无法访问对应功能与数据。确认继续吗？</p>
            <div class="modal-panel__foot"><button class="ghost-action" type="button" @click="grantsStage = 1">返回修改</button><button class="primary-action" type="button" style="background:#c25450" :disabled="grantsSaving" @click="confirmGrants">确认移除并保存</button></div>
          </template>
        </div>
      </div>

      <!-- 注销账号两轮确认：保留历史引用，只撤销登录能力 -->
      <div v-if="deleteOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="注销账号确认" @click.self="deleteOpen = false" @keydown.esc="deleteOpen = false">
        <div class="modal-panel" style="width:min(520px,100%)">
          <div class="modal-panel__head"><div><p class="section-label">Retire user · 第 {{ deleteStage }} / 2 轮确认</p><h2>{{ deleteStage === 1 ? '注销账号确认' : '最终确认' }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="deleteOpen = false">✕</button></div>
          <template v-if="deleteStage === 1">
            <p class="section-subtitle" style="line-height:1.8">即将注销账号：「{{ deleteTarget?.name }}」（{{ deleteTarget?.phone }}）。<br>系统会撤销登录会话并禁止再次登录；注册申请、角色、数据范围和业务台账将保留，供审计追溯。</p>
            <div class="modal-panel__foot"><button class="ghost-action" type="button" @click="deleteOpen = false">取消</button><button class="primary-action" type="button" @click="confirmRetireUser">下一步，继续确认</button></div>
          </template>
          <template v-else>
            <p class="modal-error" style="line-height:1.8">⚠ 第二轮确认：注销后账号不能恢复或修改权限，但历史记录仍可查看。请填写注销原因并确认。</p>
            <label class="field-label" for="retire-reason">注销原因</label><textarea id="retire-reason" v-model="retireReason" rows="3" maxlength="500" placeholder="例如：员工离职、岗位调整"></textarea>
            <div class="modal-panel__foot"><button class="ghost-action" type="button" @click="deleteOpen = false">再想想，不注销</button><button class="primary-action" type="button" style="background:#c25450" :disabled="busyUserId !== null" @click="confirmRetireUser">确认注销</button></div>
          </template>
        </div>
      </div>
    </Teleport>
  </AuthLayout>
</template>
