import { expect, test, type Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/auth/login')
  await page.waitForLoadState('networkidle')
  if (await page.locator('#identifier').count() === 0) {
    await expect(page).toHaveURL(/\/workbench$/)
    return
  }
  await page.locator('#identifier').fill('13800000000')
  await page.locator('#password').fill('AnyPass9!')
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/workbench$/)
}

test.describe('窄屏布局回归', () => {
  test('业务页面不应产生视口横向溢出', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await login(page)

    for (const path of ['/workbench', '/ponds', '/batches', '/feeding/plans', '/warehouse/materials', '/purchase/orders', '/sales/orders', '/cost/expenses', '/data/templates']) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      await expect(page.getByRole('alert')).toHaveCount(0)
      await expect(page.locator('.workbench-main')).toBeVisible()
      const dimensions = await page.evaluate(() => ({ innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth }))
      console.log(`${path}: ${JSON.stringify(dimensions)}`)
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { timeout: 5000 }).toBe(true)
    }
  })

  test('移动导航支持焦点、Escape 和路由关闭', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await login(page)

    const toggle = page.getByRole('button', { name: '打开导航' })
    await toggle.click()
    await expect(page.getByRole('button', { name: '关闭导航' }).first()).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: '打开导航' })).toBeVisible()

    await toggle.click()
    await page.locator('nav[aria-label="主导航"] a').click()
    await expect(page.locator('.workbench-sidebar')).not.toHaveClass(/is-mobile-open/)
  })
})
