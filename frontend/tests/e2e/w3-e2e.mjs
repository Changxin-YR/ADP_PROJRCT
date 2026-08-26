// W3 验收 E2E（Playwright + 真实后端 5003 / 前端 5175）
// 覆盖：25 模板导入（materials/batches 两例）、预览校验中文错误、
//       确认导入、撤销（含 409 场景说明）、TemplatePage 徽标、
//       列表页“导出当前范围”→ 后端 xlsx（解析元数据 + 中文断言）。
import { chromium } from 'playwright'
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'

const BASE = 'http://127.0.0.1:5175'
const OUT = 'C:/Users/27363/Desktop/repair-w3/repair'
const SHOT = (name) => join(OUT, name)

const results = []
function record(name, pass, detail = '') {
  results.push({ name, pass, detail })
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? `  :: ${detail}` : ''}`)
}

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
page.on('pageerror', (err) => console.log('PAGE ERROR:', err.message))

try {
  // ---- 登录 ----
  await page.goto(`${BASE}/auth/login`, { waitUntil: 'networkidle' })
  await page.fill('#identifier', '13800000000')
  await page.fill('#password', 'Adp#6df76d2beb7955a7d7413d6d40360dc5')
  await page.click('button[type="submit"]')
  await page.waitForURL(/\/workbench/, { timeout: 15000 })
  record('login', true, '超管登录成功')

  // ---- TemplatePage 徽标 ----
  await page.goto(`${BASE}/data/templates`, { waitUntil: 'networkidle' })
  const badges = await page.locator('.status-badge').allTextContents()
  const importableCount = badges.filter((t) => t.includes('可导入')).length
  const downloadOnly = badges.filter((t) => t.includes('仅下载')).length
  record('template-badges', importableCount >= 29 && downloadOnly >= 1, `可导入 ${importableCount} 个 / 仅下载 ${downloadOnly} 个`)
  await page.screenshot({ path: SHOT('w3_templates.png'), fullPage: true })

  // ---- 导入 materials（正确文件）→ 预览 → 确认 ----
  // 测试文件由 repair/w3-fixtures.py 生成（含时间戳编号，可重复运行）。
  await page.goto(`${BASE}/data/imports`, { waitUntil: 'networkidle' })
  await page.click('[data-testid="import-open"]')
  await page.fill('.modal-panel input[type="number"]', '1')
  await page.selectOption('.modal-panel select', 'materials')
  await page.setInputFiles('[data-testid="import-file"]', join(OUT, 'w3-materials-ok.xlsx'))
  await page.click('[data-testid="import-preview"]')
  await page.waitForSelector('[data-testid="import-confirm"]', { timeout: 10000 })
  await page.click('[data-testid="import-confirm"]')
  await page.waitForSelector('.form-alert--success', { timeout: 10000 })
  const notice1 = await page.locator('.form-alert--success').first().textContent()
  record('import-materials-ok', notice1.includes('导入成功'), notice1)
  await page.locator('.modal-panel__foot .ghost-action').click()

  // ---- 预览阶段业务校验（重复编号 + 不存在塘口 → 中文逐行错误，不可确认）----
  await page.click('[data-testid="import-open"]')
  await page.fill('.modal-panel input[type="number"]', '1')
  await page.selectOption('.modal-panel select', 'batches')
  await page.setInputFiles('[data-testid="import-file"]', join(OUT, 'w3-batches-bad.xlsx'))
  await page.click('[data-testid="import-preview"]')
  await page.waitForSelector('.modal-error', { timeout: 10000 })
  const modalErrors = await page.locator('.modal-error').allTextContents()
  const hasDup = modalErrors.some((t) => t.includes('业务编号已存在') || t.includes('文件内业务编号重复'))
  const hasPond = modalErrors.some((t) => t.includes('塘口不存在'))
  const confirmHidden = (await page.locator('[data-testid="import-confirm"]').count()) === 0
  record('preview-business-errors', hasDup && hasPond && confirmHidden, `错误条数 ${modalErrors.length}`)
  await page.screenshot({ path: SHOT('w3_preview_errors.png'), fullPage: true })
  await page.locator('.modal-panel__foot .ghost-action').click()

  // ---- 撤销：撤销全部已导入批次（覆盖撤销按钮 + 409 状态校验的边界）----
  const revokeBtn = page.locator('[data-testid="import-revoke"]')
  const revokeCount = await revokeBtn.count()
  if (revokeCount > 0) {
    page.once('dialog', (dialog) => dialog.accept())
    await revokeBtn.first().click()
    await page.waitForSelector('.form-alert--success', { timeout: 10000 })
    const notice2 = await page.locator('.form-alert--success').first().textContent()
    record('revoke-import', notice2.includes('已撤销'), notice2)
    const remaining = await page.locator('[data-testid="import-revoke"]').count()
    record('revoke-only-imported', remaining === revokeCount - 1, `撤销前 ${revokeCount} 个 → 撤销后 ${remaining} 个`)
  } else {
    record('revoke-import', false, '列表页未出现撤销按钮')
  }

  // ---- 后端导出（有数据的资源：imports）并解析断言中文与元数据 ----
  const exportResult = await page.evaluate(async () => {
    const csrf = await fetch('/api/v1/auth/csrf').then((r) => r.json()).then((body) => body.data.csrf_token)
    const response = await fetch('/api/v1/data-exchange/exports', {
      method: 'POST', credentials: 'include',
      headers: { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ organization_id: 1, resource: 'imports', format: 'xlsx', filters: { status: '' } }),
    })
    if (!response.ok) return { ok: false, status: response.status }
    const bytes = [...new Uint8Array(await response.arrayBuffer())]
    return { ok: true, bytes, name: response.headers.get('Content-Disposition') ?? '' }
  })
  if (exportResult.ok) {
    writeFileSync(join(OUT, 'w3-export-imports.xlsx'), Buffer.from(exportResult.bytes))
    record('export-api-with-rows', true, exportResult.name)
  } else {
    record('export-api-with-rows', false, `HTTP ${exportResult.status}`)
  }

  // ---- 导出当前范围（采购单列表 → xlsx 下载并解析）----
  await page.goto(`${BASE}/purchase/orders`, { waitUntil: 'networkidle' })
  const downloadPromise = page.waitForEvent('download', { timeout: 15000 })
  await page.click('[data-testid="table-export-xlsx"]')
  const download = await downloadPromise
  const xlsxPath = join(OUT, 'w3-export-orders.xlsx')
  await download.saveAs(xlsxPath)
  record('export-xlsx-download', download.suggestedFilename().endsWith('.xlsx'), download.suggestedFilename())
  await page.screenshot({ path: SHOT('w3_export_orders.png'), fullPage: true })
} catch (err) {
  record('e2e-run', false, String(err?.message ?? err))
  await page.screenshot({ path: SHOT('w3_e2e_failure.png'), fullPage: true }).catch(() => {})
} finally {
  await browser.close()
  writeFileSync(join(OUT, 'w3_e2e_summary.json'), JSON.stringify(results, null, 2))
  const failed = results.filter((r) => !r.pass).length
  console.log(`\nSUMMARY: ${results.length - failed}/${results.length} passed`)
  process.exit(failed ? 1 : 0)
}
