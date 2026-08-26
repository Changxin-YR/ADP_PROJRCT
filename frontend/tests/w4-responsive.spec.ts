import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

import { ApiError, errorText, isNetworkError, submitErrorText } from '../src/layers/common/api/errors'
import { createApiClient } from '../src/layers/common/api/client'
import { useSubmitGuard } from '../src/layers/common/ui/useSubmitGuard'
import DataTablePage from '../src/layers/common/ui/DataTablePage.vue'
import WorkbenchDashboardPage from '../src/layers/product/workbench/WorkbenchDashboardPage.vue'

const { getWorkbenchSummary, getWorkItems, getNotifications, listPonds, transitionWorkItem, updateNotification } = vi.hoisted(() => ({
  getWorkbenchSummary: vi.fn(),
  getWorkItems: vi.fn(),
  getNotifications: vi.fn(),
  listPonds: vi.fn(),
  transitionWorkItem: vi.fn(),
  updateNotification: vi.fn(),
}))
vi.mock('../src/layers/features/workbench/workbench.service', () => ({
  getWorkbenchSummary,
  getWorkItems,
  getNotifications,
  listPonds,
  transitionWorkItem,
  updateNotification,
}))

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body, headers: { get: () => null } }
}

describe('W4 错误文案（BUG-006 前端 / BUG-M4-10）', () => {
  it('errorText 直接展示 ApiError 中文消息，不回退英文', () => {
    expect(errorText(new ApiError('DUPLICATE_CODE', '编码已存在，请更换后重试', 409), 'fallback')).toBe('编码已存在，请更换后重试')
    expect(errorText(new Error('boom'), '兜底文案')).toBe('boom')
    expect(errorText(null, '兜底文案')).toBe('兜底文案')
  })

  it('isNetworkError 识别网络层失败', () => {
    expect(isNetworkError(new ApiError('NETWORK_ERROR', '网络连接失败，请检查网络后重试', 0))).toBe(true)
    expect(isNetworkError(new ApiError('VALIDATION_ERROR', '参数错误', 400))).toBe(false)
  })

  it('submitErrorText 弱网时提示内容已保留', () => {
    expect(submitErrorText(new ApiError('NETWORK_ERROR', '网络连接失败，请检查网络后重试', 0), '保存失败')).toBe('提交失败，内容已保留，可重试')
    expect(submitErrorText(new ApiError('VALIDATION_ERROR', '面积必须大于 0', 400), '保存失败')).toBe('面积必须大于 0')
  })
})

describe('W4 API 客户端（500 映射 / 无英文 Failed to fetch / 防重复提交）', () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('/api/v1/auth/csrf')) return jsonResponse({ code: 'OK', message: 'ok', data: { csrf_token: 'test-token' } })
      throw new TypeError('Failed to fetch')
    })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('网络层失败统一为中文，绝不透传 Failed to fetch', async () => {
    const api = createApiClient()
    await expect(api.post('/api/v1/whatever', {})).rejects.toMatchObject({ code: 'NETWORK_ERROR', message: '网络连接失败，请检查网络后重试', status: 0 })
  })

  it('500 展示"服务器暂时无法处理请求（request_id）"', async () => {
    fetchMock.mockReset()
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('/api/v1/auth/csrf')) return jsonResponse({ code: 'OK', message: 'ok', data: { csrf_token: 'test-token' } })
      return jsonResponse({ code: 'INTERNAL_ERROR', message: '服务器暂时无法处理请求', request_id: 'req-abc-123', data: null }, 500)
    })
    const api = createApiClient()
    await expect(api.post('/api/v1/broken', {})).rejects.toMatchObject({
      code: 'INTERNAL_ERROR',
      status: 500,
      message: '服务器暂时无法处理请求（req-abc-123）',
    })
  })

  it('后端中文业务消息直接透传（WEAK_PASSWORD 等）', async () => {
    fetchMock.mockReset()
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('/api/v1/auth/csrf')) return jsonResponse({ code: 'OK', message: 'ok', data: { csrf_token: 'test-token' } })
      return jsonResponse({ code: 'WEAK_PASSWORD', message: '密码过弱：请避免连续或重复字符', request_id: 'req-1', data: null }, 400)
    })
    const api = createApiClient()
    await expect(api.post('/api/v1/auth/register', { password: '12345678' })).rejects.toMatchObject({ code: 'WEAK_PASSWORD', message: '密码过弱：请避免连续或重复字符' })
  })

  it('相同路径+请求体的写请求在途时复用同一 Promise（连点仅发一次请求）', async () => {
    let postCalls = 0
    fetchMock.mockReset()
    fetchMock.mockImplementation(async (url: string) => {
      if (String(url).includes('/api/v1/auth/csrf')) return jsonResponse({ code: 'OK', message: 'ok', data: { csrf_token: 'test-token' } })
      postCalls += 1
      await new Promise((resolve) => setTimeout(resolve, 30))
      return jsonResponse({ code: 'OK', message: 'ok', request_id: 'r', data: { record: { id: 1 } } })
    })
    const api = createApiClient()
    const payload = { name: '塘口A', code: 'P-001' }
    const results = await Promise.all(Array.from({ length: 10 }, () => api.post('/api/v1/master-data/ponds', payload)))
    expect(postCalls).toBe(1)
    expect(results.every((item) => (item as { record: { id: number } }).record.id === 1)).toBe(true)
  })
})

