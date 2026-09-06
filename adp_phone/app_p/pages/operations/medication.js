const app = getApp()
Page({
  data: {
    form: { pondId: '', pondName: '', medicineName: '', purpose: '', dosage: '', unit: 'ml', remark: '' },
    purposeOptions: ['预防', '治疗', '改水', '消毒'],
  },
  selectPond() {
    wx.navigateTo({ url: '/pages/ponds/picker?mode=select', events: { onPondSelected: (data) => { this.setData({ 'form.pondId': data.id, 'form.pondName': data.name }) } } })
  },
  onInput(e) { this.setData({ [`form.${e.currentTarget.dataset.field}`]: e.detail.value }) },
  selectPurpose(e) { this.setData({ 'form.purpose': e.currentTarget.dataset.value }) },
  async submit() {
    const { form } = this.data
    if (!form.pondId) return wx.showToast({ title: '请选择塘口', icon: 'none' })
    if (!form.medicineName) return wx.showToast({ title: '请输入药品名称', icon: 'none' })
    wx.showLoading({ title: '提交中' })
    try {
      await app.request({ url: '/production/daily-operations', method: 'POST', data: {
        code: `WX-MED-${Date.now()}`, name: '微信用药记录', pond_id: form.pondId,
        happened_at: new Date().toISOString(), note: form.remark,
        payload: { operation_type: 'medication', medicine_name: form.medicineName, purpose: form.purpose, dosage: form.dosage ? parseFloat(form.dosage) : null, unit: form.unit },
      } })
      wx.hideLoading(); wx.showToast({ title: '提交成功', icon: 'success' }); setTimeout(() => wx.navigateBack(), 1000)
    } catch (e) { wx.hideLoading(); wx.showToast({ title: '提交失败', icon: 'none' }) }
  },
})
