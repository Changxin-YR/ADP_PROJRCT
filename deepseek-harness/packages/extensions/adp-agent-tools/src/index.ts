import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { JsonValue } from '@deepseek-ai/dsh-util-values'

export const name = 'adp-agent-tools'
export const inject = ['tools']

export interface AdpAgentToolsConfig {
  gatewayUrl: string
  contextToken: string
  operationCatalog?: string
}

function endpoint(config: AdpAgentToolsConfig, path: '/query' | '/prepare'): string {
  let base: URL
  try {
    base = new URL(config.gatewayUrl)
  } catch {
    throw new Error('ADP Gateway 地址无效')
  }
  if (!['http:', 'https:'].includes(base.protocol)) throw new Error('ADP Gateway 只允许 HTTP(S) 地址')
  return `${base.toString().replace(/\/+$/, '')}${path}`
}

function describeOperations(catalog: string | undefined): string {
  if (!catalog?.trim()) return '必须使用已登记的 ADP 工具名。'
  try {
    const operations = JSON.parse(catalog) as Array<{
      n?: string
      d?: string
      m?: string
      p?: string
      r?: string
      a?: string[]
    }>
    if (!Array.isArray(operations)) throw new Error('catalog must be an array')
    const lines = operations.map((operation) => [
      operation.n,
      operation.d,
      `${operation.m ?? ''} ${operation.p ?? ''}`.trim(),
      operation.r ? `risk=${operation.r}` : '',
      operation.a ? `parameters=${operation.a.join(',')}` : '',
    ].filter(Boolean).join(' | '))
    return `必须从已登记的 ADP 工具名中选择，并按对应参数调用：\n${lines.join('\n')}`
  } catch {
    return '必须从已登记的 ADP 工具名中选择。'
  }
}

async function callGateway(
  config: AdpAgentToolsConfig,
  path: '/query' | '/prepare',
  args: { operation: string; arguments: Record<string, unknown> },
  signal: AbortSignal,
): Promise<JsonValue> {
  const response = await fetch(endpoint(config, path), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Agent-Context': config.contextToken,
    },
    body: JSON.stringify(args),
    signal,
  })
  const body = await response.json().catch(() => null) as Record<string, unknown> | null
  if (!response.ok) throw new Error(String(body?.message || 'ADP Gateway 请求失败'))
  return (body?.data ?? body) as JsonValue
}

export function apply(ctx: Context, config: AdpAgentToolsConfig): void {
  // Keep the short-lived gateway credential out of child shell environments.
  if (typeof process !== 'undefined') {
    delete process.env.ADP_AGENT_GATEWAY_URL
    delete process.env.ADP_AGENT_CONTEXT_TOKEN
  }
  const operationDescription = describeOperations(config.operationCatalog)
  ctx.tools.register(defineTool({
    name: 'adp_query',
    description: '查询当前登录用户有权查看的 ADP 数据。',
    parameters: {
      operation: { type: 'string', required: true, description: operationDescription },
      arguments: { type: 'json', required: true, description: '该工具的对象参数。' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
    },
    async execute(args, exec) {
      return callGateway(config, '/query', args as { operation: string; arguments: Record<string, unknown> }, exec.signal)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'adp_mutation',
    description: '准备一个需要登录者确认的 ADP 业务写操作。',
    parameters: {
      operation: { type: 'string', required: true, description: operationDescription },
      arguments: { type: 'json', required: true, description: '该工具的对象参数。' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
    },
    async execute(args, exec) {
      return callGateway(config, '/prepare', args as { operation: string; arguments: Record<string, unknown> }, exec.signal)
    },
  }))
}
