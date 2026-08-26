import { defineConfig } from '@playwright/test'

// W4 专用运行配置：独立端口（stub 5012 + vite 5176），不干扰主配置的 5173/5011
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: /w4-responsive\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: [['line']],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5176',
    channel: 'chrome',
    trace: 'retain-on-failure',
    launchOptions: {
      args: ['--disable-gpu', '--disable-dev-shm-usage', '--no-sandbox', '--disable-extensions'],
    },
  },
  webServer: [
    {
      command: 'python -u tests/e2e/full_stub.py --port 5012',
      url: 'http://127.0.0.1:5012/api/v1/health',
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5176',
      url: 'http://127.0.0.1:5176/auth/login',
      reuseExistingServer: false,
      env: { VITE_API_PROXY_TARGET: 'http://127.0.0.1:5012' },
    },
  ],
})
