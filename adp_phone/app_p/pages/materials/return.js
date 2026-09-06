const app = getApp()
Page({
  data: {
    form: { materialName: '', quantity: '', reason: '', remark: '' },
    reasonOptions: ['剩余退回', '质量问题', '计划变更', '其他'],
  },
  onInput(e) { this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value }) },
  selectReason(e) { this.setData({ 'form.reason': e.currentTarget.dataset.value }) },
  async submit() {
    const { form } = this.data
    if (!form.materialName) return wx.showToast({ title: '请输入物料名称', icon: 'none' })
    if (!form.quantity) return wx.showToast({ title: '请输入数量', icon: 'none' })
    wx.showLoading({ title: '提交中' })
    try {
      throw new Error('RETURN_REQUIRES_SOURCE_IDS')
      wx.hideLoading(); wx.showToast({ title: '退还成功', icon: 'success' }); setTimeout(() => wx.navigateBack(), 1000)
    } catch (e) { wx.hideLoading(); wx.showToast({ title: '提交失败', icon: 'none' }) }
  },
})
