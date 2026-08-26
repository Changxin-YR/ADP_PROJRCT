import { createApiClient } from '../../common/api/client'
import { ApiError } from '../../common/api/errors'
import type { ApiResponse } from '../../common/api/models'
import { getCsrfToken } from '../../common/security/csrf'
import { createSessionStore } from '../../common/session/session.store'

export interface TemplateField { key: string; label: string; required: boolean; kind: string; example: string }
export interface ExchangeTemplate { code: string; name: string; group: string; version: string; fields: TemplateField[]; importable: boolean; updated_at: string }
export interface ImportError { row: number; column: string; message: string; value?: unknown }
export interface ImportBatch {
  id: number; template_code: string; template_name: string; template_version: string; file_name: string
  total_rows: number; passed_rows: number; failed_rows: number; status: 'invalid' | 'ready' | 'imported' | 'undone'
  errors: ImportError[]; preview_rows: Record<string, unknown>[]; imported_count?: number; created_at?: string
}
export interface Attachment { id: number; original_name: string; storage_name: string; media_type: string; size_bytes: number; created_at?: string }

const api = createApiClient()
export const getExchangeTemplates = () => api.get<{ items: ExchangeTemplate[] }>('/api/v1/data-exchange/templates')
export const getImportBatches = () => api.get<{ items: ImportBatch[] }>('/api/v1/data-exchange/imports')
export const confirmImport = (id: number) => api.post<{ batch: ImportBatch }>(`/api/v1/data-exchange/imports/${id}/confirm`, {})
export const revokeImport = (id: number) => api.post<{ batch: ImportBatch }>(`/api/v1/data-exchange/imports/${id}/revoke`, {})
export const getAttachments = (entityType: string, entityId: number) => api.get<{ items: Attachment[] }>(`/api/v1/data-exchange/attachments?entity_type=${encodeURIComponent(entityType)}&entity_id=${entityId}`)

export interface ExportPayload {
  organization_id: number
  resource: string
  format: 'xlsx' | 'pdf'
  filters: Record<string, unknown>
}

/** 从当前会话的数据范围解析所属企业 ID（无范围信息时回退 1，由服务端校验）。 */
export function resolveOrganizationId(): number {
  const { user } = createSessionStore()
  const scopes = user.value?.data_scopes ?? []
  const withOrg = scopes.find((item) => item.organization_id)
  return withOrg?.organization_id ?? 1
}

export async function exportData(payload: ExportPayload) {
  const response = await fetch('/api/v1/data-exchange/exports', {
    method: 'POST', credentials: 'include',
    headers: { 'X-CSRF-Token': await getCsrfToken(), 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as ApiResponse<unknown> | null
    throw new ApiError(body?.code ?? 'EXPORT_FAILED', body?.message ?? '导出失败', response.status, body?.request_id, body?.data)
  }
  if (typeof URL.createObjectURL !== 'function') return
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a'); link.href = url
  link.download = response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/)?.[1] ?? `adp-export.${payload.format}`
  link.click(); URL.revokeObjectURL(url)
}

async function multipart<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(path, { method: 'POST', body, credentials: 'include', headers: { 'X-CSRF-Token': await getCsrfToken(), Accept: 'application/json' } })
  const payload = await response.json() as ApiResponse<T>
  if (!response.ok || payload.code !== 'OK') throw new ApiError(payload.code, payload.message, response.status, payload.request_id, payload.data)
  return payload.data
}

export function previewImport(organizationId: number, templateCode: string, file: File) {
  const body = new FormData()
  body.append('organization_id', String(organizationId)); body.append('template_code', templateCode); body.append('file', file)
  return multipart<{ batch: ImportBatch }>('/api/v1/data-exchange/imports/preview', body)
}

export function uploadAttachment(organizationId: number, entityType: string, entityId: number, file: File) {
  const body = new FormData()
  body.append('organization_id', String(organizationId)); body.append('entity_type', entityType); body.append('entity_id', String(entityId)); body.append('file', file)
  return multipart<{ attachment: Attachment }>('/api/v1/data-exchange/attachments', body)
}

export async function downloadFile(path: string, fallbackName: string) {
  const response = await fetch(path, { credentials: 'include' })
  if (!response.ok) throw new ApiError('DOWNLOAD_FAILED', '文件下载失败', response.status)
  if (typeof URL.createObjectURL !== 'function') return
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a'); link.href = url
  link.download = response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/)?.[1] ?? fallbackName
  link.click(); URL.revokeObjectURL(url)
}

export const downloadTemplate = (code: string) => downloadFile(`/api/v1/data-exchange/templates/${code}/download`, `${code}.xlsx`)
export const downloadImportErrors = (id: number) => downloadFile(`/api/v1/data-exchange/imports/${id}/errors`, `import-${id}-errors.xlsx`)
export const downloadAttachment = (id: number, name: string) => downloadFile(`/api/v1/data-exchange/attachments/${id}/download`, name)
