import { ApiError } from './errors'
import type { ApiResponse } from './models'
import { clearCsrfToken, getCsrfToken } from '../security/csrf'

type RequestOptions = Omit<RequestInit, 'body'> & { body?: unknown }
const stateChangingMethods = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export function createApiClient() {
  // 同一路径+同一请求体的写请求在途时复用同一 Promise：连点/重试不会产生重复 POST（弱网恢复后重提也不重复）
  const inflight = new Map<string, Promise<unknown>>()
  async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const method = (options.method ?? 'GET').toUpperCase()
    const headers = new Headers(options.headers)
    headers.set('Accept', 'application/json')
    if (options.body !== undefined) headers.set('Content-Type', 'application/json')
    if (stateChangingMethods.has(method) && path !== '/api/v1/auth/csrf') headers.set('X-CSRF-Token', await getCsrfToken())
    const dedupeKey = stateChangingMethods.has(method) ? `${method} ${path} ${JSON.stringify(options.body ?? null)}` : ''
    if (dedupeKey && inflight.has(dedupeKey)) return inflight.get(dedupeKey) as Promise<T>
    const promise = doRequest<T>(path, options, method, headers)
    if (dedupeKey) {
      const tracked = promise.then(
        (value) => { inflight.delete(dedupeKey); return value },
        (reason) => { inflight.delete(dedupeKey); throw reason },
      )
      inflight.set(dedupeKey, tracked)
      return tracked
    }
    return promise
  }
  async function doRequest<T>(path: string, options: RequestOptions, method: string, headers: Headers): Promise<T> {
    let response: Response
    try {
      response = await fetch(path, {
        ...options,
        method,
        headers,
        credentials: 'include',
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
      })
    } catch {
      // 网络层失败（断网/弱网/DNS 失败）：统一为中文网络错误，绝不展示浏览器英文 Failed to fetch
      throw new ApiError('NETWORK_ERROR', '网络连接失败，请检查网络后重试', 0)
    }
    let payload: ApiResponse<T>
    try { payload = await response.json() as ApiResponse<T> } catch { throw new ApiError('NETWORK_ERROR', '网络响应无法解析', response.status) }
    if (!response.ok || payload.code !== 'OK') {
      if (payload.code === 'CSRF_INVALID') clearCsrfToken()
      const retryAfterValue = response.headers.get('Retry-After')
      const retryAfter = retryAfterValue && /^\d+$/.test(retryAfterValue) ? Number(retryAfterValue) : undefined
      throw new ApiError(payload.code, errorMessageOf(payload, response.status), response.status, payload.request_id, payload.data, retryAfter)
    }
    return payload.data
  }
  return {
    request,
    get: <T>(path: string) => request<T>(path),
    post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
    put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
    patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
    delete: <T>(path: string, body?: unknown) => request<T>(path, { method: 'DELETE', body }),
  }
}

/** 生成面向用户的错误文案：500 带 request_id；其余情况后端中文消息优先，缺省时按状态码给中文兜底 */
function errorMessageOf(payload: { code?: string; message?: string; request_id?: string }, status: number): string {
  if (status >= 500) return payload.request_id ? `服务器暂时无法处理请求（${payload.request_id}）` : '服务器暂时无法处理请求'
  if (payload.message && payload.message.trim()) return payload.message
  const fallbacks: Record<number, string> = {
    400: '请求参数有误，请检查后重试',
    401: '登录状态已失效，请重新登录',
    403: '当前账号没有权限执行该操作',
    404: '请求的数据不存在',
    409: '数据冲突，请刷新后重试',
    429: '操作过于频繁，请稍后重试',
  }
  return fallbacks[status] ?? '请求失败，请稍后重试'
}

export type ApiClient = ReturnType<typeof createApiClient>
