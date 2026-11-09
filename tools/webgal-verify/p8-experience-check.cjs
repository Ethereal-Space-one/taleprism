const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require('playwright')
const out = path.resolve(__dirname, '../../data/verification/p8')
const fixture = JSON.parse(fs.readFileSync(path.join(out, 'fixture.json')))
const base = process.argv[2] || 'http://127.0.0.1:8000'
;(async () => {
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  const report = { passed: false, checked_at: new Date().toISOString(), project_id: fixture.project_id }
  try {
    for (const saveData of [false, true]) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
      await context.addInitScript((saveData) => {
        Object.defineProperty(navigator, 'connection', { value: { saveData }, configurable: true })
        window.__predicted = []
        const Original = window.Image
        window.Image = class extends Original {
          constructor(...args) { super(...args); window.__predicted.push(this) }
        }
      }, saveData)
      const page = await context.newPage()
      const content = await (await page.request.get(base + '/api/projects/' + fixture.project_id + '/reader/content')).json()
      await page.goto(base + fixture.reader_url)
      await page.getByRole('button', { name: /^开始阅读/ }).click()
      await page.waitForTimeout(500)
      const id = await page.locator('.reader-stage').getAttribute('data-presentation-id')
      const start = content.presentations.findIndex(p => p.id === id)
      const expected = [...new Set(content.presentations.slice(start, start + (saveData ? 1 : 3)).flatMap(p => [p.image_asset_id, ...p.cast.map(c => c.figure_asset_id)]).map(id => new URL(content.media[id].url, base).href))].sort()
      const predicted = await page.evaluate(() => window.__predicted.map(image => image.src).sort())
      assert.deepEqual(predicted, expected)
      assert.ok(predicted.length <= 9)
      assert.equal(await page.locator('audio').evaluate(e => e.paused), true)
      if (!saveData) {
        for (const [quote, who] of [['子龍可帶三千軍馬', '赵云'], ['又喚張飛曰', '张飞']]) {
          await page.getByRole('button', { name: '搜索', exact: true }).click()
          await page.getByLabel('查找原文', { exact: true }).fill(quote)
          await page.locator('.reader-results>button').first().click()
          const anchor = await page.locator('.reader-root').getAttribute('data-view-byte')
          for (const width of [320, 375, 414, 768, 1440]) {
            await page.setViewportSize({ width, height: 1000 })
            await page.waitForTimeout(300)
            assert.deepEqual(await page.locator('.reader-portraits figcaption').allTextContents(), ['孔明', who])
            assert.equal(await page.locator('.reader-root').getAttribute('data-view-byte'), anchor)
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
            await page.waitForFunction(() => [...document.querySelectorAll('.reader-portraits img')].every(i => i.complete && i.naturalWidth > 0))
            await page.screenshot({ path: path.join(out, (who === '赵云' ? 'zhaoyun' : 'zhangfei') + '-' + width + '.png') })
          }
        }
      }
      report[saveData ? 'save_data_current_only' : 'bounded_current_and_next_two'] = true
      await context.close()
    }
    report.new_roles_five_viewports = true
    report.preloading_does_not_play_audio = true
    report.passed = true
  } finally {
    fs.writeFileSync(path.join(out, 'experience-report.json'), JSON.stringify(report, null, 2))
    await browser.close()
  }
  console.log(JSON.stringify(report, null, 2))
})().catch(e => { console.error(e); process.exit(1) })
