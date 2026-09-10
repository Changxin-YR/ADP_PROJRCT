import { expect, test } from '@playwright/test'

test.describe('域名切换真实登录验收', () => {
  test.skip(
    !process.env.DOMAIN_CUTOVER_IDENTIFIER || !process.env.DOMAIN_CUTOVER_PASSWORD,
    '需要通过环境变量提供一次性验收账号',
  )

  test('登录页可见并能完成真实登录进入工作台', async ({ page }) => {
    await page.goto('auth/login')
    await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
    await page.locator('#identifier').fill(process.env.DOMAIN_CUTOVER_IDENTIFIER!)
    await page.locator('#password').fill(process.env.DOMAIN_CUTOVER_PASSWORD!)
    await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()
    await expect(page).toHaveURL(/\/(?:adp\/)?workbench\/?$/)
    await expect(page.getByRole('heading', { name: '今日工作台' })).toBeVisible()
  })
})
