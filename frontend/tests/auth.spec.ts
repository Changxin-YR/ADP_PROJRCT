import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import FormField from '../src/layers/common/ui/FormField.vue'
import { createApiClient } from '../src/layers/common/api/client'
import { createSessionStore } from '../src/layers/common/session/session.store'

describe('auth common layer', () => {
  it('uses the airy sea-salt theme for the page background and card surface', () => {
    const tokens = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8')
    const styles = readFileSync(resolve(process.cwd(), 'src/styles/auth.css'), 'utf8')

    expect(tokens).toContain('--auth-bg: #e9f5f5;')
    expect(styles).toContain('linear-gradient(135deg,#e9f5f5')
    expect(styles).toContain('background:rgba(255,255,255,.86)')
  })

  it('uses the design primary token and a visible focus ring contract', () => {
    const tokens = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8')
    const styles = readFileSync(resolve(process.cwd(), 'src/styles/auth.css'), 'utf8')

    expect(tokens).toContain('--auth-accent: #14b8a6;')
    expect(styles).toContain('outline:2px solid #5eead4')
  })

  it('keeps password controls at the shared input height', () => {
    const styles = readFileSync(resolve(process.cwd(), 'src/styles/auth.css'), 'utf8')

    expect(styles).toMatch(/\.password-control input[^}]*min-height:43px/)
  })

  it('renders an accessible field label, error and invalid state', () => {
    const wrapper = mount(FormField, {
      props: {
        id: 'phone',
        label: '手机号',
        modelValue: '',
        error: '请输入手机号',
      },
      slots: { default: '<input id="phone" />' },
    })

    expect(wrapper.text()).toContain('手机号')
    expect(wrapper.text()).toContain('请输入手机号')
    expect(wrapper.find('[aria-invalid="true"]').exists()).toBe(true)
  })

  it('adds CSRF token to state-changing requests', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { csrf_token: 'csrf-123' } })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'OK', data: null })))
    vi.stubGlobal('fetch', fetchMock)
    const client = createApiClient()

    await client.post('/api/v1/auth/login', { identifier: '13800000000', password: 'FarmPass9!' })

    expect(new Headers(fetchMock.mock.calls[1][1].headers).get('X-CSRF-Token')).toBe('csrf-123')
  })

  it('keeps only the current user summary and maps status for routing', () => {
    const store = createSessionStore()
    store.setUser({ id: 1, name: '张三', phone: '13800000000', status: 'pending', roles: [], data_scopes: [], permissions: [] })

    expect(store.user.value?.status).toBe('pending')
    expect(store.nextPath.value).toBe('/auth/pending')
  })

  it('shares the current user between session store consumers', () => {
    const first = createSessionStore()
    const second = createSessionStore()
    first.setUser({ id: 2, name: '管理员', phone: '13800000001', status: 'active', roles: [{ id: 1, code: 'admin', name: '管理员' }], data_scopes: [], permissions: ['auth.user.manage'] })

    expect(second.user.value?.id).toBe(2)
    second.clear()
    expect(first.user.value).toBeNull()
  })
})
