import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import ImportPage from '../src/layers/product/data/ImportPage.vue'
import TemplatePage from '../src/layers/product/data/TemplatePage.vue'


const globals = { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } }
const envelope = (data: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify({
  code: status >= 400 ? 'DATA_EXCHANGE_FAILED' : 'OK', message: status >= 400 ? '服务不可用' : '操作成功', data, request_id: 'exchange-test',
}), { status, headers: { 'Content-Type': 'application/json' } }))

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('governed data exchange pages', () => {
  it('loads versioned templates from the API and downloads the selected workbook', async () => {
    const calls: Array<{ path: string; method: string }> = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input), method = init?.method ?? 'GET'; calls.push({ path, method })
      if (path.endsWith('/templates/materials/download')) return Promise.resolve(new Response(new Blob(['xlsx']), { status: 200, headers: { 'Content-Disposition': 'attachment; filename="materials.xlsx"' } }))
      return envelope({ items: [{ code: 'materials', name: '物料档案', group: '主数据', version: '3.0', fields: [{ key: 'code' }, { key: 'name' }], updated_at: '2026-08-17' }] })
    }))

    const wrapper = mount(TemplatePage, { global: globals })
    await flushPromises()
    expect(calls).toContainEqual({ path: '/api/v1/data-exchange/templates', method: 'GET' })
    expect(wrapper.text()).toContain('3.0')
    expect(wrapper.text()).toContain('物料档案')
    await wrapper.get('[data-testid="template-download-materials"]').trigger('click')
    await flushPromises()
    expect(calls).toContainEqual({ path: '/api/v1/data-exchange/templates/materials/download', method: 'GET' })
  })

  it('uploads the real file, previews validation, and confirms only clean batches', async () => {
    const calls: Array<{ path: string; method: string; body?: BodyInit | null }> = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input), method = init?.method ?? 'GET'; calls.push({ path, method, body: init?.body })
      if (path.includes('/auth/csrf')) return envelope({ csrf_token: 'csrf' })
      if (path.endsWith('/imports/preview')) return envelope({ batch: { id: 8, file_name: 'materials.xlsx', template_name: '物料档案', total_rows: 1, passed_rows: 1, failed_rows: 0, status: 'ready', errors: [], preview_rows: [{ code: 'MAT-8', name: '饲料' }] } }, 201)
      if (path.endsWith('/imports/8/confirm')) return envelope({ batch: { id: 8, status: 'imported', imported_count: 1 } })
      if (path.endsWith('/templates')) return envelope({ items: [{ code: 'materials', name: '物料档案', version: '3.0', group: '主数据', fields: [] }] })
      return envelope({ items: [] })
    }))
    const wrapper = mount(ImportPage, { global: globals })
    await flushPromises()
    await wrapper.get('[data-testid="import-open"]').trigger('click')
    const file = new File(['xlsx-content'], 'materials.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    Object.defineProperty(wrapper.get('[data-testid="import-file"]').element, 'files', { value: [file] })
    await wrapper.get('[data-testid="import-file"]').trigger('change')
    await wrapper.get('[data-testid="import-preview"]').trigger('click')
    await flushPromises()
    const preview = calls.find((call) => call.path.endsWith('/imports/preview'))
    expect(preview?.body).toBeInstanceOf(FormData)
    expect(wrapper.text()).toContain('MAT-8')
    await wrapper.get('[data-testid="import-confirm"]').trigger('click')
    await flushPromises()
    expect(calls).toContainEqual(expect.objectContaining({ path: '/api/v1/data-exchange/imports/8/confirm', method: 'POST' }))
    expect(wrapper.text()).toContain('导入成功')
  })

  it('shows an explicit error and never restores static import rows', async () => {
    vi.stubGlobal('fetch', vi.fn(() => envelope(null, 503)))
    const wrappers = [mount(TemplatePage, { global: globals }), mount(ImportPage, { global: globals })]
    await flushPromises()
    for (const wrapper of wrappers) {
      expect(wrapper.get('[role="alert"]').text()).toContain('数据加载失败')
      expect(wrapper.text()).not.toContain('IMP-20260815-01')
      expect(wrapper.text()).not.toContain('现场台账_0815.xlsx')
    }
  })
})
