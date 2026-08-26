import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import { createSessionStore } from '../src/layers/common/session/session.store'
import AppShell from '../src/layers/common/ui/AppShell.vue'
import PondDetailPage from '../src/layers/product/ponds/PondDetailPage.vue'
import QueuePage from '../src/layers/product/workbench/QueuePage.vue'
import RolePage from '../src/layers/product/admin/RolePage.vue'
import WorkbenchDashboardPage from '../src/layers/product/workbench/WorkbenchDashboardPage.vue'

function response(data: unknown, status = 200, message = '操作成功') {
  return Promise.resolve(new Response(JSON.stringify({ code: status < 400 ? 'OK' : 'SERVICE_UNAVAILABLE', message, data, request_id: 'enterprise-test' }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

function router(path = '/workbench') {
  const instance = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/workbench', component: { template: '<div />' } },
      { path: '/ponds/:id', component: { template: '<div />' } },
      { path: '/:pathMatch(.*)*', component: { template: '<div />' } },
    ],
  })
  return instance.push(path).then(() => instance.isReady()).then(() => instance)
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('enterprise workbench data sources', () => {
  it('shows an explicit queue error and never renders demo facts', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response(null, 503, '协作服务暂时不可用')))
    const wrapper = mount(QueuePage, { props: { mode: 'todos' }, global: { stubs: { AppShell: { template: '<main><slot /></main>' }, RouterLink: true, Teleport: true } } })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('服务器暂时无法处理请求')
    expect(wrapper.text()).not.toContain('审核费用')
    expect(wrapper.text()).not.toContain('投喂任务')
  })

  it('shows a dashboard error instead of a mock summary', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response(null, 503, '工作台服务暂时不可用')))
    const wrapper = mount(WorkbenchDashboardPage, { global: { stubs: { AppShell: { template: '<main><slot /></main>' }, RouterLink: true } } })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('服务器暂时无法处理请求')
    expect(wrapper.find('[data-testid="kpi-ponds"]').exists()).toBe(false)
  })

  it('loads shell notification and todo counts from governance APIs', async () => {
    createSessionStore().setUser({ id: 1, phone: '13800000000', name: '管理员', status: 'active', roles: [{ id: 1, code: 'super_admin', name: '超级管理员' }], data_scopes: [], permissions: ['workbench.enter', 'work_item.view', 'auth.user.manage'] })
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/notifications')) return response({ items: [{ id: 9, title: '库存预警', module_code: 'warehouse', level: 'high', status: 'unread', occurrence_count: 1 }], page: 1, page_size: 100, total: 1, has_next: false })
      if (path.includes('/work-items')) return response({ items: [{ id: 3, title: '核验入库', module_code: 'warehouse', action_code: 'verify', priority: 'normal', status: 'pending', row_version: 1 }], page: 1, page_size: 100, total: 1, has_next: false })
      return response({ items: [], page: 1, page_size: 100, total: 0, has_next: false })
    }))
    const wrapper = mount(AppShell, { global: { plugins: [await router()], stubs: { Teleport: true } } })
    await flushPromises()

    expect(wrapper.get('[data-testid="notification-count"]').text()).toBe('1')
    expect(wrapper.get('[data-testid="todo-count"]').text()).toBe('1')
  })

  it('renders roles returned by the admin API', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({ items: [{ id: 88, code: 'auditor', name: '审计观察员', description: '只读审计', status: 'active', user_count: 2, permissions: [{ code: 'audit.view', name: '查看审计', module_code: 'admin' }] }], available_permissions: [{ code: 'audit.view', name: '查看审计', module_code: 'admin' }], total: 1 })))
    const wrapper = mount(RolePage, { global: { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } } })
    await flushPromises()

    expect(wrapper.text()).toContain('审计观察员')
    expect(wrapper.text()).toContain('2')
    expect(wrapper.text()).not.toContain('养殖作业员')
  })

  it('changes database role permissions only after the second confirmation', async () => {
    const roleList = { items: [{ id: 2, code: 'breed_manager', name: '养殖管理员', status: 'active', user_count: 1, permissions: [{ code: 'production.view', name: '查看养殖', module_code: 'production' }] }], available_permissions: [{ code: 'production.view', name: '查看养殖', module_code: 'production' }], total: 1 }
    const fetch = vi.fn((input: RequestInfo | URL) => String(input).includes('/auth/csrf') ? response({ csrf_token: 'csrf' }) : response(roleList))
    vi.stubGlobal('fetch', fetch)
    const wrapper = mount(RolePage, { global: { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } } })
    await flushPromises()

    const edit = wrapper.findAll('button').find((button) => button.text() === '编辑权限')
    expect(edit).toBeDefined()
    await edit!.trigger('click')
    await wrapper.get('[data-testid="role-permissions-next"]').trigger('click')
    expect(fetch).toHaveBeenCalledTimes(1)
    await wrapper.get('[data-testid="role-permissions-confirm"]').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith('/api/v1/admin/roles/2/permissions', expect.objectContaining({ method: 'PUT', body: JSON.stringify({ permission_codes: ['production.view'], confirm_phrase: 'CONFIRM' }) }))
  })

  it('loads a verified pond from the API and keeps it read-only', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({ record: { id: 7, code: 'P-007', name: '核验塘', area_id: 1, pond_group_id: null, capacity_mu: 12, species: '鲈鱼', manager_name: '周经理', location_text: '东区', pond_status: 'farming', status: 'verified', row_version: 4, version: 4, allowed_actions: ['view'], timeline: [] } })))
    const wrapper = mount(PondDetailPage, { global: { plugins: [await router('/ponds/7')], stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } } })
    await flushPromises()

    expect(wrapper.text()).toContain('核验塘')
    expect(wrapper.text()).toContain('已核验')
    expect(wrapper.text()).not.toContain('编辑塘口')
  })

  it('requests a verified pond status change through the governed endpoint', async () => {
    const fetch = vi.fn((input: RequestInfo | URL) => String(input).includes('/auth/csrf')
      ? response({ csrf_token: 'csrf' })
      : String(input).endsWith('/status-changes')
        ? response({ status_change: { id: 19, status: 'submitted' } }, 201)
        : response({ record: { id: 7, code: 'P-007', name: '核验塘', pond_status: 'farming', status: 'verified', row_version: 4, version: 4, allowed_actions: ['view'], status_change_targets: ['clean', 'rest'], can_request_status_change: true, can_verify_status_change: false, pending_status_change: null, timeline_preview: [] } }))
    vi.stubGlobal('fetch', fetch)
    const wrapper = mount(PondDetailPage, { global: { plugins: [await router('/ponds/7')], stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } } })
    await flushPromises()

    expect(wrapper.text()).not.toContain('编辑塘口')
    await wrapper.get('[data-testid="request-pond-status"]').trigger('click')
    await wrapper.get('select').setValue('clean')
    await wrapper.get('textarea').setValue('批次结束清塘')
    await wrapper.get('[data-testid="submit-pond-status"]').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith('/api/v1/master-data/ponds/7/status-changes', expect.objectContaining({ method: 'POST', body: JSON.stringify({ to_status: 'clean', reason: '批次结束清塘', expected_version: 4 }) }))
  })

  it('does not expose generic completion for domain review work items', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({ items: [{ id: 12, title: '核验塘口状态变更', module_code: 'master_data', action_code: 'verify', object_type: 'master:pond_status_change', object_id: 7, priority: 'normal', status: 'pending', row_version: 1, handling_mode: 'domain' }], page: 1, page_size: 100, total: 1, has_next: false })))
    const wrapper = mount(QueuePage, { props: { mode: 'todos' }, global: { stubs: { AppShell: { template: '<main><slot /></main>' }, RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' }, Teleport: true } } })
    await flushPromises()

    expect(wrapper.text()).toContain('去处理')
    expect(wrapper.findAll('button').some((button) => button.text() === '完成')).toBe(false)
    expect(wrapper.get('a').attributes('href')).toBe('/ponds/7')
  })

  it('keeps notification object identity, supports closing, and paginates history', async () => {
    const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path.includes('/auth/csrf')) return response({ csrf_token: 'csrf' })
      if (path.includes('/notifications/9')) return response({ notification: { id: 9, title: '库存预警', module_code: 'warehouse', status: 'closed', close_conclusion: '已处理' } })
      if (path.includes('/notifications?')) return response({ items: [{ id: 9, title: '库存预警', body: '请处理', module_code: 'warehouse', object_type: 'warehouse:alerts', object_id: 12, object_ref: 'alerts:12', level: 'high', status: 'unread', occurrence_count: 1 }], page: 2, page_size: 100, total: 101, has_next: false })
      return response({ items: [], page: 1, page_size: 100, total: 0, has_next: false })
    })
    vi.stubGlobal('fetch', fetch)
    vi.stubGlobal('prompt', vi.fn(() => '已处理'))
    const wrapper = mount(QueuePage, { props: { mode: 'messages' }, global: { stubs: { AppShell: { template: '<main><slot /></main>' }, RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' }, Teleport: true } } })
    await flushPromises()

    expect(wrapper.get('a').attributes('href')).toBe('/warehouse/alerts')
    expect(wrapper.text()).toContain('关闭')
    await wrapper.findAll('button').find((button) => button.text() === '关闭')!.trigger('click')
    await flushPromises()
    expect(fetch).toHaveBeenCalledWith('/api/v1/notifications/9', expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ status: 'closed', conclusion: '已处理' }) }))
    expect(fetch.mock.calls.some(([input]) => String(input).includes('/notifications?include_history=true&page=1&page_size=100'))).toBe(true)
  })

  it('renders unavailable production metrics without fake zeroes', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response({ date_label: '2026年08月17日', availability: { production: false }, kpis: { ponds: null, active_batches: null, current_stock: null, todo_open: 2 }, pond_status: [], todos: [], alerts: [], recent_batches: [] })))
    const wrapper = mount(WorkbenchDashboardPage, { global: { stubs: { AppShell: { template: '<main><slot /></main>' }, RouterLink: true } } })
    await flushPromises()

    expect(wrapper.text()).toContain('--')
    expect(wrapper.text()).toContain('无养殖数据权限')
  })

  it('contains no production static fallback or browser business storage', async () => {
    const modules = import.meta.glob('../src/**/*.{ts,vue}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
    const offenders = Object.entries(modules).filter(([path, source]) => !path.includes('/features/dataset/') && !path.includes('/features/workbench/workbench.mock') && /dataset\/dataset|workbench\.mock|localStorage|sessionStorage/.test(source))
    expect(offenders.map(([path]) => path)).toEqual([])
  })
})
