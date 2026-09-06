const app = getApp()

Page({
  data: {
    isOnline: true,
    form: {
      pondId: '',
      pondName: '',
      time: '',
      waterColor: '',
      transparency: '',
      waterTemp: '',
      ph: '',
      fishBehavior: '',
      severity: '',
      equipmentStatus: '',
      remark: '',
    },
    photos: [],
    hasAbnormal: false,
    behaviorOptions: [
      { label: '正常', value: 'normal' },
      { label: '浮头', value: 'floating' },
      { label: '跳跃', value: 'jumping' },
      { label: '聚堆', value: 'clustering' },
      { label: '游边', value: 'edging' },
    ],
    abnormalOptions: [
      { label: '无异常', value: 'none', selected: true },
      { label: '死鱼', value: 'dead_fish', selected: false },
      { label: '水质恶化', value: 'water_bad', selected: false },
      { label: '设备故障', value: 'equip_fail', selected: false },
      { label: '病害迹象', value: 'disease', selected: false },
    ],
    severityOptions: [
      { label: '轻微', value: 'low' },
      { label: '中等', value: 'medium' },
      { label: '严重', value: 'high' },
    ],
    equipmentOptions: [
      { label: '正常', value: 'normal' },
      { label: '需维修', value: 'repair' },
      { label: '已停机', value: 'stopped' },
    ],
  },

  onLoad(options) {
    const now = new Date()
    const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
    this.setData({ 'form.time': time })

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

  onTimeChange(e) {
    this.setData({ 'form.time': e.detail.value })
  },

  onInput(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ [`form.${field}`]: e.detail.value })
  },

  selectBehavior(e) {
    this.setData({ 'form.fishBehavior': e.currentTarget.dataset.value })
  },

  toggleAbnormal(e) {
    const index = e.currentTarget.dataset.index
    const opts = [...this.data.abnormalOptions]
    if (index === 0) {
      opts.forEach((o, i) => { o.selected = i === 0 })
    } else {
      opts[0].selected = false
      opts[index].selected = !opts[index].selected
      if (!opts.some((o, i) => i > 0 && o.selected)) {
        opts[0].selected = true
      }
    }
    const hasAbnormal = !opts[0].selected
    this.setData({ abnormalOptions: opts, hasAbnormal })
  },

  selectSeverity(e) {
    this.setData({ 'form.severity': e.currentTarget.dataset.value })
  },

  selectEquipment(e) {
    this.setData({ 'form.equipmentStatus': e.currentTarget.dataset.value })
  },

  addPhoto() {
    wx.chooseMedia({
      count: 9 - this.data.photos.length,
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      success: (res) => {
        const newPhotos = res.tempFiles.map(f => f.tempFilePath)
        this.setData({ photos: [...this.data.photos, ...newPhotos] })
      },
    })
  },

  previewPhoto(e) {
    wx.previewImage({ current: e.currentTarget.dataset.url, urls: this.data.photos })
  },

  deletePhoto(e) {
    const photos = [...this.data.photos]
    photos.splice(e.currentTarget.dataset.index, 1)
    this.setData({ photos })
  },

  async submitPatrol() {
    const { form, photos, abnormalOptions } = this.data
    if (!form.pondId) return wx.showToast({ title: '请选择塘口', icon: 'none' })

    wx.showLoading({ title: '提交中' })

    const abnormals = abnormalOptions.filter(o => o.selected && o.value !== 'none').map(o => o.value)

    try {
      const payload = {
        code: `WX-PATROL-${Date.now()}`,
        name: '微信巡塘记录',
        pond_id: form.pondId,
        happened_at: `${this.formatToday()}T${form.time}:00`,
        note: form.remark,
        payload: {
          water_color: form.waterColor,
          transparency: form.transparency ? parseFloat(form.transparency) : null,
          water_temp: form.waterTemp ? parseFloat(form.waterTemp) : null,
          ph: form.ph ? parseFloat(form.ph) : null,
          fish_behavior: form.fishBehavior,
          abnormalities: abnormals,
          severity: form.severity,
          equipment_status: form.equipmentStatus,
        },
      }

      const res = await app.request({ url: '/production/daily-operations', method: 'POST', data: payload })

      if (res.success && photos.length > 0) {
        for (const photo of photos) {
          await new Promise((resolve, reject) => {
            wx.uploadFile({
              url: `${app.globalData.baseUrl}/data-exchange/attachments`,
              filePath: photo,
              name: 'file',
              formData: {
                organization_id: this.organizationId(),
                entity_type: 'production:daily-operations',
                entity_id: res.data.id,
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
        }
      }

      wx.hideLoading()
      wx.showToast({ title: '提交成功', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 1000)
    } catch (e) {
      wx.hideLoading()
      if (!this.data.isOnline) {
        app.addToOfflineQueue({ type: 'patrol', data: { ...form, photos, abnormals } })
        wx.showToast({ title: '已保存至离线队列', icon: 'none' })
        setTimeout(() => wx.navigateBack(), 1000)
      } else {
        wx.showToast({ title: '提交失败', icon: 'none' })
      }
    }
  },

  formatToday() {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  },

  organizationId() {
    const user = app.globalData.userInfo || {}
    return user.organization_id || (user.data_scopes || []).find(scope => scope.organization_id)?.organization_id || ''
  },
})