describe('W4 useSubmitGuard 防重复提交', () => {
  it('busy 期间重复调用被忽略', async () => {
    const { busy, run } = useSubmitGuard()
    let calls = 0
    const task = async () => { calls += 1; await new Promise((resolve) => setTimeout(resolve, 20)); return calls }
    const [first, second] = await Promise.all([run(task), run(task)])
    expect(first).toBe(1)
    expect(second).toBeUndefined()
    expect(calls).toBe(1)
    expect(busy.value).toBe(false)
  })
})

describe('W4 DataTablePage 移动卡片模式', () => {
  const columns = [
    { key: 'name', label: '名称', type: 'title' as const, sub: 'code' },
    { key: 'status_label', label: '状态', type: 'badge' as const, tones: { 待处理: 'amber' as const } },
    { key: 'quantity', label: '数量', type: 'number' as const },
    { key: 'unit', label: '单位' },
  ]
  const rows = [
    { id: 1, name: '饲料 A', code: 'F-001', status_label: '待处理', quantity: 120, unit: '袋', allowed_actions: ['handle'] },
    { id: 2, name: '饲料 B', code: 'F-002', status_label: '已处理', quantity: 0, unit: '袋', allowed_actions: [] },
  ]

  it('渲染卡片列表，标题/徽标/关键字段前置', () => {
    const wrapper = mount(DataTablePage, {
      props: { title: '库存预警', columns, rows },
      global: { stubs: { AppShell: { template: '<div><slot /></div>' }, RouterLink: { template: '<a><slot /></a>' } } },
    })
    const cards = wrapper.findAll('.table-card')
    expect(cards).toHaveLength(2)
    const first = cards[0]
    expect(first.get('.table-card__title strong').text()).toBe('饲料 A')
    expect(first.get('.table-card__title small').text()).toBe('F-001')
    expect(first.findAll('.table-card__badges .status-badge')).toHaveLength(1)
    const labels = first.findAll('.table-card__fields dt').map((node) => node.text())
    expect(labels).toEqual(['数量', '单位'])
    expect(first.find('footer .table-actions').exists()).toBe(true)
  })

  it('空数据时展示空态文案', () => {
    const wrapper = mount(DataTablePage, {
      props: { title: '库存预警', columns, rows: [], emptyText: '当前没有库存预警' },
      global: { stubs: { AppShell: { template: '<div><slot /></div>' }, RouterLink: { template: '<a><slot /></a>' } } },
    })
    expect(wrapper.find('.data-table-cards .table-empty').text()).toBe('当前没有库存预警')
  })

  it('记录操作按钮防双击：点击后短暂锁定', async () => {
    const wrapper = mount(DataTablePage, {
      props: { title: '库存预警', columns, rows },
      global: { stubs: { AppShell: { template: '<div><slot /></div>' }, RouterLink: { template: '<a><slot /></a>' } } },
    })
    const button = wrapper.find('footer .table-action-btn')
    button.trigger('click')
    expect(wrapper.emitted('action')).toHaveLength(1)
    button.trigger('click')
    expect(wrapper.emitted('action')).toHaveLength(1)
    await new Promise((resolve) => setTimeout(resolve, 650))
    button.trigger('click')
    expect(wrapper.emitted('action')).toHaveLength(2)
  })
})

describe('W4 工作台待办超时提示（BUG-003 硬编码移除）', () => {
  const summary = {
    date_label: '2026-08-16',
    kpis: { ponds: 5, active_batches: 2, current_stock: 12000, todo_open: 4 },
    pond_status: [], todos: [], alerts: [], recent_batches: [],
  }
  function mountPage(workItems: Array<{ overdue?: boolean }>, rejectItems = false) {
    getWorkbenchSummary.mockResolvedValue(summary)
    if (rejectItems) getWorkItems.mockRejectedValue(new Error('403'))
    else getWorkItems.mockResolvedValue({ items: workItems, total: workItems.length })
    const wrapper = mount(WorkbenchDashboardPage, {
      global: { stubs: { AppShell: { template: '<div><slot /></div>' }, RouterLink: { template: '<a><slot /></a>' } } },
    })
    return wrapper
  }

  it('按工作项接口真实统计超时数量', async () => {
    const wrapper = mountPage([{ overdue: true }, { overdue: false }, { overdue: true }])
    await flushPromises(); await nextTick()
    expect(wrapper.text()).toContain('其中 2 项已超过处理时限')
    expect(wrapper.text()).not.toContain('其中 1 项已超过处理时限')
  })

  it('无超时待办时显示中性提示', async () => {
    const wrapper = mountPage([{ overdue: false }])
    await flushPromises(); await nextTick()
    expect(wrapper.text()).toContain('暂无超过处理时限的待办')
  })

  it('工作项接口不可用时不再显示硬编码数字', async () => {
    const wrapper = mountPage([], true)
    await flushPromises(); await nextTick()
    expect(wrapper.text()).toContain('待办时限以列表为准')
    expect(wrapper.text()).not.toContain('其中 1 项已超过处理时限')
  })
})
