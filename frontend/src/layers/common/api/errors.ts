export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly requestId?: string
  readonly data?: unknown
  readonly retryAfter?: number

  constructor(code: string, message: string, status: number, requestId?: string, data?: unknown, retryAfter?: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.requestId = requestId
    this.data = data
    this.retryAfter = retryAfter
  }
}

/** 网络层失败（请求未到达服务器或连接中断），用于弱网提示判断 */
export function isNetworkError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 0 || error.code === 'NETWORK_ERROR')
}

/** 把任意异常转为可直接展示的中文文案（ApiError 消息直接展示，绝不透传英文底层错误） */
export function errorText(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message || fallback
  if (error instanceof Error && error.message) return error.message
  return fallback
}

/** 表单提交失败文案：弱网时提示内容已保留；其余情况直接展示中文业务消息 */
export function submitErrorText(error: unknown, fallback: string): string {
  if (isNetworkError(error)) return '提交失败，内容已保留，可重试'
  return errorText(error, fallback)
}

/** 页面级提示：在固定业务场景前缀后拼接 ApiError 消息；非业务异常回退到场景文案 */
export function messageWithContext(error: unknown, fallback: string): string {
  return error instanceof ApiError ? `${fallback}：${error.message}` : fallback
}
