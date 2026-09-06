const app = getApp()
Page({
  data: {
    form: { pondId: '', pondName: '', deviceType: '', action: '', duration: '', remark: '' },
    deviceOptions: ['叶轮式', '水车式', '微孔式', '射流式'],
    actionOptions: [{ label: '开启', value: 'start' }, { label: '关闭', value: 'stop' }],
  },
  selectPond() {
    wx.navigateTo({ url: '/pages/ponds/picker?mode=select', events: { onPondSelected: (data) => { this.setData({ 'form.pondId': data.id, 'form.pondName': data.name }) } } })
  },
  onInput(e) { this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value }) },
  selectDevice(e) { this.setData({ 'form.deviceType': e.currentTarget.dataset.value }) },
  selectAction(e) { this.setData({ 'form.action': e.currentTarget.dataset.value }) },
  async submit() {
    const { form } = this.data
    if (!form.pondId) return wx.showToast({ title: '请选择塘口', icon: 'none' })
    wx.showLoading({ title: '提交中' })
    try {
      await app.request({ url: '/production/daily-operations', method: 'POST', data: {
        code: `WX-AERATION-${Date.now()}`, name: '微信增氧记录', pond_id: form.pondId,
        happened_at: new Date().toISOString(), note: form.remark,
        payload: { operation_type: 'aeration', device_type: form.deviceType, action: form.action, duration: form.duration ? parseFloat(form.duration) : null },
      } })
      wx.hideLoading(); wx.showToast({ title: '提交成功', icon: 'success' }); setTimeout(() => wx.navigateBack(), 1000)
    } catch (e) { wx.hideLoading(); wx.showToast({ title: '提交失败', icon: 'none' }) }
  },
})
