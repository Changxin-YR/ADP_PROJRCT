const app = getApp()
Page({
  data: { batch: {} },
  onLoad(options) { if (options.id) this.loadBatch(options.id) },
  async loadBatch(id) {
    try {
      const res = await app.request({ url: `/production/batches/${id}`, method: 'GET' })
      if (res.success) this.setData({ batch: res.data })
    } catch (e) {}
  },
})
