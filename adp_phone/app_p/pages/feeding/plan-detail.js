const app = getApp()
Page({
  data: { plan: {} },
  onLoad(options) { if (options.id) this.loadPlan(options.id) },
  async loadPlan(id) {
    try {
      const res = await app.request({ url: `/production/feed-plans/${id}`, method: 'GET' })
      if (res.success) {
        const statusMap = { pending: { text: '待执行', color: 'warning' }, in_progress: { text: '执行中', color: 'primary' }, awaiting_review: { text: '待核验', color: 'info' }, reviewed: { text: '已核验', color: 'success' }, cancelled: { text: '已取消', color: 'gray' } }
        const p = res.data; const s = statusMap[p.status] || { text: p.status, color: 'gray' }
        const user = app.globalData.userInfo || {}
        this.setData({ plan: { ...p, statusText: s.text, statusColor: s.color, canExecute: p.status === 'pending' && (user.role_code === 'breed_worker' || user.role_code === 'breed_manager') } })
      }
    } catch (e) {}
  },
  async startExecution() {
    wx.showModal({ title: '确认执行', content: '确定开始执行此投喂任务？', success: async (res) => {
      if (res.confirm) {
        await app.request({ url: `/production/feed-plans/${this.data.plan.id}/submit`, method: 'POST', data: { expected_version: this.data.plan.version || 1 } })
        wx.showToast({ title: '已开始', icon: 'success' })
        wx.navigateBack()
      }
    }})
  },
})
