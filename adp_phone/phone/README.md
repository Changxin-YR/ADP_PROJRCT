# ADP 移动 App（Expo / React Native）

本目录是 ADP 最新独立移动 App 源码，技术栈为 Expo 57、React Native 0.86、React 19 与 TypeScript 6。它与桌面 `ADP` 工程共用 Flask API、权限规则与业务数据。

## 功能范围

- 登录、注册审核、改密、个人中心、通知与工作台。
- 塘口、批次、抽样、损耗、调塘、捕捞、投喂计划与记录、日常作业。
- 物料、入出库、退库、盘点、报损、调拨与库存预警。
- 采购、供应商、销售、客户、成本与数据交换。
- 安全存储移动会话、离线请求队列、联网后同步、照片与文件选择。

## 配置与运行

复制环境变量示例并填写可从设备访问的 HTTPS 后端地址：

```powershell
Copy-Item .env.example .env.local
npm ci
npm run check
npm run test:android
```

应用使用静态可内联的 `EXPO_PUBLIC_API_BASE_URL`，默认示例为 `https://23331.cloud/adp`（共享域名部署，API 实际位于 `/adp/api/v1`）。IP 直连入口已下线，用 IP 会被 Nginx 断开。不要在 `EXPO_PUBLIC_` 变量中存放密码或密钥。

## 验证命令

```powershell
npx expo install --check
npm run check
npm run export:android
```

2026-08-24 已完成 Expo 依赖兼容检查、TypeScript 检查、31 项 API 契约检查、Android 静态导出，以及 Android 37 x86_64 模拟器上的登录/注册页面真实渲染和无错误热重载。运行安卓模拟器时，`ANDROID_SDK_ROOT` 与 `ANDROID_HOME` 应指向实际完整 SDK；本机使用 `C:\Users\27363\AppData\Local\Android\Sdk`。
