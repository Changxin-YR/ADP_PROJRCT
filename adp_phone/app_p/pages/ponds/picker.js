const app = getApp()

Page({
  data: {
    keyword: '',
    ponds: [],
    filteredPonds: [],
    mode: 'select',
  },

  onLoad(options) {
    this.eventChannel = this.getOpenerEventChannel()
    if (options.mode) this.setData({ mode: options.mode })
    this.loadPonds()
  },

  async loadPonds() {
    try {
      const res = await app.request({ url: '/master-data/ponds', method: 'GET', data: { status: 'verified' } })
      if (res.success) {
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
        const ponds = (res.data.items || []).map(p => {
          const status = p.pond_status || p.status
          const s = statusMap[status] || { text: status, color: 'gray' }
          return { ...p, status, statusText: s.text, statusColor: s.color }
        })
        this.setData({ ponds, filteredPonds: ponds })
      }
    } catch (e) {
      const cached = wx.getStorageSync('ponds_cache') || []
      this.setData({ ponds: cached, filteredPonds: cached })
    }
  },

  onSearch(e) {
    const keyword = e.detail.value.toLowerCase()
    this.setData({
      keyword,
      filteredPonds: this.data.ponds.filter(p => p.name.toLowerCase().includes(keyword)),
    })
  },

  selectPond(e) {
    const pond = e.currentTarget.dataset.pond
    if (this.eventChannel) {
      this.eventChannel.emit('onPondSelected', { id: pond.id, name: pond.name })
    }
    wx.navigateBack()
  },
})
