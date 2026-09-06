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

export interface AgentTurnResult {
  kind: 'assistant' | 'success' | 'confirmation_required' | 'human_only'
  message?: string
  data?: unknown
  confirmation?: AgentConfirmation
  request_id?: string
  conversation_id?: string
  session_id?: string
  status?: number
}
