const app = getApp()

Page({
  data: {
    oldPassword: '',
    newPassword: '',
    confirmPassword: '',
    error: '',
    showOld: false,
    showNew: false,
    showConfirm: false,
  },

  onOldInput(e) { this.setData({ oldPassword: e.detail.value, error: '' }) },
  onNewInput(e) { this.setData({ newPassword: e.detail.value, error: '' }) },
  onConfirmInput(e) { this.setData({ confirmPassword: e.detail.value, error: '' }) },

  async submitChange() {
    const { oldPassword, newPassword, confirmPassword } = this.data

    if (!oldPassword) return this.setData({ error: '请输入当前密码' })
    if (!newPassword || newPassword.length < 8) return this.setData({ error: '新密码至少8位' })
    if (!/[a-zA-Z]/.test(newPassword) || !/[0-9]/.test(newPassword)) {
      return this.setData({ error: '密码需包含字母和数字' })
    }
    if (newPassword !== confirmPassword) return this.setData({ error: '两次输入不一致' })

    wx.showLoading({ title: '提交中' })
    try {
      await app.request({
        url: '/auth/password/change',
        method: 'POST',
        data: { old_password: oldPassword, new_password: newPassword },
      })
      wx.hideLoading()
      wx.showToast({ title: '修改成功', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 1000)
    } catch (e) {
      wx.hideLoading()
      this.setData({ error: e.message || '修改失败，请检查当前密码' })
    }
  },
})
