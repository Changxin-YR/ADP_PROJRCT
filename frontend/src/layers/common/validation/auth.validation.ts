export type FieldErrors = Record<string, string>

export function validateLogin(identifier: string, password: string): FieldErrors {
  const errors: FieldErrors = {}
  if (!identifier.trim()) errors.identifier = '请输入手机号或账号'
  if (!password) errors.password = '请输入密码'
  return errors
}

export function validateRegistration(payload: { phone: string; name: string; password: string; confirm_password: string; desired_role_id: number | string; area_id: number | string; desired_scope_type?: string; application_note: string }): FieldErrors {
  const errors: FieldErrors = {}
  const phone = payload.phone.replace(/[\s-]/g, '').replace(/^\+86/, '')
  if (!/^1[3-9]\d{9}$/.test(phone)) errors.phone = '请输入有效的大陆手机号'
  const name = payload.name.trim()
  if (!name) errors.name = '请输入姓名'
  else if (name.length < 2 || name.length > 40) errors.name = '姓名长度必须为 2-40 个字符'
  if (payload.password.length < 8 || !/[A-Za-z]/.test(payload.password) || !/\d/.test(payload.password)) errors.password = '密码至少 8 位且包含字母和数字'
  if (payload.password !== payload.confirm_password) errors.confirm_password = '两次输入的密码不一致'
  if (!payload.desired_role_id) errors.desired_role_id = '请选择申请岗位'
  const scopeType = payload.desired_scope_type ?? 'area'
  if (!['farm', 'area', 'personal'].includes(scopeType)) errors.desired_scope_type = '请选择有效的数据范围'
  if (scopeType === 'area' && !payload.area_id) errors.area_id = '请选择所属区域/基地'
  if (payload.application_note.length > 500) errors.application_note = '申请说明不能超过 500 个字符'
  return errors
}
