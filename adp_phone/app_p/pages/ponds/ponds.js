const app = getApp()

Page({
  data: {
    isOnline: true,
    loading: true,
    keyword: '',
    activeStatus: '',
    ponds: [],
    filteredPonds: [],
    statusOptions: [
      { label: '筹建', value: 'preparing', color: 'gray' },
      { label: '放养', value: 'stocking', color: 'info' },
      { label: '养殖', value: 'farming', color: 'success' },
      { label: '轮休', value: 'resting', color: 'warning' },
      { label: '清塘', value: 'clearing', color: 'primary' },
      { label: '改造', value: 'renovating', color: 'gray' },
    ],
  },

  onShow() {
    this.setData({ isOnline: app.globalData.isOnline })
    this.loadPonds()
  },

  onPullDownRefresh() {
    this.loadPonds().then(() => wx.stopPullDownRefresh())
  },

  async loadPonds() {
    this.setData({ loading: true })
    try {
      const res = await app.request({ url: '/master-data/ponds', method: 'GET' })
      if (res.success) {
        const ponds = (res.data.items || []).map(this.formatPond.bind(this))
        this.setData({ ponds })
        wx.setStorageSync('ponds_cache', ponds)
      }
    } catch (e) {
      const cached = wx.getStorageSync('ponds_cache')
      if (cached) this.setData({ ponds: cached })
    } finally {
      this.setData({ loading: false })
      this.applyFilter()
    }
  },

  formatPond(pond) {
    const statusMap = {
      build: { text: '筹建', color: 'gray' }, stocked: { text: '放养', color: 'info' },
      rest: { text: '轮休', color: 'warning' }, clean: { text: '清塘', color: 'primary' }, rebuild: { text: '改造', color: 'gray' },
      preparing: { text: '筹建', color: 'gray' },
      stocking: { text: '放养', color: 'info' },
      farming: { text: '养殖', color: 'success' },
      resting: { text: '轮休', color: 'warning' },
      clearing: { text: '清塘', color: 'primary' },
      renovating: { text: '改造', color: 'gray' },
    }
    const status = pond.pond_status || pond.status
    const s = statusMap[status] || { text: status, color: 'gray' }
    return { ...pond, status, statusText: s.text, statusColor: s.color }
  },

  onSearch(e) {
    this.setData({ keyword: e.detail.value })
    this.applyFilter()
  },

  filterByStatus(e) {
    this.setData({ activeStatus: e.currentTarget.dataset.status })
    this.applyFilter()
  },

  applyFilter() {
    const { ponds, keyword, activeStatus } = this.data
    let result = ponds
    if (keyword) {
      const kw = keyword.toLowerCase()
      result = result.filter(p => p.name.toLowerCase().includes(kw))
    }
    if (activeStatus) {
      result = result.filter(p => p.status === activeStatus)
    }
    this.setData({ filteredPonds: result })
  },

  goPondDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/ponds/detail?id=${id}` })
  },
})
