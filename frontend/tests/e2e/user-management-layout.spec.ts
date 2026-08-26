import { expect, test, type Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/auth/login')
  await page.waitForLoadState('networkidle')
  if ((await page.locator('#identifier').count()) === 0) {
    await expect(page).toHaveURL(/\/workbench$/)
    return
  }
  await page.locator('#identifier').fill('13800000000')
  await page.locator('#password').fill('AnyPass9!')
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/workbench$/)
}

test.describe('账号管理列表布局', () => {
  test('账号行使用稳定的三列布局，第二列起点一致', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 })
    await login(page)
    await page.goto('/admin/users')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('.user-row').first()).toBeVisible()
    expect(await page.locator('.user-row .user-identity').count()).toBeGreaterThan(0)
    expect(await page.locator('.user-row .user-meta').count()).toBeGreaterThan(0)
    const grid = await page.locator('.user-row').first().evaluate((el) => getComputedStyle(el).gridTemplateColumns)
    const columns = grid.split(' ').filter(Boolean)
    expect(columns.length).toBeGreaterThanOrEqual(3)
    const starts = await page.locator('.user-row .user-meta').evaluateAll((els) => els.map((el) => el.getBoundingClientRect().left))
    expect(Math.max(...starts) - Math.min(...starts)).toBeLessThan(2)
  })

  test('中等屏幕操作区换行，手机端单列且无横向溢出', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 900 })
    await login(page)
    await page.goto('/admin/users')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('.user-row').first()).toBeVisible()
    const actions = page.locator('.user-row .user-actions').first()
    const meta = page.locator('.user-row .user-meta').first()
      const metaBox = await meta.boundingBox()
      const actionBox = await actions.boundingBox()
      expect(metaBox).not.toBeNull()
      expect(actionBox).not.toBeNull()
      expect(actionBox!.y).toBeGreaterThanOrEqual(metaBox!.y + metaBox!.height - 1)

    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/admin/users')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('.user-row').first()).toBeVisible()
    const columns = await page.locator('.user-row').first().evaluate((el) => getComputedStyle(el).gridTemplateColumns)
    expect(columns.split(' ').filter(Boolean).length).toBe(1)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { timeout: 5000 }).toBe(true)
  })
})
