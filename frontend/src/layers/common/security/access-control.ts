import type { UserSummary } from '../api/models'

type PermissionHolder = Pick<UserSummary, 'permissions'> | null | undefined

export function hasPermission(user: PermissionHolder, permission: string): boolean {
  return Boolean(user?.permissions.includes(permission))
}

export function hasAnyPermission(user: PermissionHolder, permissions: string[]): boolean {
  return permissions.some((permission) => hasPermission(user, permission))
}
