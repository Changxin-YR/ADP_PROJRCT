const app = getApp()

Page({
  data: {
    loading: true,
    activeTab: 'all',
    messages: [],
    unreadCount: 0,
  },

  onLoad(options) {
    if (options.tab) this.setData({ activeTab: options.tab })
  },

  onShow() {
    this.loadMessages()
  },

  onPullDownRefresh() {
    this.loadMessages().then(() => wx.stopPullDownRefresh())
  },

  switchTab(e) {
    this.setData({ activeTab: e.currentTarget.dataset.tab })
    this.loadMessages()
  },

  async loadMessages() {
    this.setData({ loading: true })
    try {
      const includeNotifications = this.data.activeTab !== 'tasks'
      const includeTasks = this.data.activeTab === 'all' || this.data.activeTab === 'tasks'
      const [notificationRes, taskRes] = await Promise.all([
        includeNotifications ? app.request({ url: '/notifications', method: 'GET', data: { page: 1, page_size: 100, include_history: true } }) : null,
        includeTasks ? app.request({ url: '/work-items', method: 'GET', data: { page: 1, page_size: 100 } }) : null,
      ])
      const notifications = notificationRes && notificationRes.success ? (notificationRes.data.items || []).map(item => ({
        ...item,
        source: 'notification',
        type: ['high', 'critical'].includes(item.level) ? 'alerts' : 'system',
        content: item.body || item.detail || '',
        read: item.status !== 'unread',
        created_at: item.last_occurred_at || item.created_at,
      })) : []
      const tasks = taskRes && taskRes.success ? (taskRes.data.items || []).map(item => ({
        ...item,
        source: 'work-item',
        type: 'tasks',
        content: item.detail || '',
        read: item.status !== 'pending',
        created_at: item.due_at || item.created_at,
      })) : []
      const activeTab = this.data.activeTab
      const messages = [...notifications, ...tasks]
        .filter(item => activeTab === 'all' || item.type === activeTab)
        .map(this.formatMessage)
      const unreadCount = messages.filter(item => !item.read).length
      wx.setStorageSync('messages_cache', messages)
      this.setData({ messages, unreadCount })
    } catch (e) {
      const cached = wx.getStorageSync('messages_cache')
      if (cached) this.setData({ messages: cached })
    } finally {
      this.setData({ loading: false })
    }
  },

  formatMessage(msg) {
    const iconMap = {
      alerts: '⚠️',
      tasks: '📋',
      system: '🔔',
    }
    const now = new Date()
    const msgTime = new Date(msg.created_at)
    const diff = now - msgTime
    let timeStr = ''
    if (diff < 3600000) timeStr = `${Math.floor(diff / 60000)}分钟前`
    else if (diff < 86400000) timeStr = `${Math.floor(diff / 3600000)}小时前`
    else timeStr = `${msgTime.getMonth() + 1}/${msgTime.getDate()}`

    return {
      ...msg,
      icon: iconMap[msg.type] || '📨',
      timeStr,
    }
  },

  async openMessage(e) {
    const id = e.currentTarget.dataset.id
    const messages = [...this.data.messages]
    const idx = messages.findIndex(m => m.id === id)
    if (idx >= 0 && !messages[idx].read) {
      messages[idx].read = true
      this.setData({ messages, unreadCount: this.data.unreadCount - 1 })
      if (messages[idx].source === 'notification') {
        app.request({ url: `/notifications/${id}`, method: 'PATCH', data: { status: 'read' } }).catch(() => {})
      }
    }
  },
})
