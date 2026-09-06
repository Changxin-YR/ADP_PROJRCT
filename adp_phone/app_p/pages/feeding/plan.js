const app = getApp()
Page({
  data: { loading: true, plans: [] },
  onShow() { this.loadPlans() },
  onPullDownRefresh() { this.loadPlans().then(() => wx.stopPullDownRefresh()) },
  async loadPlans() {
    this.setData({ loading: true })
    try {
      const res = await app.request({ url: '/production/feed-plans', method: 'GET' })
      if (res.success) {
        const statusMap = { pending: { text: '待执行', color: 'warning' }, in_progress: { text: '执行中', color: 'primary' }, awaiting_review: { text: '待核验', color: 'info' }, reviewed: { text: '已核验', color: 'success' }, cancelled: { text: '已取消', color: 'gray' } }
        this.setData({ plans: (res.data.items || []).map(p => { const s = statusMap[p.status] || { text: p.status, color: 'gray' }; return { ...p, statusText: s.text, statusColor: s.color } }) })
      }
    } catch (e) {} finally { this.setData({ loading: false }) }
  },
  goDetail(e) { wx.navigateTo({ url: `/pages/feeding/plan-detail?id=${e.currentTarget.dataset.id}` }) },
})
