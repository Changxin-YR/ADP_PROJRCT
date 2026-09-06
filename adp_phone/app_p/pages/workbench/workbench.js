const app = getApp()

Page({
  data: {
    isOnline: true,
    loading: true,
    userName: '',
    roleName: '',
    avatarText: '',
    greeting: '',
    summary: {
      pendingTasks: 0,
      feedingCompletion: 0,
      alerts: 0,
      activePonds: 0,
    },
    tasks: [],
    alerts: [],
    favoritePonds: [],
  },

  onLoad() {
    this.initUserInfo()
    this.setGreeting()
  },

  onShow() {
    this.setData({ isOnline: app.globalData.isOnline })
    this.loadData()
  },

  onPullDownRefresh() {
    this.loadData().then(() => wx.stopPullDownRefresh())
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
      avatarText: (user.name || '用')[0],
    })
  },

  setGreeting() {
    const hour = new Date().getHours()
    let greeting = '早上好'
    if (hour >= 12 && hour < 14) greeting = '中午好'
    else if (hour >= 14 && hour < 18) greeting = '下午好'
    else if (hour >= 18) greeting = '晚上好'
    this.setData({ greeting })
  },

  async loadData() {
    this.setData({ loading: true })
    try {
      const res = await app.request({ url: '/workbench/summary', method: 'GET' })
      if (res.success) {
        this.setData({
          summary: res.data.summary || this.data.summary,
          tasks: (res.data.tasks || []).map(this.formatTask),
          alerts: res.data.alerts || [],
          favoritePonds: res.data.favoritePonds || [],
        })
      }
    } catch (e) {
      // 离线时从缓存加载
      const cached = wx.getStorageSync('workbench_cache')
      if (cached) {
        this.setData({
          summary: cached.summary || this.data.summary,
          tasks: (cached.tasks || []).map(this.formatTask),
          alerts: cached.alerts || [],
          favoritePonds: cached.favoritePonds || [],
        })
      }
    } finally {
      this.setData({ loading: false })
    }
  },

  formatTask(task) {
    const statusMap = {
      pending: { text: '待执行', color: 'warning' },
      in_progress: { text: '执行中', color: 'primary' },
      awaiting_review: { text: '待核验', color: 'info' },
      reviewed: { text: '已核验', color: 'success' },
      cancelled: { text: '已取消', color: 'gray' },
    }
    const s = statusMap[task.status] || { text: task.status, color: 'gray' }
    return {
      ...task,
      statusText: s.text,
      statusColor: s.color,
    }
  },

  refreshData() {
    this.loadData()
    wx.showToast({ title: '刷新中', icon: 'loading', duration: 500 })
  },

  // Navigation
  goProfile() { wx.switchTab({ url: '/pages/profile/profile' }) },
  goTodos() { wx.navigateTo({ url: '/pages/messages/messages?tab=todos' }) },
  goFeeding() { wx.switchTab({ url: '/pages/feeding/feeding' }) },
  goAlerts() { wx.switchTab({ url: '/pages/messages/messages' }) },
  goPonds() { wx.switchTab({ url: '/pages/ponds/ponds' }) },
  goMessages() { wx.switchTab({ url: '/pages/messages/messages' }) },
  goAllTasks() { wx.navigateTo({ url: '/pages/feeding/plan' }) },

  goPondDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/ponds/detail?id=${id}` })
  },

  goTaskDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/feeding/record?taskId=${id}` })
  },

  handleAlert(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/messages/messages?alertId=${id}` })
  },

  // Quick Actions
  quickFeed() {
    wx.navigateTo({ url: '/pages/feeding/record' })
  },

  quickPatrol() {
    wx.navigateTo({ url: '/pages/operations/patrol' })
  },

  quickMaterial() {
    wx.navigateTo({ url: '/pages/materials/requisition' })
  },

  quickPhoto() {
    wx.chooseMedia({
      count: 3,
      mediaType: ['image'],
      sourceType: ['camera'],
      success: (res) => {
        const paths = res.tempFiles.map(f => f.tempFilePath)
        wx.navigateTo({
          url: `/pages/operations/patrol?photos=${encodeURIComponent(JSON.stringify(paths))}`,
        })
      },
    })
  },
})
