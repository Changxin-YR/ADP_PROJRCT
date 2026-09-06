const app = getApp()

Page({
  data: {
    userName: '',
    roleName: '',
    areaName: '',
    avatarText: '',
    offlineCount: 0,
    stats: {
      totalFeedings: 0,
      totalPatrols: 0,
      workDays: 0,
    },
  },

  onShow() {
    this.initUserInfo()
    this.loadStats()
    this.checkOfflineData()
  },

  initUserInfo() {
    const user = app.globalData.userInfo || {}
    const roleMap = {
      super_admin: '超级管理员',
      area_manager: '基地管理员',
      breed_manager: '养殖管理员',
      breed_worker: '养殖作业员',
      warehouse_manager: '仓储管理员',
      purchaser: '采购人员',
    }
    this.setData({
      userName: user.name || '用户',
      roleName: roleMap[user.role_code] || '作业人员',
      areaName: user.area_name || '',
      avatarText: (user.name || '用')[0],
    })
  },

  async loadStats() {
    try {
      const [feedRes, operationsRes] = await Promise.all([
        app.request({ url: '/production/feed-logs', method: 'GET', data: { page: 1, page_size: 100 } }),
        app.request({ url: '/production/daily-operations', method: 'GET', data: { page: 1, page_size: 100 } }),
      ])
      const feedings = feedRes.success ? (feedRes.data.items || []) : []
      const operations = operationsRes.success ? (operationsRes.data.items || []) : []
      const patrols = operations.filter(item => ['patrol', '巡塘'].includes(item.operation_type || item.type))
      const days = new Set([...feedings, ...operations].map(item => String(item.operated_at || item.recorded_at || item.created_at || '').slice(0, 10)).filter(Boolean))
      this.setData({ stats: { totalFeedings: feedings.length, totalPatrols: patrols.length, workDays: days.size } })
    } catch (e) {}
  },

  checkOfflineData() {
    const queue = wx.getStorageSync('offline_queue') || []
    this.setData({ offlineCount: queue.length })
  },

  goHistory() {
    wx.navigateTo({ url: '/pages/profile/history' })
  },

  goChangePassword() {
    wx.navigateTo({ url: '/pages/profile/password' })
  },

  goOfflineData() {
    wx.navigateTo({ url: '/pages/profile/offline' })
  },

  goSettings() {
    wx.navigateTo({ url: '/pages/profile/settings' })
  },

  goAbout() {
    wx.navigateTo({ url: '/pages/profile/about' })
  },

  handleLogout() {
    wx.showModal({
      title: '确认退出',
      content: '退出后需重新登录，离线数据不会丢失',
      confirmColor: '#FF3B30',
      success: (res) => {
        if (res.confirm) {
          app.logout()
          wx.reLaunch({ url: '/pages/login/login' })
        }
      },
    })
  },
})
