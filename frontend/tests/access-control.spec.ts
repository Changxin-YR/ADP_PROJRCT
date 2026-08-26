import { describe, expect, it } from 'vitest'

import { hasAnyPermission, hasPermission } from '../src/layers/common/security/access-control'
import { router } from '../src/router'

const user = {
  id: 9,
  name: '财务人员',
  phone: '13800000009',
  status: 'active' as const,
  roles: [{ id: 6, code: 'finance_staff', name: '财务人员' }],
  data_scopes: [],
  permissions: ['cost.view'],
}

describe('permission access control', () => {
  it('uses permission codes instead of role-name guesses', () => {
    expect(hasPermission(user, 'cost.view')).toBe(true)
    expect(hasPermission(user, 'cost.allocation.manage')).toBe(false)
    expect(hasAnyPermission(user, ['auth.review', 'cost.view'])).toBe(true)
  })

  it('declares exact permissions on cost and administration routes', () => {
    expect(router.getRoutes().find((route) => route.path === '/cost/structure')?.meta.requiredPermission).toBe('cost.view')
    expect(router.getRoutes().find((route) => route.path === '/admin/applications')?.meta.requiredPermission).toBe('auth.review')
    expect(router.getRoutes().find((route) => route.path === '/admin/users')?.meta.requiredPermission).toBe('auth.user.manage')
    expect(router.getRoutes().find((route) => route.path === '/admin/logs')?.meta.requiredPermission).toBe('audit.view')
    expect(router.getRoutes().find((route) => route.path === '/ponds')?.meta.requiredPermission).toBe('master_data.view')
    expect(router.getRoutes().find((route) => route.path === '/warehouse/in')?.meta.requiredPermission).toBe('warehouse.view')
    expect(router.getRoutes().find((route) => route.path === '/purchase/payables')?.meta.requiredPermission).toBe('finance.payable.view')
    expect(router.getRoutes().find((route) => route.path === '/sales/receivables')?.meta.requiredPermission).toBe('finance.receivable.view')
    expect(router.getRoutes().find((route) => route.path === '/admin/roles')?.meta.requiredPermission).toBe('auth.role.manage')
  })
})
