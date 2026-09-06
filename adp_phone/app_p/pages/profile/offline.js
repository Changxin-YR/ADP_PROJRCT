const app = getApp()

Page({
  data: { queue: [] },

  onShow() {
    this.loadQueue()
  },

  loadQueue() {
    const raw = wx.getStorageSync('offline_queue') || []
    const typeMap = {
      feeding_record: '投喂记录',
      patrol: '巡塘记录',
      requisition: '物料领用',
    }
    const queue = raw.map((item, index) => ({
      ...item,
      index,
      typeText: typeMap[item.type] || item.type,
      timeStr: item.timestamp ? new Date(item.timestamp).toLocaleString() : '',
    }))
    this.setData({ queue })
  },

  async syncNow() {
    if (!app.globalData.isOnline) {
      return wx.showToast({ title: '当前无网络', icon: 'none' })
    }
    wx.showLoading({ title: '同步中' })
    await app.syncOfflineData()
    wx.hideLoading()
    wx.showToast({ title: '同步完成', icon: 'success' })
    this.loadQueue()
  },
})
