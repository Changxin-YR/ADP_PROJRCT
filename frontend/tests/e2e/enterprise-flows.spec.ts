import { expect, test, type Page, type Route } from '@playwright/test'

type RoleCase = { code: string; name: string; permissions: string[]; path: string; heading: string }

const roles: RoleCase[] = [
  { code: 'super_admin', name: '系统管理员', permissions: ['workbench.enter', 'auth.role.manage', 'audit.view'], path: '/admin/roles', heading: '角色权限' },
  { code: 'breed_manager', name: '养殖管理员', permissions: ['workbench.enter', 'production.view', 'production.manage', 'production.verify'], path: '/batches', heading: '养殖批次' },
  { code: 'breed_worker', name: '养殖作业员', permissions: ['workbench.enter', 'production.view', 'production.manage'], path: '/feeding/tasks', heading: '投喂任务' },
  { code: 'warehouse_manager', name: '仓储管理员', permissions: ['workbench.enter', 'warehouse.view', 'warehouse.manage', 'warehouse.verify'], path: '/warehouse/ledger', heading: '仓储台账' },
  { code: 'purchaser', name: '采购人员', permissions: ['workbench.enter', 'purchase.view', 'purchase.manage', 'finance.payable.view'], path: '/purchase/orders', heading: '采购明细' },
  { code: 'finance_staff', name: '财务人员', permissions: ['workbench.enter', 'cost.view', 'cost.entry.manage', 'finance.payable.view'], path: '/cost/expenses', heading: '费用登记' },
  { code: 'sales_staff', name: '销售人员', permissions: ['workbench.enter', 'sales.view', 'sales.manage', 'finance.receivable.view'], path: '/sales/orders', heading: '销售明细' },
]

const ok = (data: unknown) => ({ code: 'OK', message: '操作成功', data, request_id: 'enterprise-e2e' })
const fail = (code: string, message: string) => ({ code, message, data: null, request_id: 'enterprise-e2e' })

function user(role: RoleCase) {
  return { id: roles.findIndex(item => item.code === role.code) + 1, name: role.name, phone: '13900000000', status: 'active', roles: [{ id: 1, code: role.code, name: role.name }], data_scopes: [{ id: 1, code: 'farm-all', name: '全场', scope_type: 'farm', organization_id: 1 }], permissions: role.permissions }
}

async function fulfill(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(status < 400 ? ok(data) : data) })
}

async function mockRole(page: Page, role: RoleCase) {
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/auth/me') return fulfill(route, { user: user(role), next_path: '/workbench', session: { expires_at: '2099-01-01T00:00:00Z' } })
    if (path === '/api/v1/auth/csrf') return fulfill(route, { csrf_token: 'enterprise-csrf' })
    if (path.startsWith('/api/v1/admin/') && role.code !== 'super_admin') return fulfill(route, fail('FORBIDDEN', '权限不足'), 403)
    if (path === '/api/v1/workbench/summary') return fulfill(route, { kpis: {}, alerts: [], recent_batches: [], source_availability: {} })
    if (path === '/api/v1/admin/roles') return fulfill(route, { items: [] })
    return fulfill(route, { items: [], page: 1, page_size: 20, total: 0, has_next: false })
  })
}

for (const role of roles) {
  test(`${role.name}只进入授权业务并由后端拒绝越权`, async ({ page }) => {
    await mockRole(page, role)
    await page.goto(role.path)
    await expect(page.getByRole('heading', { name: role.heading, exact: true })).toBeVisible()

    if (role.code !== 'super_admin') {
      await page.goto('/admin/roles')
      await expect(page).toHaveURL(/\/workbench$/)
      const result = await page.evaluate(async () => {
        const response = await fetch('/api/v1/admin/audit-logs', { credentials: 'include' })
        return { status: response.status, code: (await response.json()).code }
      })
      expect(result).toEqual({ status: 403, code: 'FORBIDDEN' })
    }
  })
}

