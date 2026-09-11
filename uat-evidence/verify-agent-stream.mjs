/**
 * 生产环境浏览器级验证：流式输出是否真的"边跑边出字"。
 * 用一次性会话 cookie 打开工作台 → 打开塘小助 → 提一个问题 → 采样流式气泡的增长。
 */
import { chromium } from 'playwright'
import { writeFileSync, mkdirSync } from 'node:fs'

const TOKEN = process.env.ADP_SESSION_TOKEN
const OUT = process.env.ADP_SHOT_DIR || '.'
if (!TOKEN) { console.error('ADP_SESSION_TOKEN missing'); process.exit(2) }
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1440, height: 950 }, ignoreHTTPSErrors: true })
await context.addCookies([{
  name: 'adp_session', value: TOKEN, domain: '23331.cloud', path: '/',
  httpOnly: true, secure: true, sameSite: 'Lax',
}])

const page = await context.newPage()
const errors = []
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 160)) })

await page.goto('https://23331.cloud/adp/workbench', { waitUntil: 'domcontentloaded', timeout: 60000 })
await page.waitForSelector('[aria-label="打开塘小助"]', { timeout: 45000 })
await page.screenshot({ path: `${OUT}/01-workbench.png` })

await page.click('[aria-label="打开塘小助"]')
await page.waitForSelector('[aria-label="塘小助指令"]', { timeout: 15000 })
await page.screenshot({ path: `${OUT}/02-agent-panel.png` })

await page.fill('[aria-label="塘小助指令"]', '南区的塘口情况怎么样？')
const t0 = Date.now()
await page.press('[aria-label="塘小助指令"]', 'Enter')

let firstTokenAt = null
let firstStatusAt = null
const samples = []
for (let i = 0; i < 400; i++) {
  const state = await page.evaluate(() => {
    const stream = document.querySelector('[data-testid="agent-streaming"]')
    const status = document.querySelector('[data-testid="agent-status"]')
    const msgs = Array.from(document.querySelectorAll('.agent-message--assistant'))
    return {
      stream: stream ? (stream.textContent || '').trim() : '',
      status: status ? (status.textContent || '').trim() : '',
      last: msgs.length ? (msgs[msgs.length - 1].textContent || '').trim() : '',
      error: document.querySelector('.agent-panel__error')?.textContent?.trim() || '',
    }
  })
  const at = Date.now() - t0
  if (state.status && !firstStatusAt) { firstStatusAt = at; samples.push([at, 'status:' + state.status]) }
  if (state.stream && firstTokenAt === null) {
    firstTokenAt = at
    await page.screenshot({ path: `${OUT}/03-streaming.png` })
  }
  if (state.stream) samples.push([at, state.stream.length])
  if (firstTokenAt !== null && !state.stream) {
    samples.push([at, 'final:' + state.last.length])
    if (state.error) samples.push([at, 'error:' + state.error])
    break
  }
  await page.waitForTimeout(100)
}

await page.waitForTimeout(600)
await page.screenshot({ path: `${OUT}/04-final.png` })
const finalText = await page.evaluate(() => {
  const msgs = Array.from(document.querySelectorAll('.agent-message--assistant'))
  return msgs.length ? (msgs[msgs.length - 1].textContent || '') : ''
})

writeFileSync(`${OUT}/report.json`, JSON.stringify({
  firstTokenMs: firstTokenAt, firstStatus: firstStatusAt, samples, finalChars: finalText.length,
  finalHead: finalText.slice(0, 160), consoleErrors: errors,
}, null, 2), 'utf-8')

console.log(JSON.stringify({
  firstTokenMs: firstTokenAt, firstStatusMs: firstStatusAt,
  streamSamples: samples.slice(0, 6), finalChars: finalText.length,
  finalHead: finalText.slice(0, 100), consoleErrors: errors.slice(0, 3),
}, null, 2))

await browser.close()
