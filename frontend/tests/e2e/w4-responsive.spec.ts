import { test, expect, type Browser, type Page } from '@playwright/test'

// W4 响应式验证矩阵：320/360/375/390/414/768/1024/1920
// 运行：npx playwright test tests/e2e/w4-responsive.spec.ts --reporter=line
// 截图证据输出到 ../repair/w4_*.png（相对 frontend 工作目录）

const WIDTHS = [320, 360, 375, 390, 414, 768, 1024, 1920]
const MOBILE = [320, 360, 375, 390, 414, 768]

const EVIDENCE_DIR = '../repair'

async function newPage(browser: Browser, width: number, height = 800): Promise<Page> {
  const context = await browser.newContext({ viewport: { width, height } })
  return context.newPage()
}

async function login(page: Page, phone = '13800000000') {
  await page.goto('/auth/login')
  await page.fill('#identifier', phone)
  await page.fill('#password', 'Adp#demo-password-1')
  await page.click('button[type="submit"]')
  await page.waitForURL(/\/workbench/, { timeout: 15000 })
}

async function expectNoHorizontalOverflow(page: Page, width: number) {
  const metrics = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    inner: window.innerWidth,
  }))
  expect(metrics.doc, `document 宽度 ${metrics.doc} 超过视口 ${width}`).toBeLessThanOrEqual(width + 1)
  expect(metrics.body, `body 宽度 ${metrics.body} 超过视口 ${width}`).toBeLessThanOrEqual(width + 1)
}

test.use({ channel: 'chrome' })

