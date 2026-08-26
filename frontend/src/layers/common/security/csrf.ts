let cachedToken: string | null = null

export async function getCsrfToken(): Promise<string> {
  if (cachedToken) return cachedToken
  const response = await fetch('/api/v1/auth/csrf', { credentials: 'include' })
  const body = await response.json() as { data?: { csrf_token?: string } }
  if (!response.ok || !body.data?.csrf_token) throw new Error('CSRF Token 获取失败')
  cachedToken = body.data.csrf_token
  return cachedToken
}

export function clearCsrfToken(): void {
  cachedToken = null
}
