import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import CostPage from '../src/layers/product/cost/CostPage.vue'
import { createSessionStore } from '../src/layers/common/session/session.store'


const categories = [
  ['pond_rent', '塘租', 'public', '120000.00', '17.8571', 'area'],
  ['equipment', '设备', 'public', '38000.00', '5.6548', 'equipment_count'],
  ['infrastructure', '基础建设', 'public', '46000.00', '6.8452', 'area'],
  ['labor', '人工', 'public', '144000.00', '21.4286', 'work_scope'],
  ['electricity', '电费', 'public', '42000.00', '6.2500', 'runtime_hours'],
  ['seed', '苗种', 'direct', '96000.00', '14.2857', 'direct_input'],
  ['feed', '饲料', 'direct', '128000.00', '19.0476', 'direct_consumption'],
  ['health', '动保', 'direct', '26000.00', '3.8690', 'direct_consumption'],
  ['other', '其他费用', 'public', '32000.00', '4.7619', 'equal'],
].map(([code, name, nature, amount, share, allocation_driver], index) => ({
  id: index + 1,
  code,
  name,
  nature,
  amount,
  share,
  allocation_driver,
}))

const structure = {
  period_start: '2026-01-01',
  period_end: '2026-08-16',
  total_amount: '672000.00',
  direct_amount: '250000.00',
  public_amount: '422000.00',
  direct_share: '37.2024',
  public_share: '62.7976',
  confirmed_output_weight_jin: '98000.000',
  confirmed_income_amount: '815000.00',
  confirmed_profit_amount: '143000.00',
  unit_production_cost: '6.8571',
  unit_cost_status: 'available',
  source_fact_counts: { warehouse: 12, purchase: 4, production: 3, expense: 6, asset: 2, sales: 5 },
  source_quality: 'legacy_import',
  confirmed_entry_count: 9,
  has_data: true,
  categories,
}

const ruleVersion = {
  id: 1,
  version_no: 1,
  effective_from: '2026-01-01',
  effective_to: null,
  status: 'active',
  change_reason: '初始化九类成本分摊规则',
  created_by_name: '财务管理员',
  rules: categories.map((item) => ({
    category_id: item.id,
    category_code: item.code,
    category_name: item.name,
    driver: item.allocation_driver,
    fallback_driver: 'equal',
    manual_ratio_json: null,
  })),
}

const scheduledRuleVersion = {
  ...ruleVersion,
  id: 2,
  version_no: 2,
  effective_from: '2099-01-01',
  change_reason: '下一期间分摊规则',
  rules: ruleVersion.rules.map((item) => item.category_id === 9 ? { ...item, driver: 'area' } : item),
}