test('已提交记录可修订，核验后只读且旧版本冲突', async ({ page }) => {
  const role: RoleCase = { code: 'breed_manager', name: '养殖管理员', permissions: ['workbench.enter', 'production.view', 'production.manage', 'production.verify'], path: '/losses', heading: '损耗记录' }
  let record = { id: 21, code: 'LS-021', name: '疾病损耗', batch_id: 4, pond_id: 2, quantity: 12, weight_kg: 1.8, note: '初始记录', status: 'submitted', row_version: 2, version: 2, allowed_actions: ['view', 'edit', 'verify'] }
  await page.route('**/api/v1/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (path === '/api/v1/auth/me') return fulfill(route, { user: user(role), next_path: '/workbench', session: { expires_at: '2099-01-01T00:00:00Z' } })
    if (path === '/api/v1/auth/csrf') return fulfill(route, { csrf_token: 'enterprise-csrf' })
    if (path === '/api/v1/production/losses' && request.method() === 'GET') return fulfill(route, { items: [record], page: 1, page_size: 20, total: 1, has_next: false })
    if (path === '/api/v1/production/losses/21' && request.method() === 'PATCH') {
      const body = request.postDataJSON()
      if (record.status === 'verified') return fulfill(route, fail('RECORD_READ_ONLY', '核验后只读'), 409)
      if (body.expected_version !== record.version) return fulfill(route, fail('VERSION_CONFLICT', '版本冲突'), 409)
      record = { ...record, ...body, row_version: 3, version: 3 }
      return fulfill(route, { record })
    }
    if (path === '/api/v1/production/losses/21/verify') {
      const body = request.postDataJSON()
      if (body.expected_version !== record.version) return fulfill(route, fail('VERSION_CONFLICT', '版本冲突'), 409)
      record = { ...record, status: 'verified', row_version: 4, version: 4, allowed_actions: ['view', 'correct'] }
      return fulfill(route, { record })
    }
    return fulfill(route, { items: [], page: 1, page_size: 20, total: 0, has_next: false })
  })

  await page.goto('/losses')
  const visibleTable = page.locator('.data-table:visible')
  await visibleTable.getByTestId('production-action-edit').click()
  await page.locator('#production-quantity').fill('15')
  await page.getByTestId('production-save').click()
  await expect(visibleTable.getByText('15', { exact: true })).toBeVisible()
  const stale = await page.evaluate(async () => {
    const response = await fetch('/api/v1/production/losses/21', { method: 'PATCH', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'enterprise-csrf' }, body: JSON.stringify({ quantity: 16, expected_version: 2 }) })
    return { status: response.status, code: (await response.json()).code }
  })
  expect(stale).toEqual({ status: 409, code: 'VERSION_CONFLICT' })

  await visibleTable.getByTestId('production-action-verify').click()
  await page.locator('#production-evidence').fill('91')
  await page.getByTestId('production-confirm').click()
  await expect(visibleTable.locator('.status-badge').filter({ hasText: '已核验' })).toBeVisible()
  await expect(page.getByTestId('production-action-edit')).toHaveCount(0)
  await expect(visibleTable.getByTestId('production-action-correct')).toBeVisible()
  const locked = await page.evaluate(async () => {
    const response = await fetch('/api/v1/production/losses/21', { method: 'PATCH', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'enterprise-csrf' }, body: JSON.stringify({ quantity: 17, expected_version: 4 }) })
    return { status: response.status, code: (await response.json()).code }
  })
  expect(locked).toEqual({ status: 409, code: 'RECORD_READ_ONLY' })
})

test('失败导入不出现确认入口且待办完成后保留历史', async ({ page }) => {
  const role: RoleCase = { code: 'super_admin', name: '系统管理员', permissions: ['workbench.enter', 'data_exchange.view', 'data_exchange.import', 'work_item.view'], path: '/data/imports', heading: '批量导入' }
  await page.route('**/api/v1/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (path === '/api/v1/auth/me') return fulfill(route, { user: user(role), next_path: '/workbench', session: { expires_at: '2099-01-01T00:00:00Z' } })
    if (path === '/api/v1/auth/csrf') return fulfill(route, { csrf_token: 'enterprise-csrf' })
    if (path === '/api/v1/data-exchange/templates') return fulfill(route, { items: [{ code: 'materials', name: '物料', group: '主数据', version: 'v1', fields: [], importable: true, updated_at: '2026-08-17' }] })
    if (path === '/api/v1/data-exchange/imports' && request.method() === 'GET') return fulfill(route, { items: [] })
    if (path === '/api/v1/data-exchange/imports/preview') return fulfill(route, { batch: { id: 8, template_code: 'materials', template_name: '物料', template_version: 'v1', file_name: 'invalid.xlsx', total_rows: 2, passed_rows: 1, failed_rows: 1, status: 'invalid', errors: [{ row: 3, column: 'code', message: '编码重复' }], preview_rows: [] } })
    if (path === '/api/v1/work-items') return fulfill(route, { items: [{ id: 1, module_code: 'production', action_code: 'verify', object_type: 'production:losses', object_id: 21, source_key: 'production:losses:21:verify', title: '核验损耗', detail: '已核验完成', priority: 'normal', status: 'completed', row_version: 4, completed_at: '2026-08-17 18:00:00', completion_note: '业务页面核验完成', handling_mode: 'domain' }], page: 1, page_size: 100, total: 1, has_next: false })
    return fulfill(route, { items: [] })
  })

  await page.goto('/data/imports')
  await page.getByTestId('import-open').click()
  await page.getByTestId('import-file').setInputFiles({ name: 'invalid.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('invalid') })
  await page.getByTestId('import-preview').click()
  await expect(page.getByText('第 3 行 · code：编码重复')).toBeVisible()
  await expect(page.getByTestId('import-confirm')).toHaveCount(0)

  await page.goto('/todos')
  await expect(page.getByText('核验损耗')).toBeVisible()
  await expect(page.getByText(/业务页面核验完成/)).toBeVisible()
  await expect(page.getByRole('button', { name: '完成' })).toHaveCount(0)
})
