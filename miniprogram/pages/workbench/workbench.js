Page({
  data: { loading: true, error: '', summary: null },
  onLoad() {
    const app = getApp()
    wx.request({
      url: `${app.globalData.apiBase}/api/v1/workbench/summary`,
      success: (response) => this.setData({ summary: response.data.data || response.data, loading: false }),
      fail: (error) => this.setData({ error: error.errMsg || '请求失败', loading: false }),
    })
  },
})
