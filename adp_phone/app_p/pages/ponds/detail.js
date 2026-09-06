const app = getApp()

Page({
  data: {
    isOnline: true,
    pond: {},
    batch: null,
    activities: [],
  },

  onLoad(options) {
    if (options.id) {
      this.pondId = options.id
      this.loadPondDetail(options.id)
    }
  },

  onShow() {
    this.setData({ isOnline: app.globalData.isOnline })
  },

  async loadPondDetail(id) {
    try {
      const res = await app.request({ url: `/master-data/ponds/${id}`, method: 'GET' })
      if (res.success) {
        const statusMap = {
          build: { text: '筹建', color: 'gray' }, stocked: { text: '放养', color: 'info' },
          rest: { text: '轮休', color: 'warning' }, clean: { text: '清塘', color: 'primary' }, rebuild: { text: '改造', color: 'gray' },
          preparing: { text: '筹建', color: 'gray' },
          stocking: { text: '放养', color: 'info' },
          farming: { text: '养殖', color: 'success' },
          resting: { text: '轮休', color: 'warning' },
          clearing: { text: '清塘', color: 'primary' },
          renovating: { text: '改造', color: 'gray' },
        }
        const pond = res.data.record || res.data
        const status = pond.pond_status || pond.status
        const s = statusMap[status] || { text: status, color: 'gray' }
        this.setData({
          pond: { ...pond, status, statusText: s.text, statusColor: s.color },
          batch: null,
          activities: (res.data.activities || []).map(a => ({
            ...a,
            timeStr: this.formatTime(a.created_at),
          })),
        })
      }
    } catch (e) {}
  },

  formatTime(dateStr) {
    if (!dateStr) return ''
    const d = new Date(dateStr)
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  },

  goFullHistory() {
    wx.navigateTo({ url: `/pages/ponds/history?id=${this.pondId}` })
  },

  goFeed() {
    wx.navigateTo({ url: `/pages/feeding/record?pondId=${this.pondId}&pondName=${this.data.pond.name}` })
  },

  goPatrol() {
    wx.navigateTo({ url: `/pages/operations/patrol?pondId=${this.pondId}&pondName=${this.data.pond.name}` })
  },

  goMaterial() {
    wx.navigateTo({ url: `/pages/materials/requisition?pondId=${this.pondId}&pondName=${this.data.pond.name}` })
  },
})
