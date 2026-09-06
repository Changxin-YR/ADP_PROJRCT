const app = getApp()
Page({
  data: { loading: true, groups: [] },
  onShow() { this.loadGroups() },
  async loadGroups() {
    this.setData({ loading: true })
    try {
      const res = await app.request({ url: '/master-data/pond-groups', method: 'GET' })
      if (res.success) this.setData({ groups: res.data.items || [] })
    } catch (e) {} finally { this.setData({ loading: false }) }
  },
  goGroup(e) { wx.navigateTo({ url: `/pages/ponds/ponds?groupId=${e.currentTarget.dataset.id}` }) },
})
