const app = getApp()

Page({
  data: { loading: true, records: [], filterType: '', filterTypeText: '', dateRange: '最近7天' },

  onShow() { this.loadHistory() },
  onPullDownRefresh() { this.loadHistory().then(() => wx.stopPullDownRefresh()) },

  async loadHistory() {
    this.setData({ loading: true })
    try {
      const [feedRes, operationsRes] = await Promise.all([
        app.request({ url: '/production/feed-logs', method: 'GET', data: { page: 1, page_size: 100 } }),
        app.request({ url: '/production/daily-operations', method: 'GET', data: { page: 1, page_size: 100 } }),
      ])
      const feedings = feedRes.success ? (feedRes.data.items || []).map(item => ({
        ...item, type: 'feeding', summary: item.name || item.note || '投喂记录', pondName: item.pond_name || '',
        created_at: item.recorded_at || item.operated_at || item.created_at,
      })) : []
      const operations = operationsRes.success ? (operationsRes.data.items || []).map(item => ({
        ...item, type: item.operation_type || item.type || 'patrol', summary: item.name || item.note || '日常作业',
        pondName: item.pond_name || '', created_at: item.operated_at || item.created_at,
      })) : []
      const now = Date.now()
      const dayLimit = this.data.dateRange === '最近7天' ? 7 : this.data.dateRange === '最近30天' ? 30 : null
      const records = [...feedings, ...operations]
        .filter(item => !this.data.filterType || item.type === this.data.filterType)
        .filter(item => !dayLimit || (item.created_at && now - new Date(item.created_at).getTime() <= dayLimit * 86400000))
        .map(item => ({ ...item, timeStr: item.created_at ? new Date(item.created_at).toLocaleString() : '--' }))
      this.setData({ records })
    } catch (e) {} finally { this.setData({ loading: false }) }
  },

  showTypePicker() {
    const items = ['全部类型', '投喂', '巡塘', '物料领用', '用药']
    const values = ['', 'feeding', 'patrol', 'requisition', 'medication']
    wx.showActionSheet({ itemList: items, success: (res) => {
      this.setData({ filterType: values[res.tapIndex], filterTypeText: items[res.tapIndex] === '全部类型' ? '' : items[res.tapIndex] })
      this.loadHistory()
    }})
  },

  showDateRange() {
    wx.showActionSheet({ itemList: ['最近7天', '最近30天', '全部'], success: (res) => {
      this.setData({ dateRange: ['最近7天', '最近30天', '全部'][res.tapIndex] })
      this.loadHistory()
    }})
  },
})
