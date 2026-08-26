import { createApiClient } from '../../common/api/client'
import type { ApplicationSummary, ManagedUser, UserSummary } from '../../common/api/models'

const api = createApiClient()
export interface ReviewList { items: ApplicationSummary[]; page: number; page_size: number; total: number; has_next: boolean }
export interface UserList { items: ManagedUser[]; page: number; page_size: number; total: number; has_next: boolean }
export function getApplications(status = 'pending', page = 1, pageSize = 20): Promise<ReviewList> { return api.get(`/api/v1/admin/applications?status=${encodeURIComponent(status)}&page=${page}&page_size=${pageSize}`) }
export function reviewApplication(id: number, payload: { decision: 'approve' | 'reject'; role_ids?: number[]; data_scopes?: Array<{ type: 'area'; id: number }>; reject_reason?: string }): Promise<{ application: ApplicationSummary }> { return api.patch(`/api/v1/admin/applications/${id}/review`, payload) }
export function approveApplication(id: number, roleIds: number[], scopeIds: number[]): Promise<{ application: ApplicationSummary }> { return api.post(`/api/v1/admin/applications/${id}/approve`, { role_ids: roleIds, data_scopes: scopeIds.map((scopeId) => ({ type: 'area' as const, id: scopeId })) }) }
export function rejectApplication(id: number, reason: string): Promise<{ application: ApplicationSummary }> { return api.post(`/api/v1/admin/applications/${id}/reject`, { reason }) }
export function createManagedUser(payload: Record<string, unknown>): Promise<{ user: UserSummary }> { return api.post('/api/v1/admin/users', payload) }
export function getUsers(status = '', keyword = '', page = 1, pageSize = 20): Promise<UserList> { const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) }); if (status) query.set('status', status); if (keyword) query.set('keyword', keyword); return api.get(`/api/v1/admin/users?${query.toString()}`) }
export function updateUserStatus(id: number, status: 'active' | 'disabled'): Promise<null> { return api.patch(`/api/v1/admin/users/${id}/status`, { status }) }
export function resetUserPassword(id: number, temporary_password: string): Promise<null> { return api.post(`/api/v1/admin/users/${id}/reset-password`, { temporary_password }) }

/** 管理端字典：7 角色 + 基地 + 三级数据范围（farm/area/personal） */
export interface AdminOptions {
  roles: Array<{ id: number; code: string; name: string; description?: string }>
  areas: Array<{ id: number; code: string; name: string }>
  data_scopes: Array<{ id: number; code: string; name: string; scope_type: 'farm' | 'area' | 'personal'; area_id: number | null; area_name?: string | null }>
}
export function getAdminOptions(): Promise<AdminOptions> { return api.get('/api/v1/admin/options') }
export interface RolePermission { code: string; name: string; module_code: string; description?: string }
export interface RoleSummary { id: number; code: string; name: string; description?: string; status: 'active' | 'disabled'; user_count: number; permissions: RolePermission[] }
export interface RoleList { items: RoleSummary[]; available_permissions: RolePermission[]; total: number }
export function getRoles(): Promise<RoleList> { return api.get('/api/v1/admin/roles') }
export function updateRolePermissions(id: number, permissionCodes: string[]): Promise<{ role: RoleSummary }> { return api.put(`/api/v1/admin/roles/${id}/permissions`, { permission_codes: permissionCodes, confirm_phrase: 'CONFIRM' }) }
export function copyRole(id: number, payload: { code: string; name: string; description?: string }): Promise<{ role: RoleSummary }> { return api.post(`/api/v1/admin/roles/${id}/copies`, { ...payload, confirm_phrase: 'CONFIRM' }) }

/** 注销账号：历史申请、权限和业务台账保留，账号状态变为 retired。 */
export function retireUserAccount(id: number, reason: string): Promise<{ user: { id: number; name: string; phone: string; status: 'retired' } }> { return api.post(`/api/v1/admin/users/${id}/retire`, { reason }) }
/** 旧命名兼容导出；实际调用已改为可追溯注销。 */
export const deleteUserAccount = (id: number, reason = '旧版删除接口迁移为账号注销') => retireUserAccount(id, reason)

/** 权限（角色/数据范围）调整：按最终集合同步，支持追加与移除 */
export function updateUserGrants(id: number, roleIds: number[], scopeIds: number[]): Promise<{ grants: { user_id: number; roles: Array<{ id: number; name: string }>; data_scopes: Array<{ id: number; name: string; scope_type: string }> } }> { return api.put(`/api/v1/admin/users/${id}/grants`, { role_ids: roleIds, scope_ids: scopeIds }) }
