import { createApiClient } from '../src/layers/common/api/client'

test('reuses a write idempotency key after a network response is lost', async () => {
  const calls: RequestInit[] = []
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    calls.push(init ?? {})
    if (String(input).endsWith('/auth/csrf')) return Promise.resolve(new Response(JSON.stringify({ data: { csrf_token: 'csrf' } }), { status: 200 }))
    if (calls.filter((item) => item.method === 'POST').length === 1) return Promise.reject(new TypeError('offline'))
    return Promise.resolve(new Response(JSON.stringify({ code: 'OK', data: { id: 1 } }), { status: 200 }))
  })
  vi.stubGlobal('fetch', fetchMock)
  const client = createApiClient()

  await expect(client.post('/api/v1/warehouse/receipts', { code: 'IN-1' })).rejects.toThrow('网络连接失败')
  await client.post('/api/v1/warehouse/receipts', { code: 'IN-1' })

  const writes = calls.filter((item) => item.method === 'POST')
  expect(new Headers(writes[0].headers).get('Idempotency-Key')).toBe(new Headers(writes[1].headers).get('Idempotency-Key'))
})
