import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import ExpensePage from '../src/layers/product/cost/ExpensePage.vue'
import AssetPage from '../src/layers/product/cost/AssetPage.vue'
import SettlementPage from '../src/layers/product/cost/SettlementPage.vue'


const globals = { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } }
const page = (items: unknown[], current = 1, total = items.length) => ({ items, page: current, page_size: 20, total, has_next: current * 20 < total })
function response(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify({
    code: status >= 400 ? 'COST_UNAVAILABLE' : 'OK', message: status >= 400 ? '成本服务不可用' : '操作成功',
    data, request_id: 'cost-enterprise-test',
  }), { status, headers: { 'Content-Type': 'application/json' } }))
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('enterprise cost pages', () => {
  it('loads expenses, assets and settlements from governed APIs', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input); paths.push(path)
      if (path.includes('/api/v1/cost/expenses?page=2')) return response(page([{
        id: 32, source_ref: 'EXP-API-32', category_name: '人工', amount: '80.00', occurred_on: '2026-08-11',
        status: 'confirmed', version: 4, allowed_actions: ['view', 'reverse'],
      }], 2, 21))
      if (path.startsWith('/api/v1/cost/expenses')) return response(page([{
        id: 31, source_ref: 'EXP-API-31', category_name: '电费', amount: '150.00', occurred_on: '2026-08-10',
        target_type: 'area', target_id: 2, status: 'submitted', version: 3, allowed_actions: ['view', 'edit', 'verify'],
      }], 1, 21))
      if (path.startsWith('/api/v1/cost/assets')) return response(page([{
        id: 41, code: 'ASSET-API-41', name: '北区增氧机', category_name: '设备', original_value: '1200.00',
        useful_life_months: 12, accumulated_depreciation: '100.00', status: 'confirmed', version: 4,
        allowed_actions: ['view', 'depreciate'],
      }]))
      if (path.startsWith('/api/v1/cost/settlements')) return response(page([{
        id: 51, code: 'SET-202608-1', name: '2026-08 期间结算', period_start: '2026-08-01', period_end: '2026-08-31',
        income_amount: '260.00', cost_amount: '150.00', profit_amount: '110.00', status: 'confirmed', operator: '财务 A',
        version: 4, allowed_actions: ['view', 'reverse'],
      }]))
      return response(null, 404)
    }))

    const expense = mount(ExpensePage, { global: globals })
    const asset = mount(AssetPage, { global: globals })
    const settlement = mount(SettlementPage, { global: globals })
    await flushPromises()

    expect(paths).toEqual(expect.arrayContaining(['/api/v1/cost/expenses?page=1&page_size=20', '/api/v1/cost/assets?page=1&page_size=20', '/api/v1/cost/settlements?page=1&page_size=20']))
    expect(expense.text()).toContain('EXP-API-31')
    expect(expense.find('[data-testid="cost-expense-action-view"]').exists()).toBe(true)
    expect(expense.find('[data-testid="cost-expense-action-verify"]').exists()).toBe(true)
    expect(asset.text()).toContain('ASSET-API-41')
    expect(asset.find('[data-testid="cost-asset-action-depreciate"]').exists()).toBe(true)
    expect(settlement.text()).toContain('SET-202608-1')
    expect(settlement.find('[data-testid="cost-settlement-action-reverse"]').exists()).toBe(true)
    expect(expense.text()).not.toContain('EX-0812-01')
    expect(asset.text()).not.toContain('AS-EQ-014')
    expect(settlement.text()).not.toContain('91,600')
    await expense.get('[data-testid="table-next-page"]').trigger('click')
    await flushPromises()
    expect(paths).toContain('/api/v1/cost/expenses?page=2&page_size=20')
    expect(expense.text()).toContain('EXP-API-32')
  })

  it('shows explicit API errors and never restores demo rows', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response(null, 503)))
    const wrappers = [ExpensePage, AssetPage, SettlementPage].map((component) => mount(component, { global: globals }))
    await flushPromises()
    for (const wrapper of wrappers) {
      expect(wrapper.get('[role="alert"]').text()).toContain('数据加载失败')
      expect(wrapper.text()).not.toContain('EX-0812-01')
      expect(wrapper.text()).not.toContain('AS-EQ-014')
      expect(wrapper.text()).not.toContain('91,600')
    }
  })

  it('executes governed expense, depreciation and reversal actions', async () => {
    const calls: Array<{ path: string; method: string; body: string }> = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input), method = init?.method ?? 'GET'; calls.push({ path, method, body: String(init?.body ?? '') })
      if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
      if (method === 'POST' && path.endsWith('/expenses/31/verify')) return response({ id: 31, source_ref: 'EXP-31', category_name: '电费', amount: '150.00', occurred_on: '2026-08-10', status: 'verified', version: 4, allowed_actions: ['view', 'confirm'] })
      if (method === 'POST' && path.endsWith('/assets/41/depreciate')) return response({ asset_id: 41, period: '2026-09', amount: '100.00' })
      if (method === 'POST' && path.endsWith('/settlements/51/reverse')) return response({ id: 51, code: 'SET-51', name: '八月结算', period_start: '2026-08-01', period_end: '2026-08-31', income_amount: '260.00', cost_amount: '150.00', profit_amount: '110.00', status: 'reversed', version: 5, allowed_actions: ['view'] })
      if (path.startsWith('/api/v1/cost/expenses')) return response(page([{ id: 31, source_ref: 'EXP-31', category_name: '电费', amount: '150.00', occurred_on: '2026-08-10', status: 'submitted', version: 3, allowed_actions: ['view', 'edit', 'verify'] }]))
      if (path.startsWith('/api/v1/cost/assets')) return response(page([{ id: 41, code: 'ASSET-41', name: '增氧机', category_name: '设备', original_value: '1200.00', useful_life_months: 12, accumulated_depreciation: '0.00', status: 'confirmed', version: 4, allowed_actions: ['view', 'depreciate'] }]))
      if (path.startsWith('/api/v1/cost/settlements')) return response(page([{ id: 51, code: 'SET-51', name: '八月结算', period_start: '2026-08-01', period_end: '2026-08-31', income_amount: '260.00', cost_amount: '150.00', profit_amount: '110.00', status: 'confirmed', version: 4, allowed_actions: ['view', 'reverse'] }]))
      return response(null, 404)
    }))
    const expense = mount(ExpensePage, { global: globals }), asset = mount(AssetPage, { global: globals }), settlement = mount(SettlementPage, { global: globals })
    await flushPromises()
    await expense.get('[data-testid="cost-expense-action-verify"]').trigger('click')
    await expense.get('#cost-expense-evidence').setValue('12'); await expense.get('[data-testid="cost-expense-confirm"]').trigger('click')
    await asset.get('[data-testid="cost-asset-action-depreciate"]').trigger('click')
    await asset.get('#cost-asset-period').setValue('2026-09'); await asset.get('[data-testid="cost-asset-confirm"]').trigger('click')
    await settlement.get('[data-testid="cost-settlement-action-reverse"]').trigger('click')
    await settlement.get('#cost-settlement-reason').setValue('发现漏单重新结算'); await settlement.get('[data-testid="cost-settlement-confirm"]').trigger('click')
    await flushPromises()
    expect(calls).toEqual(expect.arrayContaining([
      expect.objectContaining({ path: '/api/v1/cost/expenses/31/verify', method: 'POST', body: expect.stringContaining('"expected_version":3') }),
      expect.objectContaining({ path: '/api/v1/cost/assets/41/depreciate', method: 'POST', body: expect.stringContaining('"period":"2026-09"') }),
      expect.objectContaining({ path: '/api/v1/cost/settlements/51/reverse', method: 'POST', body: expect.stringContaining('发现漏单重新结算') }),
    ]))
  })

  it('sends server filters and labels page-only KPIs truthfully', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      paths.push(String(input))
      return response(page([]))
    }))
    const expense = mount(ExpensePage, { global: globals })
    const asset = mount(AssetPage, { global: globals })
    const settlement = mount(SettlementPage, { global: globals })
    await flushPromises()

    await expense.get('[aria-label="全部状态"]').setValue('confirmed')
    await expense.get('[aria-label="搜索费用单号"]').setValue('EXP-42')
    await asset.get('[aria-label="全部状态"]').setValue('confirmed')
    await asset.get('[aria-label="搜索资产名称 / 编号"]').setValue('增氧机')
    await settlement.get('[aria-label="全部状态"]').setValue('confirmed')
    await settlement.get('[aria-label="搜索结算期间 / 单号"]').setValue('2026-08')
    await flushPromises()

    expect(paths).toContain('/api/v1/cost/expenses?page=1&page_size=20&status=confirmed&search=EXP-42')
    expect(paths).toContain('/api/v1/cost/assets?page=1&page_size=20&status=confirmed&search=%E5%A2%9E%E6%B0%A7%E6%9C%BA')
    expect(paths).toContain('/api/v1/cost/settlements?page=1&page_size=20&status=confirmed&search=2026-08')
    for (const wrapper of [expense, asset, settlement]) expect(wrapper.text()).toContain('本页')
  })

  it('edits and deletes settlement drafts while verified records open read-only', async () => {
    const calls: Array<{ path: string; method: string; body: string }> = []
    const draft = { id: 51, code: 'SET-51', name: '八月结算', period_start: '2026-08-01', period_end: '2026-08-31', allocation_run_id: 7, income_amount: '260.00', cost_amount: '150.00', profit_amount: '110.00', status: 'draft', version: 1, allowed_actions: ['view', 'edit', 'delete', 'submit'] }
    const verified = { ...draft, id: 52, code: 'SET-52', name: '七月结算', status: 'verified', version: 3, allowed_actions: ['view', 'confirm'] }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input), method = init?.method ?? 'GET'; calls.push({ path, method, body: String(init?.body ?? '') })
      if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
      if (method === 'PATCH') return response({ ...draft, name: '八月正式结算', version: 2, allowed_actions: ['view', 'edit', 'delete', 'submit'] })
      if (method === 'DELETE') return response(draft)
      return response(page([draft, verified]))
    }))
    const wrapper = mount(SettlementPage, { global: globals }); await flushPromises()
    await wrapper.get('[data-testid="cost-settlement-action-edit"]').trigger('click')
    await wrapper.get('#cost-settlement-name').setValue('八月正式结算')
    await wrapper.get('[data-testid="cost-settlement-save"]').trigger('click'); await flushPromises()
    expect(calls).toContainEqual(expect.objectContaining({ path: '/api/v1/cost/settlements/51', method: 'PATCH', body: expect.stringContaining('"expected_version":1') }))
    await wrapper.get('[data-testid="cost-settlement-action-delete"]').trigger('click')
    await wrapper.get('[data-testid="cost-settlement-confirm"]').trigger('click'); await flushPromises()
    expect(calls).toContainEqual(expect.objectContaining({ path: '/api/v1/cost/settlements/51', method: 'DELETE' }))
    await wrapper.get('[data-testid="cost-settlement-action-view"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('SET-52')
    expect(wrapper.find('[data-testid="cost-settlement-save"]').exists()).toBe(false)
  })

  it('sends the explicit farm and area scope when running allocation', async () => {
    const calls: Array<{ path: string; method: string; body: string }> = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input), method = init?.method ?? 'GET'; calls.push({ path, method, body: String(init?.body ?? '') })
      if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
      if (method === 'POST' && path.endsWith('/cost/allocations')) return response({ id: 9, source_total: '100.00', allocated_total: '100.00', fallback_count: 0, details: [] })
      return response(page([]))
    }))
    const wrapper = mount(SettlementPage, { global: globals }); await flushPromises()
    await wrapper.findAll('button').find((button) => button.text().includes('新建结算'))!.trigger('click')
    await wrapper.get('#cost-settlement-farm').setValue('1')
    await wrapper.get('#cost-settlement-area').setValue('2')
    await wrapper.get('[data-testid="cost-settlement-allocate"]').trigger('click'); await flushPromises()
    expect(calls).toContainEqual(expect.objectContaining({
      path: '/api/v1/cost/allocations', method: 'POST', body: expect.stringContaining('"farm_id":1,"area_id":2'),
    }))
  })
})
