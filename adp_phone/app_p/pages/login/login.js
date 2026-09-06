const app = getApp()

Page({
  data: {
    identifier: '',
    password: '',
    showPassword: false,
    loading: false,
    errorMsg: '',
  },

  onLoad() {
    // 如果已登录则跳转工作台
    if (app.globalData.sessionToken && app.globalData.userInfo) {
      wx.switchTab({ url: '/pages/workbench/workbench' })
    }
  },

  onIdentifierInput(e) {
    this.setData({ identifier: e.detail.value.trim(), errorMsg: '' })
  },

  onPasswordInput(e) {
    this.setData({ password: e.detail.value, errorMsg: '' })
  },

  togglePassword() {
    this.setData({ showPassword: !this.data.showPassword })
  },

  async handleLogin() {
    const { identifier, password } = this.data
    if (!identifier || !password) {
      this.setData({ errorMsg: '请输入账号和密码' })
      return
    }
    if (password.length < 8) {
      this.setData({ errorMsg: '密码至少8位' })
      return
    }

    this.setData({ loading: true, errorMsg: '' })

    try {
      // 先获取CSRF Token
      await app.getCsrfToken()

      // 登录请求
      const res = await app.request({
        url: '/auth/login',
        method: 'POST',
        data: { identifier, password },
      })

      if (res.success) {
        const { user, session } = res.data
        app.globalData.sessionToken = session.token || ''
        app.setUserInfo(user)
        wx.setStorageSync('session_token', app.globalData.sessionToken)
        wx.setStorageSync('user_info', user)

        // 根据用户状态跳转
        if (user.status === 'must_change_password') {
          wx.redirectTo({ url: '/pages/profile/password?force=1' })
        } else if (user.status === 'active') {
          wx.switchTab({ url: '/pages/workbench/workbench' })
        } else {
          this.setData({ errorMsg: '账号状态异常，请联系管理员' })
        }
      } else {
        const msg = res.message || '登录失败'
        this.setData({ errorMsg: msg })
      }
    } catch (e) {
      this.setData({ errorMsg: '网络异常，请检查网络连接' })
    } finally {
      this.setData({ loading: false })
    }
  },
})
