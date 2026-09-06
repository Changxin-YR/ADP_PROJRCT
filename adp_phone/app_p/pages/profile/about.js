const app = getApp()

Page({
  data: {
    sdkVersion: '',
    serverVersion: '--',
  },

  onLoad() {
    const sysInfo = wx.getSystemInfoSync()
    this.setData({ sdkVersion: sysInfo.SDKVersion || '--' })
    this.loadServerVersion()
  },

  async loadServerVersion() {
    try {
      const res = await app.request({ url: '/health', method: 'GET' })
      if (res.success) this.setData({ serverVersion: res.data.version || res.data.environment || '在线' })
    } catch (e) {}
  },
})
