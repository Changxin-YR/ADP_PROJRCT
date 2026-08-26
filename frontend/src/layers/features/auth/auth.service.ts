import { createApiClient } from '../../common/api/client'
import type { CurrentUserResult, LoginResult } from './auth.models'

const api = createApiClient()

export function login(identifier: string, password: string): Promise<LoginResult> {
  return api.post<LoginResult>('/api/v1/auth/login', { identifier, password })
}

export function getCurrentUser(): Promise<CurrentUserResult> {
  return api.get<CurrentUserResult>('/api/v1/auth/me')
}

export function logout(): Promise<null> {
  return api.post<null>('/api/v1/auth/logout')
}

export function changePassword(currentPassword: string | undefined, newPassword: string, confirmPassword: string): Promise<{ next_path: string }> {
  return api.post('/api/v1/auth/password/change', {
    current_password: currentPassword,
    new_password: newPassword,
    confirm_password: confirmPassword,
  })
}
