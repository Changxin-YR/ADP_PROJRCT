const app = getApp()

Page({
  data: {
    isOnline: true,
    items: [{ id: '', name: '', quantity: '', unit: 'kg', stock: null }],
    form: {
      pondId: '',
      pondName: '',
      purpose: '',
      remark: '',
    },
    purposeOptions: ['日常投喂', '用药', '改水', '清塘', '其他'],
  },

  onShow() {
    this.setData({ isOnline: app.globalData.isOnline })
  },

  addMaterial() {
    const items = [...this.data.items, { id: '', name: '', quantity: '', unit: 'kg', stock: null }]
    this.setData({ items })
  },

  removeItem(e) {
    const items = [...this.data.items]
    items.splice(e.currentTarget.dataset.index, 1)
    this.setData({ items })
  },

  increaseQty(e) {
    const index = e.currentTarget.dataset.index
    const items = [...this.data.items]
    items[index].quantity = (parseFloat(items[index].quantity) || 0) + 1
    this.setData({ items })
  },

  decreaseQty(e) {
    const index = e.currentTarget.dataset.index
    const items = [...this.data.items]
    const cur = parseFloat(items[index].quantity) || 0
    items[index].quantity = Math.max(0, cur - 1)
    this.setData({ items })
  },

  onQtyChange(e) {
    const index = e.currentTarget.dataset.index
    const items = [...this.data.items]
    items[index].quantity = e.detail.value
    this.setData({ items })
  },

  selectPond() {
    wx.navigateTo({
      url: '/pages/ponds/picker?mode=select',
      events: {
        onPondSelected: (data) => {
          this.setData({ 'form.pondId': data.id, 'form.pondName': data.name })
        },
      },
    })
  },

  selectPurpose(e) {
    this.setData({ 'form.purpose': e.currentTarget.dataset.value })
  },

  onRemarkChange(e) {
    this.setData({ 'form.remark': e.detail.value })
  },

  async submitRequisition() {
    const { items, form } = this.data
    const validItems = items.filter(i => i.id && i.quantity)

    if (validItems.length === 0) return wx.showToast({ title: '请添加物料', icon: 'none' })
    if (!form.pondId) return wx.showToast({ title: '请选择塘口', icon: 'none' })

    wx.showLoading({ title: '提交中' })
    try {
      const payload = {
        pond_id: form.pondId,
        purpose: form.purpose,
        remark: form.remark,
        items: validItems.map(i => ({
          material_id: i.id,
          quantity: parseFloat(i.quantity),
          unit: i.unit,
        })),
      }

      const warehouses = await app.request({ url: '/warehouse/warehouses', method: 'GET' })
      const warehouseId = (warehouses.data.items || [])[0] && (warehouses.data.items || [])[0].id
      if (!warehouseId) throw new Error('WAREHOUSE_NOT_FOUND')
      for (const item of validItems) {
        await app.request({ url: '/warehouse/issue-requests', method: 'POST', data: {
          code: `WX-ISSUE-${Date.now()}-${item.id}`,
          name: '微信物料领用申请', warehouse_id: warehouseId, material_id: item.id,
          pond_id: form.pondId, quantity: parseFloat(item.quantity), scene: form.purpose, note: form.remark,
        } })
      }
      wx.hideLoading()
      wx.showToast({ title: '领用成功', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 1000)
    } catch (e) {
      wx.hideLoading()
      if (!this.data.isOnline) {
        app.addToOfflineQueue({ type: 'requisition', data: { items: validItems, ...form } })
        wx.showToast({ title: '已保存至离线队列', icon: 'none' })
        setTimeout(() => wx.navigateBack(), 1000)
      } else {
        wx.showToast({ title: '提交失败', icon: 'none' })
      }
    }
  },
})
