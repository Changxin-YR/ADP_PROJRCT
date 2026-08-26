<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import AppShell from '../../common/ui/AppShell.vue'
import DataTablePage from '../../common/ui/DataTablePage.vue'
import MultiCheckGrid from '../../common/ui/MultiCheckGrid.vue'
import { ApiError } from '../../common/api/errors'
import { copyRole, getRoles, updateRolePermissions, type RolePermission, type RoleSummary } from '../../features/account-review/review.service'

type RoleRow = RoleSummary & { users: number; summary: string; data_scope: string; status_label: string }
const rows = ref<RoleRow[]>([])
const available = ref<RolePermission[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const success = ref('')
const statusTones = { 启用: 'teal', 停用: 'slate' } as const
const memberCount = computed(() => rows.value.reduce((sum, role) => sum + role.users, 0))
const permissionChoices = computed(() => available.value.map((permission, index) => ({ id: index + 1, label: permission.name, hint: `${permission.module_code} · ${permission.code}` })))
const permissionCode = (id: number) => available.value[id - 1]?.code

async function load() {
  try {
    const result = await getRoles()
    available.value = result.available_permissions
    rows.value = result.items.map((role) => ({
      ...role,
      users: Number(role.user_count),
      summary: role.permissions.map((permission) => permission.name || permission.code).join(' / ') || '未配置功能权限',
      data_scope: '按成员数据范围授权',
      status_label: role.status === 'active' ? '启用' : '停用',
    }))
  } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '角色权限加载失败，请稍后重试' }
  finally { loading.value = false }
}
onMounted(load)

const editOpen = ref(false)
const editStage = ref<1 | 2>(1)
const editTarget = ref<RoleRow>()
const selectedPermissionIds = ref<number[]>([])
const originalCodes = ref<string[]>([])
const selectedCodes = computed(() => selectedPermissionIds.value.map(permissionCode).filter((code): code is string => Boolean(code)))
const changedCount = computed(() => new Set([...originalCodes.value.filter((code) => !selectedCodes.value.includes(code)), ...selectedCodes.value.filter((code) => !originalCodes.value.includes(code))]).size)

function openPermissions(role: RoleRow) {
  editTarget.value = role
  originalCodes.value = role.permissions.map((permission) => permission.code)
  selectedPermissionIds.value = available.value.map((permission, index) => originalCodes.value.includes(permission.code) ? index + 1 : 0).filter(Boolean)
  editStage.value = 1
  editOpen.value = true
}
async function confirmPermissions() {
  const role = editTarget.value
  if (!role) return
  if (!selectedCodes.value.length) { error.value = '角色至少保留一项功能权限'; return }
  if (editStage.value === 1) { editStage.value = 2; return }
  saving.value = true; error.value = ''; success.value = ''
  try {
    await updateRolePermissions(role.id, selectedCodes.value)
    editOpen.value = false; success.value = `角色「${role.name}」权限已更新，变更 ${changedCount.value} 项并写入审计。`; await load()
  } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '角色权限更新失败' }
  finally { saving.value = false }
}

const copyOpen = ref(false)
const copyStage = ref<1 | 2>(1)
const copyTarget = ref<RoleRow>()
const copyForm = reactive({ code: '', name: '', description: '' })
function openCopy(role: RoleRow) { copyTarget.value = role; Object.assign(copyForm, { code: '', name: `${role.name}副本`, description: role.description || '' }); copyStage.value = 1; copyOpen.value = true }
async function confirmCopy() {
  if (!copyTarget.value) return
  if (!copyForm.code.trim() || !copyForm.name.trim()) { error.value = '角色编码和名称不能为空'; return }
  if (copyStage.value === 1) { copyStage.value = 2; return }
  saving.value = true; error.value = ''; success.value = ''
  try {
    await copyRole(copyTarget.value.id, { code: copyForm.code.trim(), name: copyForm.name.trim(), description: copyForm.description.trim() || undefined })
    copyOpen.value = false; success.value = `已复制角色「${copyTarget.value.name}」，权限集合保持一致。`; await load()
  } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '角色复制失败' }
  finally { saving.value = false }
}
function runAction(action: string, row: Record<string, unknown>) {
  if (action === '编辑权限') openPermissions(row as unknown as RoleRow)
  if (action === '复制角色') openCopy(row as unknown as RoleRow)
}
</script>

