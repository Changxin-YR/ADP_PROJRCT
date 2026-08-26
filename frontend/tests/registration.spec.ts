import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import LoginPage from '../src/layers/product/auth/LoginPage.vue'
import RegisterPage from '../src/layers/product/auth/RegisterPage.vue'
import PendingPage from '../src/layers/product/auth/PendingPage.vue'
import PasswordChangePage from '../src/layers/product/auth/PasswordChangePage.vue'
import { validateRegistration } from '../src/layers/common/validation/auth.validation'

const global = { stubs: { RouterLink: { template: '<a><slot /></a>' } } }

async function mountWithRouter(component: typeof LoginPage, path: string) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/auth/login', component: LoginPage }, { path: '/auth/register', component: RegisterPage }] })
  await router.push(path)
  await router.isReady()
  return mount(component, { global: { ...global, plugins: [router] } })
}

describe('auth product pages', () => {
  it('renders the login identifier, password and primary action', async () => {
    const wrapper = await mountWithRouter(LoginPage, '/auth/login')
    expect(wrapper.find('input[autocomplete="username"]').exists()).toBe(true)
    expect(wrapper.find('input[autocomplete="current-password"]').exists()).toBe(true)
    expect(wrapper.find('button[type="submit"]').text()).toContain('登录')
  })

  it('renders all required registration fields and review notice', async () => {
    const wrapper = await mountWithRouter(RegisterPage, '/auth/register')
    expect(wrapper.find('input[autocomplete="tel"]').exists()).toBe(true)
    expect(wrapper.find('input[autocomplete="name"]').exists()).toBe(true)
    expect(wrapper.find('#register-role').exists()).toBe(true)
    expect(wrapper.find('#register-area').exists()).toBe(true)
    expect(wrapper.find('#register-note').exists()).toBe(true)
    expect(wrapper.text()).toContain('审核通过后按所申请的数据范围开放业务数据')
  })

  it('rejects one-character names before submitting', () => {
    const errors = validateRegistration({ phone: '13800000000', name: '李', password: 'FarmPass9!', confirm_password: 'FarmPass9!', desired_role_id: 3, area_id: 1, application_note: '' })

    expect(errors.name).toBe('姓名长度必须为 2-40 个字符')
  })

  it('places the review notice after the registration form and provides placeholders', async () => {
    const wrapper = await mountWithRouter(RegisterPage, '/auth/register')
    const form = wrapper.find('form').element
    const notice = wrapper.find('.page-notice').element

    expect(Boolean(form.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    expect(wrapper.find('#register-role option[disabled]').text()).toBe('请选择申请岗位')
    expect(wrapper.find('#register-area option[disabled]').text()).toBe('请选择所属区域/基地')
  })

  it('renders the first-login password copy and hides current password', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/auth/first-password', component: PasswordChangePage, meta: { mode: 'first-login' } }] })
    await router.push('/auth/first-password')
    await router.isReady()
    const wrapper = mount(PasswordChangePage, {
      global: { ...global, plugins: [router] },
    })
    expect(wrapper.text()).toContain('首次设置密码')
    expect(wrapper.find('#current-password').exists()).toBe(true)
    expect(wrapper.find('#new-password').exists()).toBe(true)
  })

  it('shows an explicit success confirmation after registration submission', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/api/v1/auth/me')) {
        return Promise.resolve(new Response(JSON.stringify({ code: 'OK', data: { user: { id: 8, name: '申请人', phone: '13800000000', status: 'pending', roles: [], data_scopes: [], permissions: [] } }, request_id: 'test' }), { headers: { 'Content-Type': 'application/json' } }))
      }
      return Promise.resolve(new Response(JSON.stringify({ code: 'OK', data: { application: { id: 11, version_no: 1, name: '申请人', desired_role_id: 3, area_id: 1, status: 'pending', application_note: '', desired_role_name: '养殖员', area_name: '北区基地' } }, request_id: 'test' }), { headers: { 'Content-Type': 'application/json' } }))
    }))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/auth/pending', component: PendingPage }] })
    await router.push('/auth/pending?submitted=1')
    await router.isReady()
    const wrapper = mount(PendingPage, { global: { ...global, plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('注册申请提交成功')
  })
})
