module.exports = {
  // 生产入口已从 IP 直连改为共享域名，且只接受 Host=23331.cloud。
  // 用 IP 访问会被 Nginx 直接断开，因此这里必须是域名。
  // 另需在微信公众平台把 23331.cloud 加入 request 合法域名。
  baseUrl: 'https://23331.cloud/adp/api/v1',
  version: '1.0.0',
  sessionKey: 'session_token',
  offlineQueueKey: 'offline_queue',
  cachePrefix: 'adp_cache_',
  requestTimeout: 15000,
  maxPhotoCount: 9,
  maxPhotoSize: 5 * 1024 * 1024,
  photoCompressQuality: 80,
}