test.describe('W4 响应式矩阵（截图证据 → repair/w4_*）', () => {
  for (const width of WIDTHS) {
    test(`宽度 ${width}：无横向溢出、无白屏、截图`, async ({ browser }) => {
      const page = await newPage(browser, width, 900)
      await login(page)
      await expect(page.locator('h1', { hasText: '今日工作台' })).toBeVisible()
      await page.waitForTimeout(500)
      await expectNoHorizontalOverflow(page, width)
      await page.screenshot({ path: `${EVIDENCE_DIR}/w4_${width}_workbench.png` })
      if (width === 320 || width === 390) {
        await page.goto('/ponds')
        await page.waitForSelector('.page-card')
        await page.waitForTimeout(300)
        await expectNoHorizontalOverflow(page, width)
        await page.screenshot({ path: `${EVIDENCE_DIR}/w4_${width}_ponds.png` })
        await page.goto('/warehouse/alerts')
        await page.waitForSelector('.page-card')
        await page.waitForTimeout(300)
        await expectNoHorizontalOverflow(page, width)
        await page.screenshot({ path: `${EVIDENCE_DIR}/w4_${width}_alerts.png` })
      }
      await page.context().close()
    })
  }

  test('移动端（≤768px）：侧边栏默认隐藏、汉堡抽屉可开关', async ({ browser }) => {
    const page = await newPage(browser, 375, 800)
    await login(page)
    const sidebar = page.locator('.workbench-sidebar')
    const toggle = page.locator('.mobile-nav-toggle')
    await expect(toggle).toBeVisible()
    // 默认隐藏（transform 移出视口）
    const before = await sidebar.boundingBox()
    expect(before!.x + before!.width).toBeLessThanOrEqual(1)
    // 打开抽屉
    await toggle.click()
    await page.waitForTimeout(350)
    const opened = await sidebar.boundingBox()
    expect(opened!.x).toBeGreaterThanOrEqual(-1)
    // 抽屉内导航可点击并关闭（业务模块分组默认折叠，先展开）
    await page.locator('.nav-group__head', { hasText: '塘口与批次' }).click()
    await page.locator('.side-nav a', { hasText: '塘口档案' }).first().click()
    await page.waitForURL(/\/ponds/)
    await page.waitForTimeout(350)
    const afterNav = await sidebar.boundingBox()
    expect(afterNav!.x + afterNav!.width).toBeLessThanOrEqual(1)
    await page.screenshot({ path: `${EVIDENCE_DIR}/w4_375_drawer_open.png` })
    await page.context().close()
  })

  test('移动端卡片模式：表格隐藏、卡片列表关键字段前置', async ({ browser }) => {
    const page = await newPage(browser, 390, 800)
    await login(page)
    await page.goto('/warehouse/alerts')
    await page.waitForSelector('.data-table-cards')
    await expect(page.locator('.data-table')).toBeHidden()
    const cards = page.locator('.table-card')
    await expect(cards.first()).toBeVisible()
    expect(await cards.count()).toBeGreaterThanOrEqual(2)
    const firstCard = cards.first()
    await expect(firstCard.locator('.table-card__title strong')).toHaveText('鲈鱼饲料')
    await expect(firstCard.locator('.table-card__badges')).not.toHaveCount(0)
    await expect(firstCard.locator('.table-card__fields dt').first()).toBeVisible()
    await page.screenshot({ path: `${EVIDENCE_DIR}/w4_390_alert_cards.png` })
    await page.context().close()
  })

  test('触控目标 ≥44px：表头/分页/关闭/登录tab/汉堡', async ({ browser }) => {
    const page = await newPage(browser, 320, 800)
    // 登录 tab
    await page.goto('/auth/login')
    const tab = page.locator('.auth-tabs button').first()
    const tabBox = (await tab.boundingBox())!
    expect(tabBox.height).toBeGreaterThanOrEqual(44)
    await login(page)
    // 汉堡
    const toggle = page.locator('.mobile-nav-toggle')
    const toggleBox = (await toggle.boundingBox())!
    expect(toggleBox.width).toBeGreaterThanOrEqual(44)
    expect(toggleBox.height).toBeGreaterThanOrEqual(44)
    // 分页按钮（DataTablePage 分页在库存预警页）
    await page.goto('/warehouse/alerts')
    await page.waitForSelector('.pagination-actions')
    const prev = page.locator('[data-testid="table-previous-page"]')
    const prevBox = (await prev.boundingBox())!
    expect(prevBox.width).toBeGreaterThanOrEqual(44)
    expect(prevBox.height).toBeGreaterThanOrEqual(44)
    // 弹窗关闭按钮（塘口新增弹窗）
    await page.goto('/ponds')
    await page.click('text=新增塘口')
    const close = page.locator('.modal-close')
    const closeBox = (await close.boundingBox())!
    expect(closeBox.width).toBeGreaterThanOrEqual(44)
    expect(closeBox.height).toBeGreaterThanOrEqual(44)
    await page.screenshot({ path: `${EVIDENCE_DIR}/w4_320_touch_targets.png` })
    await page.context().close()
  })

  test('弹窗宽度 ≤ min(92vw, 500px)', async ({ browser }) => {
    const page = await newPage(browser, 375, 800)
    await login(page)
    await page.goto('/ponds')
    await page.click('text=新增塘口')
    const panel = page.locator('.modal-panel').first()
    const box = (await panel.boundingBox())!
    expect(box.width).toBeLessThanOrEqual(Math.min(0.92 * 375, 500) + 1)
    await page.context().close()
  })

  test('弱网：提交失败保留输入并提示可重试，恢复后重提成功且不重复', async ({ browser }) => {
    const page = await newPage(browser, 390, 800)
    await login(page)
    await page.goto('/ponds')
    await page.click('text=新增塘口')
    await page.fill('[data-testid="pond-name"]', '弱网测试塘')
    await page.fill('[data-testid="pond-code"]', 'P-WEAK-01')
    await page.selectOption('[data-testid="pond-area"]', '1')
    // 断网：拦截保存请求
    await page.route('**/api/v1/master-data/ponds', (route) => {
      if (route.request().method() === 'POST') route.abort('failed')
      else route.continue()
    })
    await page.click('[data-testid="pond-save"]')
    await expect(page.locator('.modal-error')).toContainText('提交失败，内容已保留，可重试')
    // 表单值保留
    await expect(page.locator('[data-testid="pond-name"]')).toHaveValue('弱网测试塘')
    await expect(page.locator('[data-testid="pond-code"]')).toHaveValue('P-WEAK-01')
    // 网络恢复后重提成功
    let postCount = 0
    await page.unroute('**/api/v1/master-data/ponds')
    page.on('request', (req) => {
      if (req.url().includes('/api/v1/master-data/ponds') && req.method() === 'POST') postCount += 1
    })
    await page.click('[data-testid="pond-save"]')
    await expect(page.locator('.modal-overlay')).toHaveCount(0)
    expect(postCount).toBe(1)
    await page.screenshot({ path: `${EVIDENCE_DIR}/w4_390_offline_retained.png` })
    await page.context().close()
  })

  test('防重复提交：连点保存仅发出一次 POST', async ({ browser }) => {
    const page = await newPage(browser, 390, 800)
    await login(page)
    await page.goto('/ponds')
    await page.click('text=新增塘口')
    await page.fill('[data-testid="pond-name"]', '防重复塘')
    await page.fill('[data-testid="pond-code"]', 'P-DUP-01')
    await page.selectOption('[data-testid="pond-area"]', '1')
    let postCount = 0
    page.on('request', (req) => {
      if (req.url().includes('/api/v1/master-data/ponds') && req.method() === 'POST') postCount += 1
    })
    await page.locator('[data-testid="pond-save"]').dblclick()
    await expect(page.locator('.modal-overlay')).toHaveCount(0)
    await page.waitForTimeout(400)
    expect(postCount).toBe(1)
    await page.context().close()
  })

  test('库存预警"处理"按钮：无 warehouse.manage 权限时隐藏', async ({ browser }) => {
    const page = await newPage(browser, 768, 900)
    await login(page, '13900000002')
    await page.goto('/warehouse/alerts')
    await page.waitForSelector('.page-card')
    await expect(page.locator('[data-testid="warehouse-alert-action-handle"]')).toHaveCount(0)
    await page.screenshot({ path: `${EVIDENCE_DIR}/w4_768_alert_no_handle.png` })
    await page.context().close()
  })

  test('塘口扩展字段：表单字段、来源下拉、提交载荷与详情来源标识', async ({ browser }) => {
    const page = await newPage(browser, 414, 900)
    await login(page)
    await page.goto('/ponds')
    await page.click('text=新增塘口')
    for (const testId of ['pond-aerator_count', 'pond-stocking_spec', 'pond-current_spec', 'pond-stock_quantity', 'pond-stock_quantity_source']) {
      await expect(page.locator(`[data-testid="${testId}"]`)).toBeVisible()
    }
    await page.fill('[data-testid="pond-name"]', '扩展字段塘')
    await page.fill('[data-testid="pond-code"]', 'P-EXT-01')
    await page.selectOption('[data-testid="pond-area"]', '1')
    await page.fill('[data-testid="pond-aerator_count"]', '6')
    await page.fill('[data-testid="pond-stocking_spec"]', '5cm/尾')
    await page.fill('[data-testid="pond-current_spec"]', '400g/尾')
    await page.fill('[data-testid="pond-stock_quantity"]', '8000')
    await page.selectOption('[data-testid="pond-stock_quantity_source"]', 'manual_entry')
    let postBody: Record<string, unknown> = {}
    const bodyPromise = page.waitForRequest((req) => req.url().includes('/api/v1/master-data/ponds') && req.method() === 'POST')
    await page.click('[data-testid="pond-save"]')
    const request = await bodyPromise
    postBody = request.postDataJSON() as Record<string, unknown>
    expect(postBody).toMatchObject({
      name: '扩展字段塘', code: 'P-EXT-01', aerator_count: 6, stocking_spec: '5cm/尾',
      current_spec: '400g/尾', stock_quantity: 8000, stock_quantity_source: 'manual_entry',
    })
    await expect(page.locator('.modal-overlay')).toHaveCount(0)
    // 详情页来源标识
    await page.goto('/ponds/1')
    await page.waitForSelector('[data-testid="pond-stock-source"]')
    await expect(page.locator('[data-testid="pond-stock-source"]')).toHaveText('抽样')
    await expect(page.locator('[data-testid="pond-stock-quantity"]')).toContainText('12,000')
    await page.screenshot({ path: `${EVIDENCE_DIR}/w4_414_pond_extended.png` })
    await page.context().close()
  })

  test('工作台：待办超时为真实计算；预警标注口径', async ({ browser }) => {
    const page = await newPage(browser, 1024, 900)
    await login(page)
    await page.waitForSelector('[data-testid="kpi-ponds"]')
    // stub 数据两条待办均超时 → 真实计算为 2
    await expect(page.locator('.kpi-card', { hasText: '我的待办' })).toContainText('其中 2 项已超过处理时限')
    // 预警卡片口径标注
    await expect(page.locator('.section-head', { hasText: '预警与消息' })).toContainText('口径：消息中心汇总')
    await page.screenshot({ path: `${EVIDENCE_DIR}/w4_1024_workbench_metrics.png` })
    await page.context().close()
  })

  test('桌面 1920 基线对比截图（after）', async ({ browser }) => {
    const page = await newPage(browser, 1920, 1080)
    await login(page)
    await page.waitForTimeout(600)
    await page.screenshot({ path: `${EVIDENCE_DIR}/w4_after_1920_workbench.png` })
    await page.goto('/ponds')
    await page.waitForTimeout(400)
    await page.screenshot({ path: `${EVIDENCE_DIR}/w4_after_1920_ponds.png` })
    await page.goto('/warehouse/alerts')
    await page.waitForTimeout(400)
    await page.screenshot({ path: `${EVIDENCE_DIR}/w4_after_1920_alerts.png` })
    await page.context().close()
  })
})
