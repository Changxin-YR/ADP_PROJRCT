import { expect, test, type Page } from '@playwright/test'

async function mockUnauthenticatedSession(page: Page) {
  await page.route('**/api/v1/auth/me', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ code: 'UNAUTHENTICATED', message: '未登录', data: null, request_id: 'e2e' }),
    })
  })
}

test.describe('登录注册浏览器验收', () => {
  test('桌面端显示登录表单并可进入注册页', async ({ page }) => {
    await mockUnauthenticatedSession(page)
    await page.goto('/auth/login')
    await page.waitForLoadState('networkidle')

    await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
    await expect(page.locator('#identifier')).toBeVisible()
    await expect(page.locator('#password')).toBeVisible()
    await expect(page.locator('form').getByRole('button', { name: '登录', exact: true })).toBeVisible()

    await page.getByRole('link', { name: '申请加入' }).click()
    await expect(page).toHaveURL(/\/auth\/register$/)
    await expect(page.getByRole('heading', { name: '申请注册' })).toBeVisible()
    await expect(page.locator('#register-role')).toBeVisible()
    await expect(page.locator('#register-area')).toBeVisible()
    await page.screenshot({ path: 'test-results/login-register-desktop.png', fullPage: true })
  })

  test('窄屏端仍保留注册申请的关键字段', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await mockUnauthenticatedSession(page)
    await page.goto('/auth/register')
    await page.waitForLoadState('networkidle')

    await expect(page.getByRole('heading', { name: '申请注册' })).toBeVisible()
    await expect(page.locator('#register-phone')).toBeVisible()
    await expect(page.locator('#register-name')).toBeVisible()
    await expect(page.getByRole('button', { name: '提交注册申请' })).toBeVisible()
    await page.screenshot({ path: 'test-results/register-mobile.png', fullPage: true })
  })
})
