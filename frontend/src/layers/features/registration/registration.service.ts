import { createApiClient } from '../../common/api/client'
import type { ApplicationSummary, UserSummary } from '../../common/api/models'

const api = createApiClient()

export interface RegistrationPayload {
  phone: string
  name: string
  password: string
  confirm_password: string
  desired_role_id: number
  area_id: number
  desired_scope_type?: 'farm' | 'area' | 'personal'
  application_note: string
}

export interface RegistrationOptions {
  roles: { id: number; code: string; name: string; description?: string }[]
  areas: { id: number; code: string; name: string }[]
  data_scopes: { id: number; code: string; name: string; scope_type: 'farm' | 'area' | 'personal'; area_id: number | null; area_name?: string | null }[]
}

export function fetchRegistrationOptions(): Promise<RegistrationOptions> {
  return api.get<RegistrationOptions>('/api/v1/auth/register/options')
}

export interface RegistrationResult {
  user: Pick<UserSummary, 'id' | 'name' | 'status'>
  application: ApplicationSummary
  status: 'pending'
  next_path: string
}

export function register(payload: RegistrationPayload): Promise<RegistrationResult> {
  return api.post<RegistrationResult>('/api/v1/auth/register', payload)
}

export function getApplication(): Promise<{ application: ApplicationSummary | null }> {
  return api.get('/api/v1/auth/application')
}

export function resubmitApplication(payload: Pick<RegistrationPayload, 'name' | 'desired_role_id' | 'area_id' | 'desired_scope_type' | 'application_note'>): Promise<{ application: ApplicationSummary; status: 'pending' }> {
  return api.patch('/api/v1/auth/application', payload)
}
