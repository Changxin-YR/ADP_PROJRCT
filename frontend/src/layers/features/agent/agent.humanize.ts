/**
 * 面向业务人员的措辞层（入口）：把智能体一轮结果讲成中文人话。
 *
 * 后端的通俗化契约（可选字段）优先，缺哪块才用 agent.phrasing.ts 的兜底：
 * - `message`：一句或多句人话，永远是首选正文；
 * - `kind: 'executed'` + `execution.{title,detail,changes}`：写操作已直接落地；
 * - `confirmation.{summary,target,changes}`：待确认操作的卡片内容。
 *
 * 出口只有两种形态：`HumanText`（消息气泡）与 `HumanConfirmation`（确认卡片），
 * 任何入口都不会把 JSON、工具名、request_id 原样带出去。
 */
import type { AgentChangeRow, AgentConfirmation, AgentExecution, AgentTurnResult } from './agent.models'
import { CODE_KEYS, COUNT_KEYS, LIST_KEYS, NAME_KEYS, RESOURCE_LABELS, TIME_KEYS } from './agent.glossary'
import {
  EMPTY, actionTitleFromTool, formatNumber, formatTime, humanizeText, humanizeValue, isTracking, labelOf,
  sanitizeTechnical, trimText, unwrapArgs, type HumanRow,
} from './agent.phrasing'

export type { HumanRow } from './agent.phrasing'

export interface HumanText { headline: string; lines: string[]; rows: HumanRow[] }
export interface HumanConfirmation { title: string; detail: string; target: string; rows: HumanRow[]; risk: string; expiresAt: string }

const MAX_ITEMS = 5
const MAX_FIELDS = 8
const MAX_TITLE = 24
const JARGON = /风险管理数据|业务数据|HTTP|\bapi\.|JSON|字段名|接口/

// --- 结果数据 → 结构化中文 --------------------------------------------------

/** 参数 → 「填写内容」中文键值列表（顺带丢掉 payload 包裹、追踪字段与版本号）。 */
export function changeRows(payload: unknown): HumanRow[] {
  const rows: HumanRow[] = []
  const seen = new Set<string>()
  for (const [key, value] of Object.entries(unwrapArgs(payload))) {
    if (seen.has(key) || isTracking(key) || key === 'payload' || key === 'expected_version' || key === 'row_version') continue
    if (value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length)) continue
    const text = humanizeValue(value)
    if (!text || text === EMPTY) continue
    seen.add(key)
    rows.push({ label: labelOf(key), value: trimText(text) })
  }
  return rows
}

function normalizeRows(changes?: AgentChangeRow[]): HumanRow[] {
  if (!Array.isArray(changes)) return []
  const rows: HumanRow[] = []
  for (const row of changes) {
    if (!row || typeof row !== 'object') continue
    const label = trimText(sanitizeTechnical(String(row.label ?? '')), 40)
    const value = trimText(sanitizeTechnical(String(row.value ?? '')))
    if (label && value) rows.push({ label, value })
  }
  return rows
}

function rowsFrom(record: Record<string, unknown>): HumanRow[] {
  const rows: HumanRow[] = []
  for (const [key, value] of Object.entries(record)) {
    if (isTracking(key) || key === 'expected_version' || key === 'row_version' || key === 'payload') continue
    if (value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length)) continue
    const text = humanizeValue(value)
    if (text && text !== EMPTY) rows.push({ label: labelOf(key), value: trimText(text) })
  }
  return rows
}

function matchedEntry(row: Record<string, unknown>, keys: readonly string[]): [string, unknown] | null {
  for (const key of keys) {
    const value = row[key]
    if (value !== null && value !== undefined && value !== '') return [key, value]
  }
  return null
}

/** 一条业务记录的短描述：优先名称，其次编码，再补数量/重量/金额/时间/状态。 */
function describeItem(item: unknown): string {
  if (item === null || item === undefined || typeof item !== 'object' || Array.isArray(item)) {
    return humanizeValue(item) || '一条记录'
  }
  const row = item as Record<string, unknown>
  const parts: string[] = []
  const name = matchedEntry(row, NAME_KEYS)
  if (name) parts.push(`「${humanizeValue(name[1])}」`)
  const groups = [CODE_KEYS, ['quantity', 'stock_quantity', 'count'], ['weight_kg', 'avg_weight_kg'], ['amount', 'total_amount'], TIME_KEYS, ['status_text', 'status']]
  for (const keys of groups) {
    const entry = matchedEntry(row, keys)
    if (entry) parts.push(`${labelOf(entry[0])} ${humanizeValue(entry[1])}`)
  }
  return parts.join('，') || '一条记录'
}

