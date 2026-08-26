import type { UserSummary } from '../../common/api/models'

export interface LoginResult {
  user: UserSummary
  next_path: string
  session: { expires_at: string }
}

export interface CurrentUserResult {
  user: UserSummary
  next_path: string
  session: { expires_at: string }
}
