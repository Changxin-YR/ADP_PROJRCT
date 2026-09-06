const app = getApp()

Page({
  data: {
    isOnline: true,
    form: {
      pondId: '',
      pondName: '',
      feedId: '',
      feedName: '',
      amount: '',
      unit: 'kg',
      time: '',
      weather: '',
      eatingStatus: '',
      remark: '',
    },
    planAmount: null,
    deviationPercent: 0,
    photos: [],
    weatherOptions: ['晴', '多云', '阴', '小雨', '大雨', '闷热'],
    eatingOptions: [
      { label: '正常', value: 'normal' },
      { label: '偏少', value: 'less' },
      { label: '偏多', value: 'more' },
      { label: '不吃', value: 'none' },
    ],
    taskId: null,
  },

  onLoad(options) {
    const now = new Date()
    const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
    this.setData({ 'form.time': time })

    if (options.taskId) {
      this.setData({ taskId: options.taskId })
      this.loadTaskInfo(options.taskId)
    }

    if (options.photos) {
      try {
        const photos = JSON.parse(decodeURIComponent(options.photos))
        this.setData({ photos })
      } catch (e) {}
    }
  },

  onShow() {
    this.setData({ isOnline: app.globalData.isOnline })
  },

  formatToday() {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  },

  async loadTaskInfo(taskId) {
    try {
      const res = await app.request({ url: `/production/feed-tasks/${taskId}`, method: 'GET' })
      if (res.success) {
        const task = res.data
        this.setData({
          'form.pondId': task.pond_id,
          'form.pondName': task.pond_name,
          'form.feedId': task.material_id || task.feed_id,
          'form.feedName': task.material_name || task.feed_name,
          'form.unit': task.unit || 'kg',
          planAmount: task.quantity || task.planned_amount,
        })
      }
    } catch (e) {}
  },

  selectPond() {
    wx.navigateTo({
      url: '/pages/ponds/picker?mode=select',
      events: {
        onPondSelected: (data) => {
          this.setData({
            'form.pondId': data.id,
            'form.pondName': data.name,
          })
        },
      },
    })
  },

  selectFeedType() {
    wx.navigateTo({
      url: '/pages/materials/feed-picker',
      events: {
        onFeedSelected: (data) => {
          this.setData({
            'form.feedId': data.id,
            'form.feedName': data.name,
            'form.unit': data.unit || 'kg',
          })
        },
      },
    })
  },

  onAmountChange(e) {
    const amount = e.detail.value
    this.setData({ 'form.amount': amount })
    if (this.data.planAmount && amount) {
      const deviation = ((parseFloat(amount) - this.data.planAmount) / this.data.planAmount * 100).toFixed(1)
      this.setData({ deviationPercent: deviation })
    }
  },

  onTimeChange(e) {
    this.setData({ 'form.time': e.detail.value })
  },

  selectWeather(e) {
    this.setData({ 'form.weather': e.currentTarget.dataset.value })
  },

  selectEating(e) {
    this.setData({ 'form.eatingStatus': e.currentTarget.dataset.value })
  },

  onRemarkChange(e) {
    this.setData({ 'form.remark': e.detail.value })
  },

  addPhoto() {
    wx.chooseMedia({
      count: 6 - this.data.photos.length,
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      success: (res) => {
        const newPhotos = res.tempFiles.map(f => f.tempFilePath)
        this.setData({ photos: [...this.data.photos, ...newPhotos] })
      },
    })
  },

  previewPhoto(e) {
    wx.previewImage({
      current: e.currentTarget.dataset.url,
      urls: this.data.photos,
    })
  },

  deletePhoto(e) {
    const index = e.currentTarget.dataset.index
    const photos = [...this.data.photos]
    photos.splice(index, 1)
    this.setData({ photos })
  },

  async submitRecord() {
    const { form, photos, taskId } = this.data

    if (!form.pondId) return wx.showToast({ title: '请选择塘口', icon: 'none' })
    if (!form.feedId) return wx.showToast({ title: '请选择饲料', icon: 'none' })
    if (!form.amount) return wx.showToast({ title: '请输入投喂量', icon: 'none' })

    wx.showLoading({ title: '提交中' })

    try {
      const payload = {
        code: `WX-FEED-${Date.now()}`,
        name: '微信投喂记录',
        pond_id: form.pondId,
        material_id: form.feedId,
        quantity: parseFloat(form.amount),
        happened_at: `${this.formatToday()}T${form.time}:00`,
        feed_task_id: taskId || undefined,
        note: form.remark,
        payload: { unit: form.unit, weather: form.weather, eating_status: form.eatingStatus },
      }

      const res = await app.request({ url: '/production/feed-logs', method: 'POST', data: payload })

      if (res.success && photos.length > 0) {
        for (const photo of photos) {
          await this.uploadPhoto(res.data.id, photo)
        }
      }

      wx.hideLoading()
      wx.showToast({ title: '提交成功', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 1000)
    } catch (e) {
      wx.hideLoading()
      if (!this.data.isOnline) {
        app.addToOfflineQueue({
          type: 'feeding_record',
          data: { ...form, photos },
        })
        wx.showToast({ title: '已保存至离线队列', icon: 'none' })
        setTimeout(() => wx.navigateBack(), 1000)
      } else {
        wx.showToast({ title: '提交失败', icon: 'none' })
      }
    }
  },

  async uploadPhoto(recordId, filePath) {
    return new Promise((resolve, reject) => {
      wx.uploadFile({
        url: `${app.globalData.baseUrl}/data-exchange/attachments`,
        filePath,
        name: 'file',
        formData: {
          organization_id: this.organizationId(),
          entity_type: 'production:feed-logs',
          entity_id: recordId,
        },
        header: {
          'X-ADP-Client': 'mobile',
          ...(app.globalData.csrfToken ? { 'X-CSRF-Token': app.globalData.csrfToken } : {}),
          ...(app.globalData.sessionToken ? { Cookie: `adp_session=${app.globalData.sessionToken}` } : {}),
        },
        success: resolve,
        fail: reject,
      })
    })
  },

  organizationId() {
    const user = app.globalData.userInfo || {}
    return user.organization_id || (user.data_scopes || []).find(scope => scope.organization_id)?.organization_id || ''
  },
})
