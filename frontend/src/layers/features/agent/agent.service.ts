import { createApiClient } from '../../common/api/client'
import type { AgentTurnContext, AgentTurnResult } from './agent.models'

const api = createApiClient()

export function sendAgentTurn(
  message: string,
  conversationId?: string,
  context: AgentTurnContext = {},
): Promise<AgentTurnResult> {
  return api.post<AgentTurnResult>('/api/v1/agent/turn', {
    message,
    conversation_id: conversationId,
    context_path: context.contextPath,
    history: context.history,
  })
}

export function confirmAgent(token: string): Promise<AgentTurnResult> {
  return api.post<AgentTurnResult>('/api/v1/agent/confirm', { token })
}

export function cancelAgentConfirmation(confirmationId: number): Promise<{ cancelled: boolean }> {
  return api.post<{ cancelled: boolean }>('/api/v1/agent/cancel', { confirmation_id: confirmationId })
}
