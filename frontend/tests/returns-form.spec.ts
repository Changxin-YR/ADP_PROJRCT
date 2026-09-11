import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import ReturnPage from '../src/layers/product/returns/ReturnPage.vue'
import { globals, stubApi } from './returns-fixtures'

/**
 * 退货登记表单的后端字段契约与错误分支。
 * 请求体只允许出现 return_store.create_return 真正读取的列；
 * amount / payable_id / receivable_id 由后端按来源单据计算，前端提交即错。
 */

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  window.localStorage.clear()
})

describe('return form contract and error branches', () => {
  it('posts the exact purchase_return field contract the backend reads', async () => {
    const calls = stubApi()
    const wrapper = mount(ReturnPage, { props: { mode: 'purchase' }, global: globals })
    await flushPromises()

    await wrapper.get('.primary-action').trigger('click')
    await wrapper.get('#return-code').setValue('PR-052')
    await wrapper.get('#return-name').setValue('饲料退货第二批')
    await wrapper.get('#return-source_receipt_id').setValue('88')
    await wrapper.get('#return-quantity').setValue('12')
    await wrapper.get('#return-reason').setValue('到货变质，退回供应商')
    await wrapper.get('[data-testid="return-save"]').trigger('click')
    await flushPromises()

    const created = calls.find((call) => call.method === 'POST' && call.path === '/api/v1/purchase/returns')
    expect(created).toBeTruthy()
    expect(created!.body).toEqual({
      code: 'PR-052', name: '饲料退货第二批', source_receipt_id: 88, quantity: 12,
      reason: '到货变质，退回供应商',
      // 后端强制 warehouse_id/material_id/inventory_lot_id 与来源入库单一致，由来源自动带出
      warehouse_id: 3, material_id: 8, inventory_lot_id: 12,
    })
    // amount / payable_id 由后端按来源单价与应付计算，前端不得自行提交
    expect((created!.body as Record<string, unknown>).amount).toBeUndefined()
    expect((created!.body as Record<string, unknown>).payable_id).toBeUndefined()
  })

  it('posts the sales_return field contract including refund_amount', async () => {
    const calls = stubApi()
    const wrapper = mount(ReturnPage, { props: { mode: 'sales' }, global: globals })
    await flushPromises()

    await wrapper.get('.primary-action').trigger('click')
    await wrapper.get('#return-code').setValue('SR-062')
    await wrapper.get('#return-name').setValue('客户退货第二批')
    await wrapper.get('#return-source_delivery_id').setValue('77')
    await wrapper.get('#return-quantity').setValue('5')
    await wrapper.get('#return-refund_amount').setValue('130')
    await wrapper.get('#return-reason').setValue('规格不符')
    await wrapper.get('[data-testid="return-save"]').trigger('click')
    await flushPromises()

    const created = calls.find((call) => call.method === 'POST' && call.path === '/api/v1/sales/returns')
    expect(created).toBeTruthy()
    expect(created!.body).toEqual({
      code: 'SR-062', name: '客户退货第二批', source_delivery_id: 77,
      quantity: 5, refund_amount: 130, reason: '规格不符',
    })
    expect((created!.body as Record<string, unknown>).receivable_id).toBeUndefined()
  })

  it('drives the source document from a verified dropdown instead of a typed id', async () => {
    const calls = stubApi()
    const wrapper = mount(ReturnPage, { props: { mode: 'purchase' }, global: globals })
    await flushPromises()

    expect(calls.some((call) => call.path === '/api/v1/warehouse/receipts?page=1&page_size=100&status=verified')).toBe(true)
    await wrapper.get('.primary-action').trigger('click')
    const select = wrapper.get('#return-source_receipt_id')
    expect(select.element.tagName).toBe('SELECT')
    expect(select.text()).toContain('IN-088')
    expect(select.text()).toContain('LOT-2026-01')
    // 来源单据不允许手填 ID
    expect(wrapper.find('#return-source_receipt_id[type="text"]').exists()).toBe(false)
    await select.setValue('88')
    expect(wrapper.get('[data-testid="return-source-hint"]').text()).toContain('可退 100')
  })

  it('shows an explicit error and no demo rows when the returns API is unavailable', async () => {
    stubApi({ failStatus: 503 })
    const wrapper = mount(ReturnPage, { props: { mode: 'purchase' }, global: globals })
    await flushPromises()

    const alert = wrapper.get('[role="alert"]').text()
    expect(alert).toContain('退货数据加载失败')
    expect(wrapper.text()).not.toContain('PR-051')
    expect(wrapper.text()).not.toContain('饲料变质退货')
  })

  it('surfaces a 403 on write while keeping the loaded list intact', async () => {
    const calls = stubApi({ failStatus: 403, failPaths: ['/submit'] })
    const wrapper = mount(ReturnPage, { props: { mode: 'purchase' }, global: globals })
    await flushPromises()

    expect(wrapper.text()).toContain('PR-051')
    await wrapper.get('[data-testid="return-action-submit"]').trigger('click')
    await wrapper.get('[data-testid="return-confirm"]').trigger('click')
    await flushPromises()

    expect(calls.some((call) => call.path === '/api/v1/purchase/returns/51/submit')).toBe(true)
    expect(wrapper.get('[role="alert"]').text()).toContain('当前账号没有采购退货权限')
    // 列表仍显示服务端真实数据，没有被静态假数据替换
    expect(wrapper.text()).toContain('PR-051')
  })
})
