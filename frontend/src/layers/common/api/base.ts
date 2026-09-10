const configuredApiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '')
const publicBasePath = (import.meta.env.BASE_URL ?? '/').replace(/\/+$/, '')
const defaultApiBaseUrl = typeof window !== 'undefined' && window.location.protocol === 'file:'
  ? 'http://127.0.0.1:5001'
  : ''

export function apiUrl(path: string, base = configuredApiBaseUrl || defaultApiBaseUrl): string {
  if (/^https?:\/\//i.test(path)) return path
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  if (!base) return `${publicBasePath}${normalizedPath}`
  const normalizedBase = base.trim().replace(/\/+$/, '')
  return `${normalizedBase}${normalizedPath}`
}
