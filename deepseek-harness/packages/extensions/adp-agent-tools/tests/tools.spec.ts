import { describe, expect, it, vi } from 'vitest'
import { apply } from '../src/index.ts'

function context() {
  const registered: any[] = []
  return {
    registered,
    tools: { register: (tool: unknown) => registered.push(tool) },
    approval: { request: vi.fn(async () => 'rejected') },
  } as any
}

describe('ADP agent tools', () => {
  it('registers only fixed query and mutation tools', () => {
    const ctx = context()
    apply(ctx, { gatewayUrl: 'http://127.0.0.1/api/v1/agent', contextToken: 'short-lived' })
    expect(ctx.registered.map((tool: { name: string }) => tool.name)).toEqual(['adp_query', 'adp_mutation'])
  })

  it('sends mutations to the ADP confirmation gateway', async () => {
    const ctx = context()
    apply(ctx, { gatewayUrl: 'http://127.0.0.1/api/v1/agent', contextToken: 'short-lived' })
    const mutation = ctx.registered[1]
    const original = globalThis.fetch
    let called: { url: string; body: string } | undefined
    globalThis.fetch = (async (input, init) => {
      called = { url: String(input), body: String(init?.body) }
      return new Response(JSON.stringify({ data: { kind: 'confirmation_required' } }), { status: 200 })
    }) as typeof fetch
    try {
      await expect(mutation.execute(
        { operation: 'master_data.create_record', arguments: { resource: 'ponds' } },
        { signal: new AbortController().signal, agent: {}, callId: 'write-1' },
      )).resolves.toEqual({ kind: 'confirmation_required' })
    } finally {
      globalThis.fetch = original
    }
    expect(called?.url).toBe('http://127.0.0.1/api/v1/agent/prepare')
    expect(JSON.parse(called?.body ?? '{}').operation).toBe('master_data.create_record')
  })

  it('declares a profile bundle patch for runtime installation', async () => {
    const manifest = await import('node:fs/promises').then(({ readFile }) => readFile(new URL('../package.json', import.meta.url), 'utf8'))
    expect(JSON.parse(manifest).dsh.bundle.patch).toBe('./cordis.patch.yml')
  })

  it('removes gateway credentials from the child process environment', () => {
    process.env.ADP_AGENT_GATEWAY_URL = 'http://127.0.0.1'
    process.env.ADP_AGENT_CONTEXT_TOKEN = 'short-lived'
    apply(context(), { gatewayUrl: 'http://127.0.0.1/api/v1/agent', contextToken: 'short-lived' })
    expect(process.env.ADP_AGENT_GATEWAY_URL).toBeUndefined()
    expect(process.env.ADP_AGENT_CONTEXT_TOKEN).toBeUndefined()
  })
})
