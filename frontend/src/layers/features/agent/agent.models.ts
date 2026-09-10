export type AgentMessageRole = 'user' | 'assistant' | 'system'

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
}

export interface AgentTurnHistoryItem {
  role: AgentMessageRole
  text: string
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

export interface AgentTurnResult {
  kind: 'assistant' | 'success' | 'confirmation_required' | 'human_only' | 'clarification'
  message?: string
  data?: unknown
  confirmation?: AgentConfirmation
  clarification?: AgentClarification
  request_id?: string
  conversation_id?: string
  session_id?: string
  status?: number
}