<template>
  <AppShell v-if="loading || (error && !rows.length)" title="角色权限">
    <div class="page-title"><div><p class="section-label">System / Roles</p><h1>角色权限</h1><p>功能权限与数据范围分别授权，关键权限变更永久留痕。</p></div></div>
    <div v-if="loading" class="page-card table-empty" role="status">正在加载角色权限…</div>
    <div v-else class="page-card table-empty" role="alert">{{ error }}</div>
  </AppShell>
  <DataTablePage v-else
    title="角色权限" label="System / Roles" description="角色决定功能权限；数据范围按成员授权，所有接口仍会再次校验。"
    :kpis="[
      { label: '角色总数', value: rows.length, unit: '个', hint: `${memberCount} 名成员在岗` },
      { label: '数据范围层级', value: '3', unit: '级', hint: '全场 / 区域 / 个人' },
      { label: '权限来源', value: '数据库', tone: 'blue', hint: '角色与权限关系实时读取' },
    ]"
    :filters="[
      { key: 'status_label', type: 'select', label: '全部状态', options: Object.keys(statusTones).map((status) => ({ value: status, label: status })) },
      { key: 'name', type: 'search', placeholder: '搜索角色名称 / 编码 / 权限' },
    ]"
    :columns="[
      { key: 'name', label: '角色名称', type: 'title', sub: 'code' }, { key: 'users', label: '成员数', type: 'number' },
      { key: 'summary', label: '功能权限' }, { key: 'data_scope', label: '数据范围' },
      { key: 'status_label', label: '状态', type: 'badge', tones: statusTones },
    ]"
    :rows="rows" :actions="['编辑权限', '复制角色']" :exportable="false" empty-text="数据库中没有可用角色" @action="runAction"
  >
    <template #tabs><p v-if="error" class="field-error" role="alert">{{ error }}</p><p v-if="success" class="success-message" role="status">{{ success }}</p></template>
  </DataTablePage>
  <Teleport to="body">
    <div v-if="editOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="编辑角色权限" @click.self="editOpen = false" @keydown.esc="editOpen = false">
      <div class="modal-panel" style="width:min(720px,100%)">
        <div class="modal-panel__head"><div><p class="section-label">Role grants · 第 {{ editStage }} / 2 轮确认</p><h2>编辑权限：{{ editTarget?.name }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="editOpen = false">×</button></div>
        <template v-if="editStage === 1"><MultiCheckGrid v-model="selectedPermissionIds" name="角色功能权限" :options="permissionChoices" /><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="editOpen = false">取消</button><button class="primary-action" data-testid="role-permissions-next" type="button" @click="confirmPermissions">下一步，核对权限差异</button></div></template>
        <template v-else><p class="section-subtitle">将对「{{ editTarget?.name }}」变更 {{ changedCount }} 项权限。保存后立即影响该角色下全部账号，并永久记录变更前后差异。</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="editStage = 1">返回修改</button><button class="primary-action" data-testid="role-permissions-confirm" type="button" :disabled="saving" @click="confirmPermissions">确认并保存</button></div></template>
      </div>
    </div>
    <div v-if="copyOpen" class="modal-overlay" role="dialog" aria-modal="true" aria-label="复制角色" @click.self="copyOpen = false" @keydown.esc="copyOpen = false">
      <div class="modal-panel" style="width:min(540px,100%)"><div class="modal-panel__head"><div><p class="section-label">Copy role · 第 {{ copyStage }} / 2 轮确认</p><h2>复制：{{ copyTarget?.name }}</h2></div><button class="modal-close" type="button" aria-label="关闭" @click="copyOpen = false">×</button></div>
        <template v-if="copyStage === 1"><div class="management-form"><label class="field-label">角色编码<input v-model="copyForm.code" maxlength="64" placeholder="例如 breed_reviewer"></label><label class="field-label">角色名称<input v-model="copyForm.name" maxlength="100"></label><label class="field-label">角色说明<textarea v-model="copyForm.description" rows="3" maxlength="255"></textarea></label></div><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="copyOpen = false">取消</button><button class="primary-action" type="button" @click="confirmCopy">下一步，核对复制</button></div></template>
        <template v-else><p class="section-subtitle">新角色将完整继承「{{ copyTarget?.name }}」的当前权限，但不会自动分配给任何账号。</p><div class="modal-panel__foot"><button class="ghost-action" type="button" @click="copyStage = 1">返回修改</button><button class="primary-action" type="button" :disabled="saving" @click="confirmCopy">确认创建角色</button></div></template>
      </div>
    </div>
  </Teleport>
</template>
