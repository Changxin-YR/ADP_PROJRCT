import { describe, expect, it } from 'vitest'
import { formatNumber, humanizeToolName, labelOf, sanitizeTechnical } from '../src/layers/features/agent/agent.phrasing'
import { changeRows, humanTextBlock, humanizeConfirmation, humanizeTurn, summarizeData } from '../src/layers/features/agent/agent.humanize'
import type { AgentConfirmation, AgentTurnResult } from '../src/layers/features/agent/agent.models'

/** 正文里不该出现的痕迹：JSON 结构、英文标识符、未翻译的占位。 */
function leaks(text: string): string[] {
  return ['{', '}', '"', 'undefined', 'null', 'NaN'].filter((token) => text.includes(token))
}

function confirmation(overrides: Partial<AgentConfirmation> = {}): AgentConfirmation {
  return {
    id: 1,
    token: 'once',
    tool_name: 'master_data.create_record',
    summary: '',
    arguments: {},
    risk: '',
    expires_at: '',
    conversation_id: 'c-1',
    request_id: 'req-1',
    ...overrides,
  }
}

describe('agent phrasing', () => {
  it('maps common field names to Chinese and never echoes snake_case', () => {
    expect(labelOf('pond_code')).toBe('塘口编码')
    expect(labelOf('batch_code')).toBe('批次编号')
    expect(labelOf('weight_kg')).toBe('重量（kg）')
    expect(labelOf('happened_at')).toBe('发生时间')
    expect(labelOf('status_text')).toBe('状态')
    expect(labelOf('')).toBe('内容')
    expect(labelOf('stock_quantity_source')).toBe('库存数量来源')
    expect(labelOf('weird_field_name')).not.toContain('_')
  })

  it('formats numbers and times for reading', () => {
    expect(formatNumber(1200)).toBe('1,200')
    expect(formatNumber(12.5)).toBe('12.5')
  })

  it('strips tool names, API paths, HTTP verbs, tracking ids and status codes', () => {
    const text = sanitizeTechnical('调用 adp_query / POST /api/v1/master-data/ponds 时 request_id=req_abc123 失败，HTTP 500，status=pending')
    expect(text).toContain('新增塘口档案')
    expect(text).toContain('状态：待确认')
    for (const token of ['adp_query', '/api/v1', 'POST', 'request_id', 'req_abc123', 'HTTP', '500', 'status=pending']) {
      expect(text).not.toContain(token)
    }
  })

  it('turns a raw JSON blob into Chinese key/value wording', () => {
    const text = sanitizeTechnical('结果：{"pond_code":"TK-001","quantity":120}')
    expect(text).toContain('塘口编码：TK-001')
    expect(text).toContain('数量：120')
    expect(leaks(text)).toEqual([])
  })

  it('names actions from tool names with or without a resource argument', () => {
    expect(humanizeToolName('api.production_create_post_api_v1_production_resource')).toBe('新增生产记录')
    expect(humanizeToolName('api.cost_create_entry_post_api_v1_cost_entries')).toBe('新增成本分录')
    expect(humanizeToolName('master_data.list_records')).toContain('查询')
    expect(humanizeToolName('api.some_unknown_operation')).not.toContain('api.')
  })
})

