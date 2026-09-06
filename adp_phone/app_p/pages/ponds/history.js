const app = getApp()
Page({
  data: { loading: true, records: [] },
  onLoad(options) { if (options.id) this.pondId = options.id; this.loadHistory() },
  onPullDownRefresh() { this.loadHistory().then(() => wx.stopPullDownRefresh()) },
  async loadHistory() {
    this.setData({ loading: true })
    try {
      const res = await app.request({ url: '/production/daily-operations', method: 'GET' })
      if (res.success) {
        const items = (res.data.items || []).filter(item => String(item.pond_id) === String(this.pondId))
        this.setData({ records: items.map(r => ({ ...r, timeStr: new Date(r.created_at || r.happened_at).toLocaleString() })) })
      }
    } catch (e) {} finally { this.setData({ loading: false }) }
  },
})
