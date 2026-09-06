const config = require('./utils/config')

App({
  globalData: {
    baseUrl: config.baseUrl,
    userInfo: null,
    sessionToken: null,
    csrfToken: null,
    cookieJar: {},
    isOnline: true,
    offlineQueue: [],
  },

  onLaunch() {
    this.globalData.cookieJar = wx.getStorageSync('http_cookies') || {}
    this.checkSession()
    this.initNetworkListener()
    this.syncOfflineData()
  },

  setUserInfo(user) {
    const roles = user && Array.isArray(user.roles) ? user.roles : []
    const normalized = {
      ...(user || {}),
      role_code: user && user.role_code || (roles[0] && roles[0].code) || '',
      organization_id: user && user.organization_id || ((user && user.data_scopes) || []).find(scope => scope.organization_id)?.organization_id || '',
    }
    this.globalData.userInfo = normalized
    wx.setStorageSync('user_info', normalized)
    return normalized
  },

  // 检查登录状态
  checkSession() {
    const token = wx.getStorageSync('session_token')
    const userInfo = wx.getStorageSync('user_info')
    if (token && userInfo) {
      this.globalData.sessionToken = token
      this.setUserInfo(userInfo)
      this.refreshSession()
    }
  },

  // 刷新会话
  async refreshSession() {
    try {
      const res = await this.request({ url: '/auth/me', method: 'GET' })
      if (res.success) {
        this.setUserInfo(res.data.user)
      } else {
        this.logout()
      }
    } catch (e) {
      // 离线时保留缓存的会话
      if (this.globalData.isOnline) {
        this.logout()
      }
    }
  },

  // 获取CSRF Token
  async getCsrfToken() {
    try {
      const res = await this.request({ url: '/auth/csrf', method: 'GET' })
      if (res.success) {
        this.globalData.csrfToken = res.data.csrf_token
        wx.setStorageSync('csrf_token', res.data.csrf_token)
      }
      return this.globalData.csrfToken
    } catch (e) {
      return wx.getStorageSync('csrf_token')
    }
  },

  // 统一请求方法
  request({ url, method = 'GET', data = {}, header = {} }) {
    return new Promise((resolve, reject) => {
      const baseHeader = {
        'Content-Type': 'application/json',
        'X-ADP-Client': 'mobile',
      }
      const cookieHeader = this.getCookieHeader()
      if (cookieHeader) baseHeader['Cookie'] = cookieHeader
      if (this.globalData.csrfToken && method !== 'GET') {
        baseHeader['X-CSRF-Token'] = this.globalData.csrfToken
      }
      wx.request({
        url: this.globalData.baseUrl + url,
        method,
        data,
        header: { ...baseHeader, ...header },
        success: (res) => {
          this.captureResponseCookies(res)
          if (res.statusCode === 401) {
            // 会话过期
            wx.removeStorageSync('session_token')
            wx.removeStorageSync('user_info')
            wx.reLaunch({ url: '/pages/login/login' })
            reject(new Error('SESSION_EXPIRED'))
          } else {
            const body = res.data || {}
            if (body && typeof body === 'object' && Object.prototype.hasOwnProperty.call(body, 'code')) {
              const payload = body.data
              // Current APIs wrap a single resource in { data: { record } }.
              const data = payload && typeof payload === 'object' && Object.keys(payload).length === 1 && Object.prototype.hasOwnProperty.call(payload, 'record')
                ? payload.record
                : payload
              resolve({ ...body, success: body.code === 'OK', data })
            } else {
              resolve(body)
            }
          }
        },
        fail(err) {
          reject(err)
        },
      })
    })
  },

  getCookieHeader() {
    const cookies = { ...(this.globalData.cookieJar || {}) }
    if (this.globalData.sessionToken) cookies.adp_session = this.globalData.sessionToken
    return Object.entries(cookies).map(([name, value]) => `${name}=${value}`).join('; ')
  },

  captureResponseCookies(res) {
    const headers = res.header || {}
    const headerCookie = headers['Set-Cookie'] || headers['set-cookie']
    const rawCookies = [...(res.cookies || [])]
    if (Array.isArray(headerCookie)) rawCookies.push(...headerCookie)
    else if (headerCookie) rawCookies.push(...String(headerCookie).split(/,(?=\s*[^;,=]+=[^;,]*)/))
    if (!rawCookies.length) return
    const jar = { ...(this.globalData.cookieJar || {}) }
    for (const raw of rawCookies) {
      const pair = String(raw).split(';', 1)[0]
      const separator = pair.indexOf('=')
      if (separator > 0) jar[pair.slice(0, separator).trim()] = pair.slice(separator + 1).trim()
    }
    this.globalData.cookieJar = jar
    wx.setStorageSync('http_cookies', jar)
  },

  // 退出登录
  logout() {
    this.globalData.sessionToken = null
    this.globalData.userInfo = null
    this.globalData.csrfToken = null
    this.globalData.cookieJar = {}
    wx.removeStorageSync('session_token')
    wx.removeStorageSync('user_info')
    wx.removeStorageSync('csrf_token')
    wx.removeStorageSync('http_cookies')
    wx.reLaunch({ url: '/pages/login/login' })
  },

  // 网络监听
  initNetworkListener() {
    wx.onNetworkStatusChange((res) => {
      this.globalData.isOnline = res.isConnected
      if (res.isConnected) {
        this.syncOfflineData()
      }
    })
  },

  // 离线数据同步
  async syncOfflineData() {
    if (!this.globalData.isOnline) return
    const queue = wx.getStorageSync('offline_queue') || []
    if (queue.length === 0) return

    const failed = []
    for (const item of queue) {
      try {
        await this.request(item)
      } catch (e) {
        failed.push(item)
      }
    }
    wx.setStorageSync('offline_queue', failed)
    this.globalData.offlineQueue = failed

    if (failed.length === 0) {
      wx.showToast({ title: '离线数据已同步', icon: 'success' })
    } else {
      wx.showToast({ title: `${queue.length - failed.length}条已同步，${failed.length}条待重试`, icon: 'none' })
    }
  },

  // 添加到离线队列
  addToOfflineQueue(requestData) {
    const queue = wx.getStorageSync('offline_queue') || []
    queue.push({
      ...requestData,
      _offlineTime: Date.now(),
      _syncStatus: 'pending',
    })
    wx.setStorageSync('offline_queue', queue)
    this.globalData.offlineQueue = queue
  },

  // 权限检查
  hasPermission(permission) {
    const user = this.globalData.userInfo
    if (!user) return false
    const role = user.role_code || ''
    const adminRoles = ['super_admin', 'area_manager']
    if (adminRoles.includes(role)) return true
    // 按角色检查具体权限
    const rolePermissions = {
      breed_manager: ['pond_view', 'pond_edit', 'feed_plan', 'feed_review', 'feed_record', 'daily_ops', 'material_request', 'report_view'],
      breed_worker: ['pond_view', 'feed_record', 'daily_ops', 'material_request', 'personal_history'],
      warehouse_manager: ['material_view', 'material_edit', 'stock_in', 'stock_out', 'stock_return', 'stocktake', 'alert_handle'],
      purchaser: ['supplier_view', 'purchase_create', 'purchase_edit'],
    }
    return (rolePermissions[role] || []).includes(permission)
  },
})
