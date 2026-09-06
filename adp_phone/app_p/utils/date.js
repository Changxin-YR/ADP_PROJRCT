module.exports = {
  formatDate(date) {
    if (!date) return ''
    const d = date instanceof Date ? date : new Date(date)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  },

  formatTime(date) {
    if (!date) return ''
    const d = date instanceof Date ? date : new Date(date)
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  },

  formatDateTime(date) {
    if (!date) return ''
    return `${this.formatDate(date)} ${this.formatTime(date)}`
  },

  formatRelative(dateStr) {
    if (!dateStr) return ''
    const now = Date.now()
    const d = new Date(dateStr).getTime()
    const diff = now - d
    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`
    return this.formatDate(dateStr)
  },

  isToday(date) {
    const d = date instanceof Date ? date : new Date(date)
    const today = new Date()
    return d.getFullYear() === today.getFullYear() &&
      d.getMonth() === today.getMonth() &&
      d.getDate() === today.getDate()
  },
}
