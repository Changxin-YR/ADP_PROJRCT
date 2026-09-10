import { createApiClient } from '../../common/api/client'
import { apiUrl } from '../../common/api/base'
import { ApiError } from '../../common/api/errors'
import { getCsrfToken } from '../../common/security/csrf'
import type { AgentStreamChunk, AgentTurnContext, AgentTurnResult } from './agent.models'

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

/** 流式入口：逐块回调，最后返回与非流式一致的 result。 */
export async function sendAgentTurnStream(
  message: string,
  conversationId: string | undefined,
  context: AgentTurnContext,
  onChunk: (chunk: AgentStreamChunk) => void,
): Promise<AgentTurnResult> {
  const response = await fetch(apiUrl('/api/v1/agent/turn/stream'), {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/x-ndjson',
      'X-CSRF-Token': await getCsrfToken(),
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      context_path: context.contextPath,
      history: context.history,
    }),
  })
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => null) as { code?: string; message?: string } | null
    throw new ApiError(payload?.code ?? 'AGENT_STREAM_FAILED', payload?.message ?? '网络连接失败，请检查网络后重试', response.status || 0)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: AgentTurnResult | undefined

  const handleLine = (line: string): void => {
    if (!line.trim()) return
    const parsed = JSON.parse(line) as AgentStreamChunk & { code?: string; message?: string }
    if (parsed.type === 'result') { result = parsed.data; return }
    if (parsed.type === 'error') {
      throw new ApiError(parsed.code ?? 'AGENT_REQUEST_FAILED', parsed.message ?? '请求失败', parsed.status ?? 500)
    }
    if (!parsed.type && typeof parsed.code === 'string') {
      // 不是 NDJSON：可能是被代理改写/旧后端的普通信封响应。
      if (parsed.code !== 'OK') throw new ApiError(parsed.code, parsed.message ?? '请求失败', response.status)
      const data = parsed.data as AgentTurnResult | null | undefined
      // data 为空说明这个地址并没有真正的流式实现，交给调用方回退到 /turn。
      if (!data || typeof data !== 'object') throw new ApiError('AGENT_STREAM_UNAVAILABLE', '流式输出不可用，请稍后重试', 404)
      result = data
      return
    }
    onChunk(parsed)
  }

  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) handleLine(line)
  }
  handleLine(buffer)   // 最后一行可能没有换行符
  if (!result) throw new ApiError('AGENT_PROTOCOL_ERROR', '智能助手这一轮没有返回结果，请重试', 502)
  return result
}

export function confirmAgent(token: string): Promise<AgentTurnResult> {
  return api.post<AgentTurnResult>('/api/v1/agent/confirm', { token })
}

export function cancelAgentConfirmation(confirmationId: number): Promise<{ cancelled: boolean }> {
  return api.post<{ cancelled: boolean }>('/api/v1/agent/cancel', { confirmation_id: confirmationId })
}
