import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { clearOfflineDraft, loadOfflineDraft, saveOfflineDraft } from '../src/layers/common/ui/offlineDraft'
import LossPage from '../src/layers/product/ponds-batches/LossPage.vue'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('offline business drafts', () => {
  it('round-trips a draft and supports explicit discard', () => {
    saveOfflineDraft('purchase:orders', { code: 'PO-1', quantity: 12 })
    expect(loadOfflineDraft<Record<string, unknown>>('purchase:orders')?.payload).toEqual({ code: 'PO-1', quantity: 12 })
    clearOfflineDraft('purchase:orders')
    expect(loadOfflineDraft('purchase:orders')).toBeNull()
  })

  it('drops malformed or expired envelopes instead of restoring unsafe data', () => {
    localStorage.setItem('adp:offline-draft:broken', '{bad json')
    expect(loadOfflineDraft('broken')).toBeNull()
    localStorage.setItem('adp:offline-draft:old', JSON.stringify({ version: 1, saved_at: '2020-01-01T00:00:00.000Z', payload: { code: 'OLD' } }))
    expect(loadOfflineDraft('old')).toBeNull()
    expect(localStorage.getItem('adp:offline-draft:old')).toBeNull()
  })

  it('restores a new production form after it is closed and allows discard', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({ code: 'OK', data: { items: [], page: 1, page_size: 20, total: 0, has_next: false } }), { headers: { 'Content-Type': 'application/json' } }))))
    const wrapper = mount(LossPage, { global: { stubs: { AppShell: { template: '<main><slot /></main>' }, Teleport: true } } })
    await flushPromises()
    await wrapper.get('button.primary-action').trigger('click')
    await wrapper.get('#production-code').setValue('LOSS-OFFLINE')
    await wrapper.get('button[aria-label="关闭"]').trigger('click')
    await wrapper.get('button.primary-action').trigger('click')
    expect((wrapper.get('#production-code').element as HTMLInputElement).value).toBe('LOSS-OFFLINE')
    await wrapper.get('[data-testid="production-discard-draft"]').trigger('click')
    expect(loadOfflineDraft('production:losses')).toBeNull()
  })
})