export function summarizeData(data: unknown, title = ''): HumanText {
  if (data === null || data === undefined) return blank(title ? `${title}已完成` : '操作已完成')
  if (typeof data === 'boolean') return blank(data ? `${title || '操作'}已完成` : `${title || '操作'}没有成功，请重试`)
  if (typeof data === 'number') return blank(`${title ? `${title}：` : ''}${formatNumber(data)}`)
  if (typeof data === 'string') return blank(humanizeText(data) || (title ? `${title}已完成` : '操作已完成'))
  if (Array.isArray(data)) return summarizeList(data, title)
  if (typeof data === 'object') {
    const record = data as Record<string, unknown>
    for (const key of LIST_KEYS) {
      const value = record[key]
      if (Array.isArray(value)) return summarizeList(value, title, countOf(record, value.length))
    }
    for (const key of ['record', 'row', 'result']) {
      const value = record[key]
      if (value && typeof value === 'object' && !Array.isArray(value)) return summarizeRecord(value as Record<string, unknown>, title)
    }
    return summarizeRecord(record, title)
  }
  return blank(title ? `${title}已完成` : '操作已完成')
}

/** 列表 → 「共 N 条」+ 每条一句人话（最多 5 条，超出只说清总数）。 */
function summarizeList(items: unknown[], title: string, total?: number): HumanText {
  const prefix = title ? `${title}：` : ''
  if (!items.length) return blank(`${prefix}没有符合条件的记录`)
  const count = typeof total === 'number' && total > items.length ? total : items.length
  const shown = items.slice(0, MAX_ITEMS)
  const lines = shown.map((item, index) => trimText(`${index + 1}. ${describeItem(item)}`))
  if (count > shown.length) lines.push(`（共 ${formatNumber(count)} 条，上面显示前 ${shown.length} 条）`)
  return { headline: `${prefix}共 ${formatNumber(count)} 条`, lines, rows: [] }
}

/** 单个对象 → 「中文字段名：值」列表；认不出内容时只给一句「操作已完成」。 */
function summarizeRecord(record: Record<string, unknown>, title: string): HumanText {
  const rows = rowsFrom(record)
  const headline = title ? `${title}已完成` : '操作已完成'
  if (!rows.length) return blank(headline)
  const shown = rows.slice(0, MAX_FIELDS)
  const lines = shown.map((row) => trimText(`${row.label}：${row.value}`))
  if (rows.length > shown.length) lines.push(`（其余 ${rows.length - shown.length} 项未显示）`)
  return { headline, lines, rows: shown }
}