describe('agent humanize', () => {
  it('summarizes a list as 共 N 条 plus one line per record', () => {
    const items = Array.from({ length: 12 }, (_, index) => ({ pond_name: `${index + 1}号塘`, pond_code: `TK-00${index + 1}` }))
    const view = summarizeData({ items, total: 12 })
    expect(view.headline).toBe('共 12 条')
    expect(view.lines[0]).toBe('1. 「1号塘」，塘口编码 TK-001')
    expect(view.lines).toHaveLength(6)
    expect(view.lines[5]).toBe('（共 12 条，上面显示前 5 条）')
    expect(leaks(humanTextBlock(view))).toEqual([])
  })

  it('summarizes a plain object as a Chinese key/value list', () => {
    const view = summarizeData({ pond_code: 'TK-001', quantity: 120, happened_at: '2026-01-01T08:30:00', request_id: 'req-1' })
    expect(view.headline).toBe('操作已完成')
    expect(view.lines).toEqual(['塘口编码：TK-001', '数量：120', '发生时间：2026-01-01 08:30'])
    expect(leaks(humanTextBlock(view))).toEqual([])
  })

  it('falls back to a single plain sentence for unrecognizable data', () => {
    const view = summarizeData(null, '新增投喂记录')
    expect(view.headline).toBe('新增投喂记录已完成')
    expect(view.lines).toEqual([])
    expect(summarizeData(true).headline).toBe('操作已完成')
    expect(leaks(humanTextBlock(summarizeData({ nested: { deep: { deeper: [1, 2, 3] } } })))).toEqual([])
  })

  it('turns arguments into Chinese rows and drops tracking fields', () => {
    const rows = changeRows({ payload: { pond_code: 'TK-001', quantity: 120 }, request_id: 'req-1', expected_version: 3, note: '' })
    expect(rows).toEqual([
      { label: '塘口编码', value: 'TK-001' },
      { label: '数量', value: '120' },
    ])
  })

  it('renders an executed write from execution.title/detail when message is missing', () => {
    const result: AgentTurnResult = {
      kind: 'executed',
      execution: {
        title: '新增投喂记录',
        detail: '新增投喂记录完成：塘口「一号塘」，120 kg。',
        changes: [{ label: '塘口', value: '一号塘' }],
        rows_changed: 1,
      },
      request_id: 'req-1',
    }
    const view = humanizeTurn(result)
    expect(view.headline).toBe('新增投喂记录完成：塘口「一号塘」，120 kg。')
    expect(view.lines).toEqual(['塘口：一号塘'])
    expect(leaks(humanTextBlock(view))).toEqual([])
  })

  it('prefers the backend message and never shows request_id', () => {
    const view = humanizeTurn({ kind: 'success', message: '一号塘已投喂 120 kg', data: { id: 1 }, request_id: 'req-abc' })
    expect(view.headline).toBe('一号塘已投喂 120 kg')
    expect(humanTextBlock(view)).not.toContain('req-abc')
  })

  it('keeps read results human even when the backend sends only data', () => {
    const view = humanizeTurn({ kind: 'success', data: { items: [{ pond_name: '一号塘', quantity: 1200 }], total: 1 } })
    expect(view.headline).toBe('共 1 条')
    expect(view.lines[0]).toContain('「一号塘」')
    expect(view.lines[0]).toContain('数量 1,200')
  })

  it('uses the backend confirmation contract when it is present', () => {
    const view = humanizeConfirmation(confirmation({
      summary: '新增投喂记录',
      target: '一号塘',
      changes: [{ label: '塘口', value: '一号塘' }, { label: '数量', value: '120 kg' }],
      arguments: { request_id: 'req-1' },
    }))
    expect(view.title).toBe('新增投喂记录')
    expect(view.target).toBe('一号塘')
    expect(view.rows).toEqual([{ label: '塘口', value: '一号塘' }, { label: '数量', value: '120 kg' }])
  })

  it('derives the affected object when the backend target only repeats the action', () => {
    const view = humanizeConfirmation(confirmation({
      tool_name: 'api.production_create_post_api_v1_production_resource',
      summary: '新增投喂记录',
      target: '新增投喂记录',
      arguments: { resource: 'feed-logs', pond_code: 'TK-001' },
      changes: [{ label: '对象类型', value: '投喂记录' }, { label: '塘口编码', value: 'TK-001' }],
    }))
    expect(view.title).toBe('新增投喂记录')
    expect(view.target).toBe('TK-001')
  })

  it('rebuilds a readable confirmation when the backend only sends legacy fields', () => {
    const view = humanizeConfirmation(confirmation({
      tool_name: 'api.production_create_post_api_v1_production_resource',
      summary: 'api.production_create_post_api_v1_production_resource',
      arguments: { resource: 'feed-logs', pond_code: 'TK-001', request_id: 'req-1', expected_version: 2 },
      risk: '该操作会修改业务数据，确认后才会执行',
      expires_at: '2099-01-01T00:00:00',
    }))
    expect(view.title).toBe('新增投喂记录')
    expect(view.target).toBe('TK-001')
    expect(view.rows).toEqual([{ label: '对象类型', value: '投喂记录' }, { label: '塘口编码', value: 'TK-001' }])
    expect(view.expiresAt).toContain('2099-01-01 00:00')
    expect(view.risk).not.toContain('业务数据')
    expect(leaks(`${view.title}${view.target}${view.risk}${view.detail}`)).toEqual([])
  })

  it('describes high risk operations without jargon', () => {
    const view = humanizeConfirmation(confirmation({
      tool_name: 'api.admin_update_role_permissions_put_api_v1_admin_roles_permissions',
      risk: '该操作会修改账号、角色或权限等高风险管理数据',
      risk_level: 'high',
    }))
    expect(view.risk).toContain('高风险')
    expect(view.risk).toContain('确认执行')
    expect(view.title).toContain('角色')
  })

  it('never leaks JSON, paths or tracking ids for hostile inputs', () => {
    const nasty = [
      '{"kind":"success","data":{"items":[{"pond_code":"TK-001"}]}}',
      '{"a": 1, "b": [1,2,3]}',
      '{"bad json": ',
      '{"nested":{"deep":{"deeper":{"x":1}}}}',
      '{}',
      '[]',
      'request_id=abc123, session_id=xyz',
      'POST /api/v1/production/feed-logs 失败了',
      'status=pending',
      'adp_mutation master_data.create_record',
    ]
    for (const input of nasty) {
      const shown = humanTextBlock(humanizeTurn({ kind: 'assistant', message: input }))
      expect(shown.length, input).toBeGreaterThan(0)
      for (const text of [sanitizeTechnical(input), shown]) {
        for (const leak of ['{', '}', '"', 'request_id', 'session_id', '/api/v1', 'POST', 'status=', 'adp_mutation', 'adp_query']) {
          expect(text, `${input} -> ${text}`).not.toContain(leak)
        }
      }
    }
  })

  it('tells the user a confirmation is pending in plain words', () => {
    const view = humanizeTurn({ kind: 'confirmation_required', confirmation: confirmation({ summary: '创建一号塘' }) })
    expect(view.headline).toBe('需要你确认后才会执行：创建一号塘')
    expect(leaks(humanTextBlock(view))).toEqual([])
  })
})
