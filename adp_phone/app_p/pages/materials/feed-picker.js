const app = getApp()
Page({
  data: { keyword: '', feeds: [], filteredFeeds: [] },
  onLoad() { this.eventChannel = this.getOpenerEventChannel(); this.loadFeeds() },
  async loadFeeds() {
    try {
      const res = await app.request({ url: '/master-data/materials', method: 'GET' })
      if (res.success) { const feeds = res.data.items || []; this.setData({ feeds, filteredFeeds: feeds }) }
    } catch (e) {
      const cached = wx.getStorageSync('feeds_cache') || []
      this.setData({ feeds: cached, filteredFeeds: cached })
    }
  },
  onSearch(e) {
    const kw = e.detail.value.toLowerCase()
    this.setData({ keyword: kw, filteredFeeds: this.data.feeds.filter(f => f.name.toLowerCase().includes(kw)) })
  },
  selectFeed(e) {
    const feed = e.currentTarget.dataset.feed
    if (this.eventChannel) this.eventChannel.emit('onFeedSelected', { id: feed.id, name: feed.name, unit: feed.unit })
    wx.navigateBack()
  },
})
