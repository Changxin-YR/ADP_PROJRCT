import { createApiClient } from '../../common/api/client'

const api = createApiClient()

export interface AuditLogRecord {
  id: number
  user_id?: number | null
  actor_name?: string | null
  action: string
  action_code?: string | null
  module_code?: string | null
  object_type: string
  object_id?: number | null
  object_ref?: string | null
  result: string
  detail_json?: unknown
  reason?: string | null
  ip_address?: string | null
  request_id?: string | null
  created_at: string
}

export interface AuditLogList { items: AuditLogRecord[]; page: number; page_size: number; total: number; has_next: boolean }

export function getAuditLogs(query: { action_code?: string; module_code?: string; object_type?: string; result?: string; page?: number; page_size?: number } = {}): Promise<AuditLogList> {
  const params = new URLSearchParams({ page: String(query.page ?? 1), page_size: String(query.page_size ?? 100) })
  for (const [key, value] of Object.entries(query)) if (value !== undefined && value !== '') params.set(key, String(value))
  return api.get(`/api/v1/admin/audit-logs?${params.toString()}`)
}
