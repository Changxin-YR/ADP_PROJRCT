import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import { createSessionStore } from '../src/layers/common/session/session.store'
import AppShell from '../src/layers/common/ui/AppShell.vue'
import RecordActions from '../src/layers/common/ui/RecordActions.vue'


function testRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/workbench', component: { template: '<div />' } },
      { path: '/:pathMatch(.*)*', component: { template: '<div />' } },
    ],
  })
}

describe('shared shell contracts', () => {
  it('preserves navigation search notifications and logout confirmation', async () => {
    createSessionStore().setUser({
      id: 1,
      phone: '13800000000',
      name: '企业管理员',
      status: 'active',
      roles: [{ id: 1, code: 'super_admin', name: '超级管理员' }],
      data_scopes: [],
      permissions: ['auth.user.manage', 'auth.review', 'audit.view', 'workbench.enter', 'work_item.view', 'master_data.view', 'production.view', 'warehouse.view', 'purchase.view', 'sales.view', 'cost.view', 'data_exchange.view'],
    })
    const router = testRouter()
    await router.push('/workbench')
    await router.isReady()
    const wrapper = mount(AppShell, { global: { plugins: [router], stubs: { Teleport: true } } })

    expect(wrapper.text()).toContain('塘口与批次')
    expect(wrapper.text()).toContain('系统管理')
    expect(wrapper.find('[aria-label="全局搜索"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="消息与预警"]').exists()).toBe(true)
    await wrapper.get('[aria-label="退出登录"]').trigger('click')
    expect(wrapper.get('[aria-label="退出登录确认"]').text()).toContain('退出当前账号')
  })

  it('renders only actions supplied by the server', () => {
    const wrapper = mount(RecordActions, {
      props: { actions: ['view', 'edit', 'verify'] },
    })

    expect(wrapper.text()).toContain('查看')
    expect(wrapper.text()).toContain('编辑')
    expect(wrapper.text()).toContain('核验')
    expect(wrapper.text()).not.toContain('删除')
  })
})
