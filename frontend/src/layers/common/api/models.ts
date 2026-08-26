export type UserStatus = 'pending' | 'rejected' | 'active' | 'disabled' | 'must_change_password' | 'retired'

export interface UserSummary {
  id: number
  name: string
  phone: string
  login_name?: string | null
  status: UserStatus
  roles: Array<{ id: number; code: string; name: string }>
  data_scopes: Array<{ id: number; code: string; name: string; scope_type?: 'farm' | 'area' | 'personal' | null; area_id?: number | null; organization_id?: number | null }>
  permissions: string[]
}

export interface ApplicationSummary {
  id: number
  version_no: number
  name: string
  phone?: string | null
  desired_role_id: number
  area_id: number
  desired_scope_type?: 'farm' | 'area' | 'personal' | null
  application_note: string
  status: 'pending' | 'approved' | 'rejected'
  rejection_reason?: string | null
  desired_role_name?: string | null
  area_name?: string | null
  reviewer_name?: string | null
  reviewed_by?: number | null
  created_at?: string
  submitted_at?: string
  updated_at?: string
  reviewed_at?: string | null
  admin_message?: string | null
}

export interface SessionSummary { expires_at: string }

export interface ManagedUser extends UserSummary {
  created_at?: string
  updated_at?: string
}

export interface ApiResponse<T> {
  code: string
  message: string
  data: T
  request_id: string
}
