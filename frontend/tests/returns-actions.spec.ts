import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import ReturnPage from '../src/layers/product/returns/ReturnPage.vue'
import { globals, purchaseReturn, salesReturn, stubApi } from './returns-fixtures'

/**
 * 退货出口：列表渲染与动作可见性。
 * 动作只由「服务端 allowed_actions ∩ 后端状态机」决定，前端不自造动作
 * （后端 /returns 无 PATCH，因此不存在 edit）。
 */

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  window.localStorage.clear()
})

describe('return list and action visibility', () => {
  it('renders server rows with status badges and only the server-permitted actions', async () => {
    const calls = stubApi()

    const wrapper = mount(ReturnPage, { props: { mode: 'purchase' }, global: globals })
    await flushPromises()

    expect(calls.some((call) => call.path.startsWith('/api/v1/purchase/returns'))).toBe(true)
    expect(wrapper.text()).toContain('PR-051')
    expect(wrapper.text()).toContain('饲料变质退货')
    expect(wrapper.text()).toContain('草稿')
    expect(wrapper.text()).toContain('待核验') // KPI 标签
    // draft → 服务端允许 view/delete/submit，前端不自造 approve/edit
    expect(wrapper.find('[data-testid="return-action-submit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="return-action-delete"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="return-action-edit"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="return-action-approve"]').exists()).toBe(false)
  })

  it('renders only view for a verified row (no submit/verify/delete)', async () => {
    stubApi({ purchaseReturns: [{ ...purchaseReturn, status: 'verified', allowed_actions: ['view'] }] })

    const wrapper = mount(ReturnPage, { props: { mode: 'purchase' }, global: globals })
    await flushPromises()

    expect(wrapper.text()).toContain('已核验')
    expect(wrapper.find('[data-testid="return-action-view"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="return-action-submit"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="return-action-verify"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="return-action-delete"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="return-action-cancel"]').exists()).toBe(false)
  })

  it('submits a draft through the version-checked endpoint', async () => {
    const calls = stubApi()
    const wrapper = mount(ReturnPage, { props: { mode: 'purchase' }, global: globals })
    await flushPromises()

    await wrapper.get('[data-testid="return-action-submit"]').trigger('click')
    await wrapper.get('[data-testid="return-confirm"]').trigger('click')
    await flushPromises()

    const submitted = calls.find((call) => call.path === '/api/v1/purchase/returns/51/submit')
    expect(submitted).toBeTruthy()
    expect(submitted!.body).toEqual({ expected_version: 1 })
    expect(wrapper.find('[data-testid="return-action-submit"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('待核验')
  })

  it('requires a cancellation reason before calling the cancel endpoint', async () => {
    const calls = stubApi({ purchaseReturns: [{ ...purchaseReturn, status: 'submitted', version: 2, row_version: 2, allowed_actions: ['view', 'verify', 'cancel'] }] })
    const wrapper = mount(ReturnPage, { props: { mode: 'purchase' }, global: globals })
    await flushPromises()

    await wrapper.get('[data-testid="return-action-cancel"]').trigger('click')
    await wrapper.get('[data-testid="return-confirm"]').trigger('click')
    await flushPromises()

    expect(calls.some((call) => call.path.endsWith('/cancel'))).toBe(false)
    expect(wrapper.get('[role="alert"]').text()).toContain('取消退货必须填写原因')

    await wrapper.get('#return-cancellation-reason').setValue('供应商已同意换货')
    await wrapper.get('[data-testid="return-confirm"]').trigger('click')
    await flushPromises()
    const cancelled = calls.find((call) => call.path === '/api/v1/purchase/returns/51/cancel')
    expect(cancelled!.body).toEqual({ expected_version: 2, cancellation_reason: '供应商已同意换货' })
  })

  it('loads customer returns on the sales tab without mixing in supplier rows', async () => {
    const calls = stubApi({ salesReturns: [salesReturn] })
    const wrapper = mount(ReturnPage, { props: { mode: 'sales' }, global: globals })
    await flushPromises()

    expect(calls.some((call) => call.path.startsWith('/api/v1/sales/returns'))).toBe(true)
    expect(wrapper.text()).toContain('客户退货')
    expect(wrapper.text()).toContain('SR-061')
    expect(wrapper.text()).toContain('SD-077')
    expect(wrapper.text()).not.toContain('PR-051')
    expect(wrapper.find('[data-testid="return-action-verify"]').exists()).toBe(true)

    await wrapper.get('[data-testid="return-tab-purchase"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('PR-051')
    expect(wrapper.text()).not.toContain('SR-061')
    expect(calls.some((call) => call.path === '/api/v1/warehouse/receipts?page=1&page_size=100&status=verified')).toBe(true)
  })

  it('reloads the matching dataset when the route mode prop changes', async () => {
    const calls = stubApi({ salesReturns: [salesReturn] })
    const wrapper = mount(ReturnPage, { props: { mode: 'purchase' }, global: globals })
    await flushPromises()
    expect(wrapper.text()).toContain('PR-051')

    await wrapper.setProps({ mode: 'sales' })
    await flushPromises()

    expect(calls.some((call) => call.path.startsWith('/api/v1/sales/returns'))).toBe(true)
    expect(wrapper.text()).toContain('SR-061')
    expect(wrapper.text()).not.toContain('PR-051')
  })

  it('registers both return routes in the real router with the right permission and component', async () => {
    const { router } = await import('../src/router')
    const purchase = router.resolve('/purchase/returns')
    const sales = router.resolve('/sales/returns')

    expect(purchase.matched).toHaveLength(1)
    expect(sales.matched).toHaveLength(1)
    expect(purchase.meta.requiredPermission).toBe('purchase.view')
    expect(sales.meta.requiredPermission).toBe('sales.view')

    // 路由懒加载必须真正解析到退货页组件，避免「有路由无页面」
    const lazy = purchase.matched[0].components?.default as (() => Promise<unknown>) | undefined
    expect(typeof lazy).toBe('function')
    const loaded = await lazy!()
    const component = (loaded as { default?: { __name?: string } })?.default
    expect(component).toBeTruthy()
    expect(String(component?.__name)).toContain('ReturnPage')
  })

  it('keeps sidebar entries pointing at routes that actually resolve', async () => {
    const { router } = await import('../src/router')
    const { navGroups } = await import('../src/layers/common/ui/app-shell/navigation')
    const items = navGroups.flatMap((group) => group.items)
    const returns = items.filter((item) => /^\/(purchase|sales)\/returns$/.test(item.to))

    // 退货出口必须是两条独立菜单项，且与仓库退库（/warehouse/returns）区分开
    expect(returns.map((item) => item.to).sort()).toEqual(['/purchase/returns', '/sales/returns'])
    expect(items.some((item) => item.to === '/warehouse/returns')).toBe(true)
    for (const item of returns) {
      expect(item.label).toBeTruthy()
      expect(router.resolve(item.to).matched).toHaveLength(1)
    }
  })
})
