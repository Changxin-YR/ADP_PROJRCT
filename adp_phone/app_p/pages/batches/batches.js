const app = getApp()
Page({
  data: { loading: true, keyword: '', batches: [], allBatches: [] },
  onShow() { this.loadBatches() },
  onPullDownRefresh() { this.loadBatches().then(() => wx.stopPullDownRefresh()) },
  async loadBatches() {
    this.setData({ loading: true })
    try {
      const res = await app.request({ url: '/production/batches', method: 'GET' })
      if (res.success) { const batches = res.data.items || []; this.setData({ allBatches: batches, batches }) }
    } catch (e) {} finally { this.setData({ loading: false }) }
  },
  onSearch(e) {
    const kw = e.detail.value.toLowerCase()
    this.setData({ keyword: kw, batches: this.data.allBatches.filter(b => b.code.toLowerCase().includes(kw) || (b.pondName || '').toLowerCase().includes(kw)) })
  },
  goDetail(e) { wx.navigateTo({ url: `/pages/batches/detail?id=${e.currentTarget.dataset.id}` }) },
})