function response(data: unknown, status = 200) {
  const code = status >= 400 ? 'SERVER_ERROR' : 'OK'
  return Promise.resolve(new Response(JSON.stringify({ code, message: status >= 400 ? '保存失败' : '操作成功', data, request_id: 'cost-test' }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

function mockCostApi(options: { putStatus?: number; savedVersion?: number; latestVersion?: number } = {}) {
  const calls: Array<{ path: string; method: string; body?: unknown }> = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    const method = (init?.method ?? 'GET').toUpperCase()
    calls.push({ path, method, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    if (path.includes('/api/v1/auth/csrf')) return response({ csrf_token: 'csrf-token' })
    if (path.includes('/api/v1/cost/structure')) return response(structure)
    if (path.includes('/api/v1/cost/entries')) {
      return response({
        items: [
          { id: 7, category_code: 'feed', category_name: '饲料', amount: '128000.00', occurred_on: '2026-08-15', period_start: '2026-01-01', period_end: '2026-08-15', status: 'confirmed', source_type: 'legacy_import', source_ref: 'LEGACY-INIT-2026', source_detail_json: { note: '从既有成本构成页面迁移的初始化口径' } },
          { id: -8, category_code: 'feed', category_name: '饲料', amount: '20.00', occurred_on: '2026-08-16', period_start: '2026-01-01', period_end: '2026-08-16', status: 'confirmed', source_type: 'warehouse_issue', source_ref: 'OUT-42', source_detail_json: { purchase_order_id: 42, inventory_ledger_id: 8 } },
        ],
        page: 1,
        page_size: 20,
        total: 2,
        has_next: false,
      })
    }
    if (path.includes('/api/v1/cost/allocation-rules') && method === 'PUT') {
      if (options.putStatus) return response(null, options.putStatus)
      const body = init?.body ? JSON.parse(String(init.body)) : {}
      return response({ ...scheduledRuleVersion, id: options.savedVersion ?? 2, version_no: options.savedVersion ?? 2, effective_from: body.effective_from, change_reason: '调整年度公共费用口径' })
    }
    if (path.includes('/api/v1/cost/allocation-rules')) {
      return response(path.includes('mode=latest') && options.latestVersion === 2 ? scheduledRuleVersion : ruleVersion)
    }
    return response(null, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock }
}

function mountPage(permissions = ['cost.view', 'cost.allocation.manage']) {
  createSessionStore().setUser({
    id: 1,
    name: '成本管理员',
    phone: '13800000000',
    status: 'active',
    roles: [{ id: 6, code: 'finance_staff', name: '财务人员' }],
    data_scopes: [],
    permissions,
  })
  return mount(CostPage, {
    global: {
      stubs: {
        AppShell: { template: '<div><slot /></div>' },
        Teleport: true,
      },
    },
  })
}

afterEach(() => {
  createSessionStore().clear()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('CostPage', () => {
  it('renders server totals and honest unit-cost availability', async () => {
    mockCostApi()
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[data-testid="cost-total"]').text()).toContain('672,000.00')
    expect(wrapper.get('[data-testid="cost-direct-share"]').text()).toContain('37.2%')
    expect(wrapper.get('[data-testid="cost-public-share"]').text()).toContain('62.8%')
    expect(wrapper.get('[data-testid="cost-income"]').text()).toContain('815,000.00')
    expect(wrapper.get('[data-testid="cost-profit"]').text()).toContain('143,000.00')
    expect(wrapper.get('[data-testid="cost-unit-cost"]').text()).toContain('6.8571')
    expect(wrapper.text()).toContain('98,000.000 斤')
    expect(wrapper.text()).toContain('财务管理员')
    expect(wrapper.find('[style*="320%"]').exists()).toBe(false)
  })

  it('shows an API error instead of falling back to static cost data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('成本数据加载失败')
    expect(wrapper.text()).not.toContain('672,000.00')
  })

  it('keeps the rule dialog open on save failure', async () => {
    mockCostApi({ putStatus: 500 })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('[data-testid="open-allocation-rules"]').trigger('click')
    await wrapper.get('#allocation-reason').setValue('调整年度公共费用口径')
    await wrapper.get('[data-testid="save-allocation-rules"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="allocation-error"]').text()).toContain('分摊规则保存失败')
  })

  it('shows the server version after a successful save', async () => {
    const { calls } = mockCostApi({ savedVersion: 2 })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('[data-testid="open-allocation-rules"]').trigger('click')
    await wrapper.get('#allocation-reason').setValue('调整年度公共费用口径')
    await wrapper.get('[data-testid="save-allocation-rules"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('规则版本 v2 已保存')
    expect(wrapper.text()).toContain('当前规则 v1')
    expect(wrapper.text()).toContain('待生效规则 v2')
    expect(wrapper.text()).not.toContain('当前规则 v2')
    expect(calls.find((call) => call.method === 'PUT')?.body).toMatchObject({ change_reason: '调整年度公共费用口径' })
  })

  it('uses the effective rule driver instead of the category default', async () => {
    const currentDriver = ruleVersion.rules.find((item) => item.category_id === 9)!.driver
    ruleVersion.rules.find((item) => item.category_id === 9)!.driver = 'area'
    mockCostApi()
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[data-testid="cost-row-other"]').text()).toContain('按塘口面积')
    ruleVersion.rules.find((item) => item.category_id === 9)!.driver = currentDriver
  })

  it('shows a separately scheduled latest rule after reload', async () => {
    mockCostApi({ latestVersion: 2 })
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('当前规则 v1')
    expect(wrapper.text()).toContain('待生效规则 v2')
  })

  it('moves focus into the allocation dialog and restores it on Escape', async () => {
    mockCostApi()
    const focus = vi.spyOn(HTMLElement.prototype, 'focus')
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="open-allocation-rules"]').trigger('click')
    await flushPromises()
    expect(focus).toHaveBeenCalled()
    await wrapper.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    await flushPromises()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(focus.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('shows the empty state when categories exist but no confirmed records do', async () => {
    const emptyStructure = { ...structure, has_data: false, confirmed_entry_count: 0 }
    const { fetchMock } = mockCostApi()
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/api/v1/cost/structure')) return response(emptyStructure)
      if (path.includes('/api/v1/cost/allocation-rules')) return response(ruleVersion)
      return response({ csrf_token: 'csrf-token' })
    })
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('当前期间暂无已确认成本记录')
    expect(wrapper.find('[data-testid="cost-row-feed"]').exists()).toBe(false)
    expect(wrapper.get('.page-title__actions button').attributes('disabled')).toBeDefined()
  })

  it('loads traceable source details when a category row is opened', async () => {
    mockCostApi()
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('[data-testid="cost-row-feed"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="cost-entry-drawer"]').text()).toContain('LEGACY-INIT-2026')
    expect(wrapper.get('[data-testid="cost-entry-drawer"]').text()).toContain('初始化口径')
    expect(wrapper.get('[data-testid="cost-entry-drawer"]').text()).toContain('采购单 #42 · 库存流水 #8')
  })

  it('moves focus into the source drawer and restores it on Escape', async () => {
    mockCostApi()
    const focus = vi.spyOn(HTMLElement.prototype, 'focus')
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="cost-row-feed"]').trigger('click')
    await flushPromises()
    expect(focus).toHaveBeenCalled()
    await wrapper.get('[data-testid="cost-entry-drawer"]').trigger('keydown', { key: 'Escape' })
    await flushPromises()

    expect(wrapper.find('[data-testid="cost-entry-drawer"]').exists()).toBe(false)
    expect(focus.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('keeps allocation controls hidden for view-only users', async () => {
    mockCostApi()
    const wrapper = mountPage(['cost.view'])
    await flushPromises()

    expect(wrapper.find('[data-testid="open-allocation-rules"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('仅查看')
  })
})
