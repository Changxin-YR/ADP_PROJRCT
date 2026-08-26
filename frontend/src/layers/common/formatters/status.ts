import type { UserStatus } from '../api/models'

export const statusLabel: Record<UserStatus, string> = { pending: '审核中', rejected: '已驳回', active: '已通过', disabled: '已停用', must_change_password: '需要首次改密', retired: '已注销' }
export function getStatusLabel(status: UserStatus): string { return statusLabel[status] }
