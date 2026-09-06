Page({
  data: {
    autoSync: true,
    compressPhoto: true,
    notifications: true,
    cacheSize: '0 KB',
  },

  onShow() {
    this.setData({
      autoSync: wx.getStorageSync('setting_autoSync') !== false,
      compressPhoto: wx.getStorageSync('setting_compress') !== false,
      notifications: wx.getStorageSync('setting_notifications') !== false,
    })
    this.calcCache()
  },

  toggleAutoSync(e) {
    wx.setStorageSync('setting_autoSync', e.detail.value)
    this.setData({ autoSync: e.detail.value })
  },

  toggleCompress(e) {
    wx.setStorageSync('setting_compress', e.detail.value)
    this.setData({ compressPhoto: e.detail.value })
  },

  toggleNotifications(e) {
    wx.setStorageSync('setting_notifications', e.detail.value)
    this.setData({ notifications: e.detail.value })
  },

  calcCache() {
    const info = wx.getStorageInfoSync()
    const kb = info.currentSize
    this.setData({ cacheSize: kb > 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb} KB` })
  },

  clearCache() {
    wx.showModal({
      title: '清除缓存',
      content: '将清除本地缓存数据（不影响离线队列）',
      success: (res) => {
        if (res.confirm) {
          const queue = wx.getStorageSync('offline_queue')
          const session = wx.getStorageSync('session_id')
          wx.clearStorageSync()
          if (queue) wx.setStorageSync('offline_queue', queue)
          if (session) wx.setStorageSync('session_id', session)
          wx.showToast({ title: '已清除', icon: 'success' })
          this.calcCache()
        }
      },
    })
  },
})
