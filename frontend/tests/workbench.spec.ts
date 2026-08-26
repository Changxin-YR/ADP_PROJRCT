import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import WorkbenchDashboardPage from '../src/layers/product/workbench/WorkbenchDashboardPage.vue'
import PondListPage from '../src/layers/product/ponds/PondListPage.vue'
import BatchListPage from '../src/layers/product/batches/BatchListPage.vue'

function router() {
  return createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
}

afterEach(() => vi.unstubAllGlobals())

describe('workbench product UI', () => {
  it('uses the same airy sea-salt background as the authentication pages', () => {
    const styles = readFileSync(resolve(process.cwd(), 'src/styles/workbench.css'), 'utf8')

    expect(styles).toContain('--wb-bg: #e9f5f5;')
    expect(styles).toContain('linear-gradient(135deg,#e9f5f5')
  })

  it('renders the workbench shell content with KPI cards and open todos', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/workbench/summary')) return Promise.resolve(new Response(JSON.stringify({
        code: 'OK', message: '操作成功', request_id: 'workbench-test', data: {
          date_label: '2026年08月17日', kpis: { ponds: 2, active_batches: 1, current_stock: 900, todo_open: 1 },
          pond_status: [{ status: 'farming', label: '养殖中', count: 2 }],
          todos: [{ id: 1, title: '核验塘口', type: '核验', due_at: '今天', overdue: false }], alerts: [], recent_batches: [],
        },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      return Promise.resolve(new Response(JSON.stringify({ code: 'OK', message: '操作成功', data: { items: [], page: 1, page_size: 100, total: 0, has_next: false } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    }))
    const wrapper = mount(WorkbenchDashboardPage, { global: { plugins: [router()] } })
    await flushPromises()

    expect(wrapper.text()).toContain('今日工作台')
    expect(wrapper.text()).toContain('塘口总数')
    expect(wrapper.text()).toContain('我的待办')
    expect(wrapper.find('[data-testid="kpi-ponds"]').exists()).toBe(true)
  })

  it('filters ponds by search text without losing the table context', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({
      code: 'OK', message: '操作成功', request_id: 'pond-list-test',
      data: { items: [
        { id: 101, code: 'DG-001', name: '东港一号塘', area_id: 1, pond_status: 'farming', status: 'verified', capacity_mu: 18, species: '南美白对虾', row_version: 2, version: 2, allowed_actions: ['view'] },
        { id: 103, code: 'NW-001', name: '南湾育苗塘', area_id: 2, pond_status: 'build', status: 'submitted', capacity_mu: 8, species: '加州鲈', row_version: 3, version: 3, allowed_actions: ['view', 'edit', 'verify'] },
      ], page: 1, page_size: 20, total: 2, has_next: false },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))))
    const wrapper = mount(PondListPage, { global: { plugins: [router()] } })
    await flushPromises()

    expect(wrapper.text()).toContain('东港一号塘')
    await wrapper.get('[data-testid="pond-search"]').setValue('南湾')

    expect(wrapper.get('tbody').text()).toContain('南湾育苗塘')
    expect(wrapper.get('tbody').text()).not.toContain('东港一号塘')
    expect(wrapper.text()).toContain('塘口档案')
  })

  it('creates ponds from verified area and matching group options', async () => {
    const calls: Array<{ path: string; method: string; body?: Record<string, unknown> }> = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      calls.push({ path, method, body })
      if (path.includes('/auth/csrf')) return Promise.resolve(new Response(JSON.stringify({ code: 'OK', message: '操作成功', data: { csrf_token: 'csrf' } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      if (method === 'POST') return Promise.resolve(new Response(JSON.stringify({ code: 'OK', message: '操作成功', data: { record: { id: 9, ...body, status: 'draft', version: 1, allowed_actions: ['view', 'edit', 'delete', 'submit'] } } }), { status: 201, headers: { 'Content-Type': 'application/json' } }))
      const items = path.includes('/areas?')
        ? [{ id: 2, code: 'AREA-2', name: '南区', status: 'verified', version: 1, allowed_actions: ['view'] }]
        : path.includes('/pond-groups?')
          ? [{ id: 3, code: 'GROUP-3', name: '育苗组', area_id: 2, status: 'verified', version: 1, allowed_actions: ['view'] }, { id: 4, code: 'GROUP-4', name: '北区组', area_id: 1, status: 'verified', version: 1, allowed_actions: ['view'] }]
          : []
      return Promise.resolve(new Response(JSON.stringify({ code: 'OK', message: '操作成功', data: { items, page: 1, page_size: 100, total: items.length, has_next: false } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    }))
    const wrapper = mount(PondListPage, { global: { plugins: [router()], stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } } })
    await flushPromises()

    await wrapper.get('button.primary-action').trigger('click')
    await wrapper.get('[data-testid="pond-area"]').setValue('2')
    expect(wrapper.get('[data-testid="pond-group"]').text()).toContain('育苗组')
    expect(wrapper.get('[data-testid="pond-group"]').text()).not.toContain('北区组')
    await wrapper.get('[data-testid="pond-name"]').setValue('测试新增塘')
    await wrapper.get('[data-testid="pond-code"]').setValue('P-NEW')
    await wrapper.get('[data-testid="pond-group"]').setValue('3')
    await wrapper.get('[data-testid="pond-save"]').trigger('click')
    await flushPromises()

    expect(calls.find((call) => call.method === 'POST' && call.path.endsWith('/ponds'))?.body).toMatchObject({ area_id: 2, pond_group_id: 3 })
  })

  it('filters batches by lifecycle status and exposes stock summaries', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({
      code: 'OK', message: '操作成功', request_id: 'batch-list-test',
      data: { items: [
        { id: 201, code: 'ADP-2026-001', name: '东港春季虾一批', species: '南美白对虾', batch_status: 'farming', pond_id: 101, initial_quantity: 180000, current_quantity: 153600, current_weight_kg: 7200, status: 'verified', row_version: 3, version: 3, allowed_actions: ['view', 'correct'] },
        { id: 203, code: 'ADP-2026-003', name: '南湾育苗试验批', species: '加州鲈', batch_status: 'pending_settlement', pond_id: 103, initial_quantity: 72000, current_quantity: 0, current_weight_kg: 0, status: 'submitted', row_version: 2, version: 2, allowed_actions: ['view', 'edit', 'verify'] },
      ], page: 1, page_size: 20, total: 2, has_next: false },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))))
    const wrapper = mount(BatchListPage, { global: { plugins: [router()] } })
    await flushPromises()

    expect(wrapper.text()).toContain('ADP-2026-001')
    await wrapper.get('[data-testid="batch-status"]').setValue('pending_settlement')

    expect(wrapper.text()).toContain('ADP-2026-003')
    expect(wrapper.text()).not.toContain('ADP-2026-001')
    expect(wrapper.text()).toContain('当前存量')
  })
})
