import { expect, test, type Page } from '@playwright/test'

// 塘小助 澄清提问 / 确认执行 的浏览器级回归：后端走 tests/e2e/full_stub.py（playwright.config.ts 自动拉起）

type AgentProbe = { messages: string[]; turns: number; conversation_ids?: string[] }

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

test.describe('塘小助 澄清提问与确认执行', () => {
  test('信息不足先提问、选项回填同一会话、写入需确认', async ({ page }) => {
    await login(page)
    await page.goto('/workbench')
    await expect(page.locator('h1', { hasText: '今日工作台' })).toBeVisible()

    const launcher = page.getByRole('button', { name: '打开塘小助' })
    await expect(launcher).toBeVisible()
    await launcher.click()

    const composer = page.getByLabel('塘小助指令')
    await composer.fill('查询我的权限')
    await page.getByRole('button', { name: '发送指令' }).click()

    // ① 信息不足 → 弹出提问区（问题 + 可点选项 + 自由输入框）
    const clarification = page.getByTestId('agent-clarification')
    await expect(clarification).toBeVisible()
    await expect(clarification).toContainText('要查询哪个塘口？')
    const options = page.getByTestId('agent-clarification-option')
    await expect(options).toHaveCount(2)
    await expect(options).toHaveText(['1 号塘', '2 号塘'])
    await expect(page.getByTestId('agent-clarification-input')).toBeVisible()

    // ② 点选项 → 提问区消失、助手回复出现；答案作为下一轮消息且 conversation_id 不变
    await options.first().click()
    await expect(page.getByTestId('agent-clarification')).toHaveCount(0)
    await expect(page.getByText('好的，正在查询 1 号塘。').first()).toBeVisible()

    const probe = await page.request.get('/api/v1/agent/_probe')
    expect(probe.ok()).toBeTruthy()
    const payload = await probe.json() as { data: AgentProbe }
    expect(payload.data.turns).toBeGreaterThanOrEqual(1)
    expect(payload.data.messages.slice(-2)).toEqual(['查询我的权限', '1 号塘'])
    const ids = payload.data.conversation_ids ?? []
    expect(ids.length).toBeGreaterThanOrEqual(2)
    expect(ids[ids.length - 1]).toBe(ids[ids.length - 2])

    // ③ 写入类操作 → 确认执行卡片，确认后卡片消失
    await composer.fill('投喂 20kg')
    await page.getByRole('button', { name: '发送指令' }).click()
    const confirmation = page.getByTestId('agent-confirmation')
    await expect(confirmation).toBeVisible()
    await expect(confirmation).toContainText('投喂 20kg')
    await page.getByTestId('agent-confirm').click()
    await expect(page.getByTestId('agent-confirmation')).toHaveCount(0)
  })
})
