const app = getApp()

Page({
  data: {
    isOnline: true,
    loading: true,
    activeTab: 'plan',
    filterDate: '',
    filterPond: '',
    filterStatus: '',
    filterStatusText: '',
    plans: [],
    records: [],
    ponds: [],
  },

  onLoad(options) {
    if (options.tab) {
      this.setData({ activeTab: options.tab })
    }
    this.setData({ filterDate: this.formatToday() })
  },

  onShow() {
    this.setData({ isOnline: app.globalData.isOnline })
    this.loadData()
  },

  onPullDownRefresh() {
    this.loadData().then(() => wx.stopPullDownRefresh())
  },

  formatToday() {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  },

  switchTab(e) {
    const tab = e.currentTarget.dataset.tab
    this.setData({ activeTab: tab })
    this.loadData()
  },

  async loadData() {
    this.setData({ loading: true })
    const { activeTab, filterDate, filterPond, filterStatus } = this.data
    const params = { date: filterDate }
    if (filterPond) params.pond_id = filterPond
    if (filterStatus) params.status = filterStatus

    try {
      if (activeTab === 'plan') {
        const res = await app.request({ url: '/production/feed-plans', method: 'GET', data: params })
        if (res.success) {
          this.setData({ plans: (res.data.items || []).map(this.formatPlan.bind(this)) })
        }
      } else {
        const res = await app.request({ url: '/production/feed-logs', method: 'GET', data: params })
        if (res.success) {
          this.setData({ records: res.data.items || [] })
        }
      }
    } catch (e) {
      const cacheKey = `feeding_${activeTab}_cache`
      const cached = wx.getStorageSync(cacheKey)
      if (cached) {
        if (activeTab === 'plan') {
          this.setData({ plans: cached })
        } else {
          this.setData({ records: cached })
        }
      }
    } finally {
      this.setData({ loading: false })
    }
  },

  formatPlan(plan) {
    const statusMap = {
      pending: { text: '待执行', color: 'warning' },
      in_progress: { text: '执行中', color: 'primary' },
      awaiting_review: { text: '待核验', color: 'info' },
      reviewed: { text: '已核验', color: 'success' },
      reflected: { text: '已复盘', color: 'success' },
      cancelled: { text: '已取消', color: 'gray' },
    }
    const s = statusMap[plan.status] || { text: plan.status, color: 'gray' }
    const user = app.globalData.userInfo || {}
    const canExecute = plan.status === 'pending' &&
      (user.role_code === 'breed_worker' || user.role_code === 'breed_manager')
    return { ...plan, statusText: s.text, statusColor: s.color, canExecute }
  },

  showDatePicker() {
    wx.showActionSheet({
      itemList: ['今天', '昨天', '全部日期'],
      success: (res) => {
        const d = new Date()
        if (res.tapIndex === 0) {
          this.setData({ filterDate: this.formatToday() })
        } else if (res.tapIndex === 1) {
          d.setDate(d.getDate() - 1)
          this.setData({ filterDate: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` })
        } else if (res.tapIndex === 2) {
          this.setData({ filterDate: '' })
        }
        this.loadData()
      },
    })
  },

  showPondPicker() {
    wx.navigateTo({ url: '/pages/ponds/picker?mode=filter' })
  },

  showStatusPicker() {
    const items = ['全部状态', '待执行', '执行中', '待核验', '已核验', '已取消']
    const values = ['', 'pending', 'in_progress', 'awaiting_review', 'reviewed', 'cancelled']
    wx.showActionSheet({
      itemList: items,
      success: (res) => {
        this.setData({
          filterStatus: values[res.tapIndex],
          filterStatusText: items[res.tapIndex] === '全部状态' ? '' : items[res.tapIndex],
        })
        this.loadData()
      },
    })
  },

  startExecution(e) {
    const id = e.currentTarget.dataset.id
    wx.showModal({
      title: '确认执行',
      content: '确定开始执行此投喂任务？',
      success: async (res) => {
        if (res.confirm) {
          try {
            const plan = this.data.plans.find(item => String(item.id) === String(id)) || {}
            await app.request({ url: `/production/feed-plans/${id}/submit`, method: 'POST', data: { expected_version: plan.version || 1 } })
            wx.showToast({ title: '已开始执行', icon: 'success' })
            this.loadData()
          } catch (e) {
            wx.showToast({ title: '操作失败', icon: 'none' })
          }
        }
      },
    })
  },

  goPlanDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/feeding/plan-detail?id=${id}` })
  },

  goRecordDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/feeding/record-detail?id=${id}` })
  },

  createRecord() {
    wx.navigateTo({ url: '/pages/feeding/record' })
  },
})
