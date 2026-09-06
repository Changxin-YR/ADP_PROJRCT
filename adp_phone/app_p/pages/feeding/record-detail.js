const app = getApp()
Page({
  data: { record: {} },
  onLoad(options) { if (options.id) this.loadRecord(options.id) },
  async loadRecord(id) {
    try {
      const res = await app.request({ url: `/production/feed-logs/${id}`, method: 'GET' })
      if (res.success) {
        const eatingMap = { normal: '正常', less: '偏少', more: '偏多', none: '不吃' }
        const r = res.data
        this.setData({ record: { ...r, eatingStatusText: eatingMap[r.eating_status] || '', photos: r.photos || [] } })
      }
    } catch (e) {}
  },
  previewPhoto(e) { wx.previewImage({ current: e.currentTarget.dataset.url, urls: this.data.record.photos }) },
})
