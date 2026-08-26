import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import AccountReviewPage from '../src/layers/product/admin/AccountReviewPage.vue'
import UserManagementPage from '../src/layers/product/admin/UserManagementPage.vue'
import WorkbenchPage from '../src/layers/product/auth/WorkbenchPage.vue'
import BackButton from '../src/layers/common/ui/BackButton.vue'
import { createRouter, createMemoryHistory } from 'vue-router'

const global = { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } }

describe('admin auth pages', () => {
  it('shows review actions and requires a rejection reason field', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      const data = path.includes('/api/v1/admin/options')
        ? {
            roles: [{ id: 1, code: 'super_admin', name: '超级管理员' }],
            areas: [{ id: 1, code: 'north-farm', name: '北区基地' }],
            data_scopes: [{ id: 1, code: 'farm-all', name: '全场数据', scope_type: 'farm', area_id: null }],
          }
        : {
            items: [{ id: 1, name: '申请人', version_no: 1, desired_role_id: 1, area_id: 1, application_note: '', status: 'pending' }],
            page: 1,
            page_size: 20,
            total: 1,
            has_next: false,
          }
      return Promise.resolve(new Response(JSON.stringify({ code: 'OK', data, request_id: 'test' }), {
        headers: { 'Content-Type': 'application/json' },
      }))
    }))
    const reviewRouter = createRouter({ history: createMemoryHistory(), routes: [{ path: '/admin/applications', component: AccountReviewPage }, { path: '/workbench', component: WorkbenchPage }] })
    await reviewRouter.push('/admin/applications')
    await reviewRouter.isReady()
    const wrapper = mount(AccountReviewPage, { global: { ...global, plugins: [reviewRouter] } })
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('申请审核')
    expect(wrapper.find('button').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="返回上一步"]').exists()).toBe(true)
    expect(wrapper.find('#rejection-reason').exists()).toBe(true)
  })

  it('keeps the last successful list and exposes retry after a transient refresh failure', async () => {
    const successfulResponse = new Response(JSON.stringify({ code: 'OK', data: { items: [{ id: 7, name: '申请人', version_no: 1, desired_role_id: 1, area_id: 1, application_note: '', status: 'pending' }], page: 1, page_size: 20, total: 1, has_next: false }, request_id: 'test' }), { headers: { 'Content-Type': 'application/json' } })
    const fetchMock = vi.fn().mockResolvedValueOnce(successfulResponse).mockRejectedValueOnce(new TypeError('network unavailable'))
    vi.stubGlobal('fetch', fetchMock)
    const reviewRouter = createRouter({ history: createMemoryHistory(), routes: [{ path: '/admin/applications', component: AccountReviewPage }, { path: '/workbench', component: WorkbenchPage }] })
    await reviewRouter.push('/admin/applications')
    await reviewRouter.isReady()
    const wrapper = mount(AccountReviewPage, { global: { ...global, plugins: [reviewRouter] } })
    await flushPromises()

    await wrapper.get('button[aria-label="刷新申请列表"]').trigger('click')
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 150))
    await flushPromises()

    expect(wrapper.text()).toContain('申请人')
    expect(wrapper.find('button[aria-label="重试加载"]').exists()).toBe(true)
  })

  it('does not render temporary passwords in user management results', async () => {
    const managementRouter = createRouter({ history: createMemoryHistory(), routes: [{ path: '/admin/users', component: UserManagementPage }, { path: '/workbench', component: WorkbenchPage }] })
    await managementRouter.push('/admin/users')
    await managementRouter.isReady()
    const wrapper = mount(UserManagementPage, { global: { ...global, plugins: [managementRouter] } })
    expect(wrapper.text()).toContain('创建账号')
    expect(wrapper.find('button[aria-label="返回上一步"]').exists()).toBe(true)
    expect(wrapper.find('#temporary-password').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('临时密码：')
  })

  it('returns to the previous page and falls back to the workbench on direct entry', async () => {
    const historyRouter = createRouter({ history: createMemoryHistory(), routes: [{ path: '/workbench', component: { template: '<div />' } }, { path: '/admin/applications', component: BackButton }] })
    await historyRouter.push('/workbench')
    await historyRouter.push('/admin/applications')
    await historyRouter.isReady()
    const historyWrapper = mount(BackButton, { global: { plugins: [historyRouter] } })
    await historyWrapper.get('button[aria-label="返回上一步"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(historyRouter.currentRoute.value.path).toBe('/workbench')

    const directRouter = createRouter({ history: createMemoryHistory(), routes: [{ path: '/workbench', component: { template: '<div />' } }, { path: '/admin/applications', component: BackButton }] })
    await directRouter.push('/admin/applications')
    await directRouter.isReady()
    const directWrapper = mount(BackButton, { global: { plugins: [directRouter] } })
    await directWrapper.get('button[aria-label="返回上一步"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(directRouter.currentRoute.value.path).toBe('/workbench')
  })

  it('shows management entry points for an administrator in the workbench', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'OK', data: { user: { id: 1, name: '管理员', phone: '13800000000', status: 'active', roles: [{ id: 1, code: 'super_admin', name: '系统管理员' }], data_scopes: [], permissions: ['auth.review', 'auth.user.manage', 'auth.session.view', 'cost.view', 'cost.allocation.manage'] } }, request_id: 'test' }), { headers: { 'Content-Type': 'application/json' } })))
    const testRouter = createRouter({ history: createMemoryHistory(), routes: [{ path: '/workbench', component: WorkbenchPage }] })
    await testRouter.push('/workbench')
    await testRouter.isReady()
    const wrapper = mount(WorkbenchPage, { global: { ...global, plugins: [testRouter] } })
    await flushPromises()

    expect(wrapper.find('a[href="/admin/applications"]').text()).toContain('申请审核')
    expect(wrapper.find('a[href="/admin/users"]').text()).toContain('账号管理')
  })
})
