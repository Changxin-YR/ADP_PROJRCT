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

interface CatalogOperation {
  n?: string
  d?: string
  m?: string
  p?: string
  r?: string
  q?: string
  a?: string[]
  f?: string[] | Record<string, string[]>
  rs?: string[]
}

function describeOperations(catalog: string | undefined): string {
  if (!catalog?.trim()) return '必须使用已登记的 ADP 工具名。'
  try {
    const parsed = JSON.parse(catalog) as CatalogOperation[] | { operations?: CatalogOperation[] }
    const operations = Array.isArray(parsed) ? parsed : parsed.operations
    if (!Array.isArray(operations)) throw new Error('catalog must be an array')
    const lines = operations.map((operation) => [
      operation.n,
      operation.d,
      `${operation.m ?? ''} ${operation.p ?? ''}`.trim(),
      operation.r ? `risk=${operation.r}` : '',
      operation.q ? `perm=${operation.q}` : '',
      operation.a ? `parameters=${operation.a.join(',')}` : '',
      describeFields(operation),
    ].filter(Boolean).join(' | '))
    return `必须从已登记的 ADP 工具名中选择，并按对应参数调用（perm= 是该操作需要的权限码）：\n${lines.join('\n')}`
  } catch {
    return '必须从已登记的 ADP 工具名中选择。'
  }
}

function describeFields(operation: CatalogOperation): string {
  const parts: string[] = []
  if (operation.f && typeof operation.f === 'object') {
    if (Array.isArray(operation.f)) {
      if (operation.f.length) parts.push(`payload 字段=${operation.f.join(',')}（! 为必填）`)
    } else {
      for (const [resource, fields] of Object.entries(operation.f)) {
        if (Array.isArray(fields) && fields.length) parts.push(`${resource}: ${fields.join(',')}`)
      }
    }
  }
  if (Array.isArray(operation.rs) && operation.rs.length) parts.push(`resource 可选=${operation.rs.join('/')}`)
  return parts.join(' ')
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
  if (!response.ok) {
    // Keep the gateway error code: the model must quote the real failure instead
    // of inventing a plausible-sounding cause.
    const code = String(body?.code || 'ADP_GATEWAY_ERROR')
    const message = String(body?.message || 'ADP Gateway 请求失败')
    throw new Error(`${code}: ${message}`)
  }
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
    description: '执行 ADP 业务增删改（新增/修改/删除）。按当前登录者权限执行；若网关返回 confirmation_required，必须等待用户确认。',
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

  const askUserDescription = '信息不足、存在歧义或需要用户在多步操作中做决定时，向用户提出一个具体问题并等待回答。调用后必须停止本轮输出，不要猜测参数，也不要用普通文字代替提问。'

  // The panel renders this payload as a question box with clickable options, so
  // the agent asks instead of guessing (and never invents a system failure).
  ctx.tools.register(defineTool({
    name: 'adp_ask_user',
    description: askUserDescription,
    parameters: {
      question: { type: 'string', required: true, description: '用简体中文提出的一个明确问题，说明缺少什么信息或需要用户在什么之间做选择。' },
      options: { type: 'json', description: '2-4 个可点击的候选答案或下一步操作（字符串数组），可为空数组。' },
      allow_free_text: { type: 'boolean', description: '是否允许用户自由输入，默认 true。' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
    },
    async execute(args) {
      const payload = args as { question?: unknown; options?: unknown; allow_free_text?: unknown }
      const question = String(payload?.question ?? '').trim()
      if (!question) throw new Error('question 不能为空')
      const options = Array.isArray(payload?.options)
        ? payload.options.map((item) => String(item)).filter((item) => item.trim()).slice(0, 5)
        : []
      return {
        kind: 'clarification',
        question,
        options,
        allow_free_text: payload?.allow_free_text !== false,
        note: '已向用户提问，请立即停止本轮输出，等待用户回答。',
      } as unknown as JsonValue
    },
  }))
}
