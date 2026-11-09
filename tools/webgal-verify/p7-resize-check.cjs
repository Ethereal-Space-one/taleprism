const assert = require('node:assert/strict'),
  fs = require('node:fs'),
  path = require('node:path')
const { chromium } = require('playwright')
const root = path.resolve(__dirname, '../..'),
  out = path.join(root, 'data/verification/p7'),
  f = JSON.parse(fs.readFileSync(path.join(out, 'fixture.json'))),
  base = process.argv[2] || 'http://127.0.0.1:8000'
;(async () => {
  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const r = { passed: false, checked_at: new Date().toISOString() }
  try {
    await page.goto(base + f.reader_url)
    await page.getByRole('button', { name: /^开始阅读/ }).click()
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    await page.getByLabel('查找原文', { exact: true }).fill('瑜命請入')
    await page.locator('.reader-results>button').first().click()
    await page.waitForTimeout(350)
    const byte = await page.locator('.reader-root').getAttribute('data-view-byte')
    await page.setViewportSize({ width: 375, height: 1000 })
    await page.waitForTimeout(500)
    assert.equal(await page.locator('.reader-root').getAttribute('data-view-byte'), byte)
    assert.deepEqual(await page.locator('.reader-portraits figcaption').allTextContents(), [
      '孔明',
      '周瑜',
    ])
    await page.locator('.reader-scroll').hover()
    await page.mouse.wheel(0, 400)
    await page.waitForTimeout(350)
    assert.notEqual(await page.locator('.reader-root').getAttribute('data-view-byte'), byte)
    r.source_and_cast_retained_on_resize = true
    r.real_wheel_scroll_resumes = true
    r.passed = true
  } finally {
    fs.writeFileSync(path.join(out, 'resize-report.json'), JSON.stringify(r, null, 2))
    await browser.close()
  }
  console.log(JSON.stringify(r))
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
