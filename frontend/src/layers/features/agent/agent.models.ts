export type AgentMessageRole = 'user' | 'assistant' | 'system'

/** 确认卡片/完成提示里的一行「字段名 → 值」，一律是中文。 */
export interface AgentChangeRow {
  label: string
  value: string
}

export interface AgentConfirmation {
  id: number
  token: string
  tool_name: string
  summary: string
  arguments: Record<string, unknown>
  risk: string
  expires_at: string
  conversation_id: string
  request_id: string
  /** 后端通俗化契约（可选）：影响对象、表单化后的填写内容、风险等级。 */
  target?: string
  changes?: AgentChangeRow[]
  risk_level?: string
}

export interface AgentTurnHistoryItem {
  role: AgentMessageRole
  text: string
}

export interface AgentStreamChunk {
  type: 'status' | 'delta' | 'result' | 'error'
  text?: string
  tool?: string
  data?: AgentTurnResult
  code?: string
  message?: string
  status?: number
}

export interface AgentTurnContext {
  contextPath?: string
  history?: AgentTurnHistoryItem[]
}

export interface AgentClarification {
  question: string
  options?: string[]
  allow_free_text?: boolean
}

/** 写操作已经直接落地时的业务化描述（后端 direct 模式返回）。 */
export interface AgentExecution {
  title: string
  detail?: string
  summary?: string
  rows_changed?: number
  changes?: AgentChangeRow[]
}

export type AgentTurnKind = 'assistant' | 'success' | 'executed' | 'confirmation_required' | 'human_only' | 'clarification'

export interface AgentTurnResult {
  kind: AgentTurnKind
  /** 后端始终给一句或多句人话，前端优先渲染它。 */
  message?: string
  data?: unknown
  execution?: AgentExecution
  confirmation?: AgentConfirmation
  clarification?: AgentClarification
  request_id?: string
  conversation_id?: string
  session_id?: string
  status?: number
}
