import { expect, test, type Page } from '@playwright/test'

async function expectNoHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
}

test('成本构成支持来源追溯并保存新分摊版本', async ({ page }) => {
  await page.goto('/auth/login')
  await page.locator('#identifier').fill('admin')
  await page.locator('#password').fill('FarmPass9!')
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()

  await expect(page).toHaveURL(/\/workbench$/)
  await page.getByRole('button', { name: /成本与经营/ }).click()
  await page.getByRole('link', { name: '成本构成' }).click()
  await expect(page).toHaveURL(/\/cost\/structure$/)
  await expect(page.getByTestId('cost-total')).toContainText('672,000.00')
  await expect(page.getByTestId('cost-unit-cost')).toContainText('待接入产量')
  await expect(page.getByText(/当前规则 v1.*系统管理员/)).toBeVisible()
  await expectNoHorizontalOverflow(page)

  await page.getByTestId('cost-row-feed').click()
  await expect(page.getByTestId('cost-entry-drawer')).toContainText('LEGACY-INIT-2026')
  await page.getByRole('button', { name: '关闭来源明细' }).click()

  await page.getByTestId('open-allocation-rules').click()
  await page.locator('#allocation-reason').fill('端到端核验新的公共成本口径')
  await page.getByTestId('save-allocation-rules').click()
  await expect(page.getByText('规则版本 v2 已保存')).toBeVisible()
  await page.reload()
  await expect(page.getByText(/当前规则 v1/)).toBeVisible()
  await expect(page.getByText(/待生效规则 v2/)).toBeVisible()
  await expect(page.getByText(/待生效规则 v2.*系统管理员/)).toBeVisible()

  await page.setViewportSize({ width: 1440, height: 900 })
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: 'test-results/cost-accounting-desktop.png' })
  await page.setViewportSize({ width: 1024, height: 768 })
  await expectNoHorizontalOverflow(page)
})
