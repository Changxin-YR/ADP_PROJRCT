/**
 * 措辞层的基础件：值 → 人话、字段名 → 中文、工具名/路径 → 中文动作、去技术标识。
 *
 * 三条硬规则：
 * 1. 绝不原样打印 JSON（大括号、引号、key 名都不能出现在正文里）；
 * 2. 绝不把工具名、HTTP 方法、接口路径、request_id/session_id、状态码当正文；
 * 3. 拿不准就退化成一句「操作已完成」+ 中文键值，不赌运气。
 *
 * 词汇表在 agent.glossary.ts，业务级组装（列表/确认卡片）在 agent.humanize.ts。
 */
import {
  DOMAIN_LABELS, FIELD_LABELS, METHOD_VERBS, OPERATION_VERBS, PATH_ACTIONS, PATH_TAILS,
  RESOURCE_LABELS, TOOL_VERBS, TRACKING_KEYS, VALUE_LABELS, WORD_LABELS,
} from './agent.glossary'

export interface HumanRow { label: string; value: string }

export const EMPTY = '—'
export const MAX_LINE = 160
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/
const ISO_TIME = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/
const NAMESPACES = ['api', 'master_data', 'production', 'warehouse', 'purchase', 'sales', 'cost', 'workbench', 'data_exchange', 'admin', 'auth', 'agent']
const DOTTED_TOKEN = new RegExp(`\\b(?:${NAMESPACES.join('|')})(?:\\.[a-z0-9_]+)+`, 'gi')
const TOOL_WORDS: Record<string, string> = { adp_query: '查询', adp_mutation: '准备写入', adp_ask_user: '向你确认' }
const TOOL_TOKEN = /\b(?:adp_query|adp_mutation|adp_ask_user)\b/gi
const PATH_TOKEN = /(?:(GET|POST|PUT|PATCH|DELETE)\s+)?\/api\/v\d+[^\s，。；、）)"'`]*/gi
const HTTP_METHOD = /(^|[\s（(“"'])(GET|POST|PUT|PATCH|DELETE)(?=[\s)）.,，。:：]|$)/g
const TRACKING_TOKEN = /\b(?:request_id|session_id|conversation_id|trace_id|idempotency[_-]?key|tool_name)\b\s*[:=]?\s*[A-Za-z0-9._:-]*/gi
const UUID_TOKEN = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi
const OPAQUE_ID = /\b(?:req|sess|conv|trace|idem)[_-][A-Za-z0-9]{3,}\b/gi
const STATUS_TOKEN = /\bstatus\s*[:=]\s*"?([a-z_]+)"?/gi
const HTTP_STATUS = /\bHTTP\s*\d{3}\b|\b(?:状态码|status_code)\s*[:=]?\s*\d{3}\b/gi
const SNAKE_TOKEN = /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g
// 响应信封字段：属于结构，不属于业务内容，展示时要下钻或丢弃。
const ENVELOPE_KEYS = new Set(['kind', 'data', 'payload', 'items', 'records', 'rows', 'list', 'results', 'total', 'page', 'page_size', 'has_next', 'meta'])

// --- 数字、时间、字段名 ----------------------------------------------------

export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return EMPTY
  const rounded = Math.round(value * 1000) / 1000
  const [intPart, fracPart] = String(Math.abs(rounded)).split('.')
  const grouped = (intPart ?? '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${rounded < 0 ? '-' : ''}${grouped}${fracPart ? `.${fracPart}` : ''}`
}

export function formatTime(value: string): string {
  const raw = String(value ?? '').trim()
  const dateOnly = ISO_DATE.exec(raw)
  if (dateOnly) return `${dateOnly[1]}-${dateOnly[2]}-${dateOnly[3]}`
  const match = ISO_TIME.exec(raw)
  return match ? `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}` : raw
}

export function trimText(text: string, max = MAX_LINE): string {
  const value = String(text ?? '').trim()
  return value.length > max ? `${value.slice(0, max - 1)}…` : value
}

export function isTracking(key: string): boolean {
  return TRACKING_KEYS.includes(String(key ?? '').toLowerCase())
}

/** 字段英文名 → 中文标签；未知字段退化成「下划线转空格 + 尽量翻译」。 */
export function labelOf(key: string): string {
  const raw = String(key ?? '').trim().replace(/\[\]$/, '')
  if (!raw) return '内容'
  const lower = raw.toLowerCase()
  return FIELD_LABELS[lower] ?? RESOURCE_LABELS[lower] ?? VALUE_LABELS[lower] ?? wordsToChinese(raw)
}

function wordsToChinese(key: string): string {
  const tokens = String(key ?? '').replace(/([a-z0-9])([A-Z])/g, '$1_$2').split(/[_\-\s.]+/).filter(Boolean)
  if (!tokens.length) return String(key ?? '')
  let translated = 0
  const parts = tokens.map((token) => {
    const hit = WORD_LABELS[token.toLowerCase()]
    if (hit) { translated += 1; return hit }
    return token
  })
  return translated === tokens.length ? parts.join('') : parts.join(' ')
}

// --- 值 → 人话 --------------------------------------------------------------

export function humanizeValue(value: unknown, depth = 0): string {
  if (value === null || value === undefined) return EMPTY
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return formatNumber(value)
  if (typeof value === 'string') return humanizeText(value)
  if (Array.isArray(value)) {
    const items = value.slice(0, 6).map((item) => humanizeValue(item, depth + 1)).filter((item) => item && item !== EMPTY)
    if (!items.length) return EMPTY
    return value.length > items.length ? `${items.join('、')} 等 ${value.length} 项` : items.join('、')
  }
  if (typeof value === 'object') {
    if (depth > 2) return '（含多条明细）'
    const parts = Object.entries(value as Record<string, unknown>)
      .filter(([key, item]) => !isTracking(key) && item !== null && item !== undefined && item !== '')
      .slice(0, 6)
      .map(([key, item]) => `${labelOf(key)}：${humanizeValue(item, depth + 1)}`)
    return parts.length ? parts.join('，') : EMPTY
  }
  return String(value)
}

export function humanizeText(text: string): string {
  const raw = String(text ?? '').trim()
  if (!raw) return ''
  const lower = raw.toLowerCase()
  const mapped = VALUE_LABELS[lower] ?? RESOURCE_LABELS[lower]
  if (mapped) return mapped
  if (ISO_DATE.test(raw) || ISO_TIME.test(raw)) return formatTime(raw)
  return sanitizeTechnical(raw)
}

// --- 去技术标识 -------------------------------------------------------------

/** 去掉工具名、路径、HTTP 方法、追踪编号、状态码、英文字段名，只留业务人话。 */
export function sanitizeTechnical(text: string): string {
  if (!text) return ''
  let output = replaceJsonBlobs(String(text))
  output = output.replace(PATH_TOKEN, (match: string, method?: string) => actionTitleFromPathToken(match, method))
  output = output.replace(DOTTED_TOKEN, (match: string) => humanizeToolName(match))
  output = output.replace(TOOL_TOKEN, (match: string) => TOOL_WORDS[match.toLowerCase()] ?? '查询')
  output = output.replace(TRACKING_TOKEN, '')
  output = output.replace(UUID_TOKEN, '')
  output = output.replace(OPAQUE_ID, '')
  output = output.replace(STATUS_TOKEN, (_match: string, value: string) => `状态：${VALUE_LABELS[String(value).toLowerCase()] ?? wordsToChinese(String(value))}`)
  output = output.replace(HTTP_STATUS, '')
  output = output.replace(HTTP_METHOD, (match: string) => (/^\s/.test(match) ? match.slice(0, 1) : ''))
  output = output.replace(SNAKE_TOKEN, (match: string) => labelOf(match.toLowerCase()))
  return tidy(output)
}

function replaceJsonBlobs(text: string): string {
  const start = text.search(/[{\[]/)
  if (start < 0) return text
  const close = Math.max(text.lastIndexOf('}'), text.lastIndexOf(']'))
  const end = close > start ? close + 1 : text.length
  try {
    const parsed: unknown = JSON.parse(text.slice(start, end))
    return `${text.slice(0, start)}${summarizeBlob(parsed)}${text.slice(end)}`
  } catch {
    // 不是合法 JSON 也不能露大括号和 key 名，退化成纯文本。
    return text.replace(/[{}[\]]/g, ' ').replace(/"[^"]{0,40}"\s*[:：]/g, '')
  }
}

function summarizeBlob(value: unknown): string {
  if (Array.isArray(value)) {
    const items = value.slice(0, 3).map((item) => humanizeValue(item)).filter((item) => item && item !== EMPTY)
    return `共 ${value.length} 项${items.length ? `：${items.join('；')}` : ''}`
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    // 信封字段不是业务内容：直接下钻，别把 key 名念给用户听。
    for (const key of ['data', 'payload', 'items', 'records', 'rows', 'results', 'list']) {
      const nested = record[key]
      if (nested && typeof nested === 'object') return summarizeBlob(nested)
    }
    const parts = Object.entries(record)
      .filter(([key, item]) => !isTracking(key) && !ENVELOPE_KEYS.has(key.toLowerCase()) && item !== null && item !== undefined && item !== '')
      .slice(0, 6)
      .map(([key, item]) => `${labelOf(key)}：${humanizeValue(item)}`)
    return parts.length ? parts.join('，') : '操作已完成'
  }
  return humanizeValue(value)
}

function tidy(text: string): string {
  return String(text ?? '')
    // 兜底：任何漏网的大括号/方括号都不能进正文。
    .replace(/[{}[\]]/g, ' ')
    .replace(/[（(]\s*[）)]/g, '')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\s+([，。；、）)])/g, '$1')
    .replace(/([（(])\s+/g, '$1')
    .replace(/[，,]\s*(?=[，。；、])/g, '')
    .replace(/^[\s，,、。;；:：\-–]+/, '')
    .replace(/[\s，,、;；:：]+$/, '')
    .trim()
    .slice(0, 600)
}

// --- 动作名（工具名 / 路径 → 中文动作） -------------------------------------

export function humanizeToolName(tool: string): string {
  const base = String(tool ?? '').trim().split(':')[0] ?? ''
  return base ? actionTitleFromTool(base, {}) : '业务操作'
}

/** 后端没给 summary 时，用工具名 + 参数里的 resource 拼出中文动作名。 */
export function actionTitleFromTool(toolName: string, args: Record<string, unknown> = {}): string {
  const raw = String(toolName ?? '').trim()
  if (!raw) return '业务操作'
  const base = raw.split(':')[0] ?? raw
  const words = base.startsWith('api.') ? base.slice(4) : base
  const tokens = words.split(/[._]/).filter(Boolean)
  const domain = tokens[0] ?? ''
  const code = resourceCodeFromArguments(args) || resourceFromWords(words)
  const label = code ? (RESOURCE_LABELS[code.toLowerCase()] ?? wordsToChinese(code)) : (DOMAIN_LABELS[domain] ?? '业务数据')
  const verb = TOOL_VERBS[base] ?? findVerb(tokens)
  if (verb) return `${verb}${label}`
  const method = /(?:^|[._])(get|post|put|patch|delete)(?:[._]|$)/i.exec(base)
  const methodVerb = method ? METHOD_VERBS[(method[1] ?? '').toUpperCase()] : ''
  return methodVerb ? `${methodVerb}${label}` : `${label}操作`
}

function findVerb(tokens: readonly string[]): string {
  for (const token of tokens) {
    const hit = OPERATION_VERBS[token.toLowerCase()]
    if (hit) return hit
  }
  return ''
}

export function resourceCodeFromArguments(args: unknown): string {
  const source = unwrapArgs(args)
  for (const key of ['resource', 'resource_type', 'resourceType']) {
    const value = source[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}

export function resourceCodeFromPath(path: string): string {
  const segments = String(path ?? '').split('?')[0]?.split('/').filter(Boolean) ?? []
  for (const segment of segments.slice(3)) {
    if (segment.startsWith('{') || /^\d+$/.test(segment) || PATH_TAILS[segment]) continue
    return segment
  }
  return ''
}

function resourceFromWords(text: string): string {
  const haystack = String(text ?? '').toLowerCase()
  let best = ''
  for (const key of Object.keys(RESOURCE_LABELS)) {
    if (key.length < 4) continue
    if ((haystack.includes(key) || haystack.includes(key.replace(/-/g, '_'))) && key.length > best.length) best = key
  }
  return best
}

/** 路径 → 中文动作：先查表（`{xxx}` 按通配匹配），再按末段动词与资源名拼。 */
export function actionTitle(method: string, path: string, resource = ''): string {
  const verb = String(method ?? '').toUpperCase() || 'POST'
  const clean = String(path ?? '').split('?')[0] ?? ''
  const exact = PATH_ACTIONS[`${verb} ${clean}`]
  if (exact) return exact
  for (const [key, title] of Object.entries(PATH_ACTIONS)) {
    const [keyVerb, keyPath] = key.split(' ')
    if (keyVerb === verb && keyPath && pathMatches(keyPath, clean)) return title
  }
  const code = (resource || resourceCodeFromPath(clean)).toLowerCase()
  const label = RESOURCE_LABELS[code] ?? DOMAIN_LABELS[code] ?? '业务数据'
  const tail = clean.replace(/\/+$/, '').split('/').pop() ?? ''
  if (PATH_TAILS[tail]) return `${PATH_TAILS[tail]}${label}`
  return `${METHOD_VERBS[verb] ?? '处理'}${label}`
}

function pathMatches(template: string, path: string): boolean {
  const escaped = template.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`^${escaped.replace(/\\\{[^}]*\\\}/g, '[^/]+')}$`).test(path)
}

function actionTitleFromPathToken(token: string, method?: string): string {
  // token 是整段匹配，可能带 HTTP 方法前缀：先剥掉再查动作表。
  const raw = String(token ?? '').trim().replace(/^(GET|POST|PUT|PATCH|DELETE)\s+/i, '')
  const path = raw.split('?')[0] ?? ''
  const verb = String(method ?? '').toUpperCase()
  if (verb) return actionTitle(verb, path)
  const code = resourceCodeFromPath(path).toLowerCase()
  return RESOURCE_LABELS[code] ?? DOMAIN_LABELS[code] ?? '业务操作'
}

/** 展开 arguments（后端可能把真正的字段放在 payload 里）。 */
export function unwrapArgs(args: unknown): Record<string, unknown> {
  const source = args && typeof args === 'object' && !Array.isArray(args) ? (args as Record<string, unknown>) : {}
  const body = source.payload && typeof source.payload === 'object' && !Array.isArray(source.payload)
    ? (source.payload as Record<string, unknown>)
    : {}
  return { ...body, ...source }
}