function countOf(record: Record<string, unknown>, fallback: number): number {
  for (const key of COUNT_KEYS) {
    const value = record[key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string' && /^\d+$/.test(value)) return Number(value)
  }
  return fallback
}

// --- 一轮结果 → 正文 --------------------------------------------------------

export function humanizeExecution(execution?: AgentExecution): HumanText {
  if (!execution) return { headline: '', lines: [], rows: [] }
  const title = trimText(sanitizeTechnical(String(execution.title ?? '')), 40)
  const detail = trimText(sanitizeTechnical(String(execution.detail ?? execution.summary ?? '')))
  const rows = normalizeRows(execution.changes)
  const lines = rows.slice(0, MAX_FIELDS).map((row) => trimText(`${row.label}：${row.value}`))
  let headline = ''
  if (detail) headline = title && !detail.includes(title) ? `${title}：${detail}` : detail
  else if (title) headline = title
  else if (typeof execution.rows_changed === 'number') headline = `已写入 ${formatNumber(execution.rows_changed)} 条记录`
  return { headline: headline || '操作已完成', lines, rows: rows.slice(0, MAX_FIELDS) }
}

function blank(headline: string): HumanText {
  return { headline, lines: [], rows: [] }
}

/** 一轮对话的正文：优先后端 message，其次 execution，最后按 kind 兜底，永不吐 JSON。 */
export function humanizeTurn(result: AgentTurnResult): HumanText {
  const message = result.message ? sanitizeTechnical(String(result.message)) : ''
  if (result.kind === 'executed') {
    const execution = humanizeExecution(result.execution)
    if (message) return { headline: message, lines: execution.lines, rows: execution.rows }
    return execution.headline ? execution : summarizeData(result.data, '操作')
  }
  if (message) return blank(message)
  if (result.kind === 'human_only') return blank('这个操作会改变登录身份或会话，需要你本人在系统页面完成')
  if (result.kind === 'clarification') {
    const question = result.clarification?.question ? sanitizeTechnical(String(result.clarification.question)) : ''
    return blank(question || '需要你补充一点信息后才能继续')
  }
  if (result.kind === 'confirmation_required') {
    return blank(result.confirmation ? `需要你确认后才会执行：${humanizeConfirmation(result.confirmation).title}` : '需要你确认后才会执行')
  }
  if (result.kind === 'assistant') return blank('这次没有可以直接显示的内容，可以换个说法再问我一次')
  return summarizeData(result.data)
}

/** 正文块 → 消息气泡文本（多行用换行分隔，气泡是 pre-wrap）。 */
export function humanTextBlock(view: HumanText): string {
  return [view.headline, ...view.lines].filter((line) => line && line.trim()).join('\n')
}

// --- 确认卡片 → 通俗版 ------------------------------------------------------

/** 确认卡片：中文动作名 + 影响对象 + 填写内容，替代原来的 JSON 展示。 */
export function humanizeConfirmation(confirmation: AgentConfirmation): HumanConfirmation {
  const rawSummary = String(confirmation.summary ?? '').trim()
  const summary = rawSummary ? sanitizeTechnical(rawSummary) : ''
  const derived = actionTitleFromTool(String(confirmation.tool_name ?? ''), confirmation.arguments ?? {})
  // summary 被净化过，说明后端给的是工具名/接口这类技术串：动作名改用工具名 + 参数推。
  const technical = !summary || rawSummary !== summary || summary.length > MAX_TITLE || /[。；;]/.test(summary)
  const title = technical ? derived : trimText(summary, 40)
  const detail = technical && summary && summary !== derived ? trimText(summary, 80) : ''
  const rows = normalizeRows(confirmation.changes)
  const expire = confirmation.expires_at ? formatTime(String(confirmation.expires_at)) : ''
  // 后端可能把 target 也填成动作名（与 summary 相同）：那样它就不是「影响对象」，改用参数推。
  const provided = confirmation.target ? sanitizeTechnical(String(confirmation.target)) : ''
  const providedTarget = provided && provided !== title && provided !== summary ? provided : ''
  return {
    title,
    detail,
    target: trimText(providedTarget || deriveTarget(confirmation.arguments) || '当前账号权限范围内的业务数据', 80),
    rows: (rows.length ? rows : changeRows(confirmation.arguments)).slice(0, MAX_FIELDS),
    risk: confirmationRisk(confirmation),
    expiresAt: expire ? `请在 ${expire} 前确认，超时自动失效` : '',
  }
}

/** 影响对象：优先后端 target，其次从参数里的名称/编码/编号推。 */
export function deriveTarget(args: unknown): string {
  const source = unwrapArgs(args)
  const picks: string[] = []
  for (const key of ['pond_name', 'pond_code', 'batch_code', 'batch_name', 'name', 'title', 'code', 'order_no', 'entry_no', 'doc_no', 'material_name', 'customer_name', 'supplier_name', 'partner_name', 'record_no']) {
    const value = source[key]
    if (typeof value !== 'string' && typeof value !== 'number') continue
    const text = humanizeValue(value)
    if (text && text !== EMPTY && !picks.includes(text)) picks.push(text)
    if (picks.length >= 2) break
  }
  if (picks.length) return picks.join('／')
  const ids: string[] = []
  for (const [key, value] of Object.entries(source)) {
    if (isTracking(key) || !/(^|_)(id|ids)$/.test(key) || value === null || value === undefined || value === '') continue
    ids.push(`${labelOf(key)} ${humanizeValue(value)}`)
    if (ids.length >= 2) break
  }
  if (ids.length) return ids.join('，')
  const code = resourceCodeOf(source)
  return code ? (RESOURCE_LABELS[code.toLowerCase()] ?? '') : ''
}

function resourceCodeOf(source: Record<string, unknown>): string {
  for (const key of ['resource', 'resource_type']) {
    const value = source[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}

function confirmationRisk(confirmation: AgentConfirmation): string {
  const level = String(confirmation.risk_level ?? '').toLowerCase()
  const raw = confirmation.risk ? sanitizeTechnical(String(confirmation.risk)) : ''
  if (level === 'high' || /账号|角色|权限|身份|会话/.test(raw)) {
    return '这会改动账号、角色或权限，属于高风险操作；请先核对影响对象和填写内容，再点「确认执行」'
  }
  if (raw && raw.length <= 60 && !JARGON.test(raw)) return raw
  return '确认后才会真正写入系统，写入记录会留下痕迹；点「取消」不会产生任何改动'
}
