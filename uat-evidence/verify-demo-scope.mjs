/**
 * 演示档（VITE_DEMO_SCOPE=core）验收：真实浏览器里只有主线分区与主线页面。
 * 用一次性会话登录本地 dev:demo（代理到生产 API），断言侧边栏文案，并截图。
 */
import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'

const TOKEN = process.env.ADP_SESSION_TOKEN
const BASE = process.env.ADP_DEMO_BASE ?? 'http://127.0.0.1:5173'
const OUT = process.env.ADP_SHOT_DIR ?? '.'
if (!TOKEN) { console.error('ADP_SESSION_TOKEN missing'); process.exit(2) }
mkdirSync(OUT, { recursive: true })

const CORE_SECTIONS = ['塘口与批次', '销售与收款', '成本与经营']
const HIDDEN_SECTIONS = ['日常养殖', '物料与仓储', '采购与付款', '数据交换', '系统管理']
const CORE_ITEMS = ['塘口档案', '塘口分组', '养殖批次', '出塘捕捞', '销售明细', '应收账款', '成本构成', '期间结算']
const HIDDEN_ITEMS = ['规格抽样', '转塘记录', '损耗记录', '供应商退货', '客户退货', '费用登记', '资产台账', '仓储台账', '饲料投喂', '塘口巡检']

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1440, height: 950 } })
await context.addCookies([{ name: 'adp_session', value: TOKEN, url: `${BASE}/`, httpOnly: true, sameSite: 'Lax' }])
const page = await context.newPage()
const problems = []
page.on('console', (m) => { if (m.type() === 'error') problems.push(m.text().slice(0, 140)) })

await page.goto(`${BASE}/workbench`, { waitUntil: 'domcontentloaded', timeout: 60000 })
await page.waitForSelector('nav, .app-shell, [class*=shell]', { timeout: 45000 })
await page.waitForTimeout(2500)

let shellText = await page.evaluate(() => document.body.innerText)
// 分区默认是折叠的：把主线分区逐个点开，确认"主线页面"也在
for (const label of ['塘口与批次', '销售与收款', '成本与经营']) {
  const hit = page.getByText(label, { exact: true }).first()
  try { await hit.click({ timeout: 4000 }) } catch { /* 已展开或不可点 */ }
  await page.waitForTimeout(400)
}
await page.waitForTimeout(600)
shellText = await page.evaluate(() => document.body.innerText)
const navText = shellText

const result = {
  coreSectionsPresent: CORE_SECTIONS.filter((t) => navText.includes(t)),
  hiddenSectionsAbsent: HIDDEN_SECTIONS.filter((t) => !navText.includes(t)),
  coreItemsPresent: CORE_ITEMS.filter((t) => navText.includes(t)),
  hiddenItemsAbsent: HIDDEN_ITEMS.filter((t) => !navText.includes(t)),
  leakedHidden: HIDDEN_SECTIONS.concat(HIDDEN_ITEMS).filter((t) => navText.includes(t)),
  missingCore: CORE_SECTIONS.concat(CORE_ITEMS).filter((t) => !navText.includes(t)),
  consoleErrors: problems,
}
await page.screenshot({ path: `${OUT}/demo-core-workbench.png` })
const nav = await page.$('nav') || await page.$('aside')
if (nav) await nav.screenshot({ path: `${OUT}/demo-core-nav.png` })

writeFileSync(`${OUT}/demo-scope-report.json`, JSON.stringify({ ...result, navText, shellHead: shellText.slice(0, 400) }, null, 2), 'utf-8')
console.log(JSON.stringify(result, null, 2))
await browser.close()
