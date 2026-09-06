module.exports = {
  required(value, fieldName) {
    if (!value && value !== 0) return `${fieldName}不能为空`
    return ''
  },

  minLength(value, min, fieldName) {
    if (value && value.length < min) return `${fieldName}至少${min}个字符`
    return ''
  },

  maxLength(value, max, fieldName) {
    if (value && value.length > max) return `${fieldName}最多${max}个字符`
    return ''
  },

  isNumber(value, fieldName) {
    if (value && isNaN(Number(value))) return `${fieldName}必须为数字`
    return ''
  },

  positiveNumber(value, fieldName) {
    const num = Number(value)
    if (isNaN(num) || num <= 0) return `${fieldName}必须大于0`
    return ''
  },

  password(value) {
    if (!value || value.length < 8) return '密码至少8位'
    if (!/[a-zA-Z]/.test(value)) return '密码需包含字母'
    if (!/[0-9]/.test(value)) return '密码需包含数字'
    return ''
  },

  validate(rules) {
    for (const rule of rules) {
      const error = rule()
      if (error) return error
    }
    return ''
  },
}
