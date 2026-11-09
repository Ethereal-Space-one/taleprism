const assert = require('node:assert/strict'),
  fs = require('node:fs'),
  path = require('node:path')
const { chromium } = require('playwright')
const root = path.resolve(__dirname, '../..'),
  out = path.join(root, 'data/verification/p6'),
  fixture = JSON.parse(fs.readFileSync(path.join(out, 'fixture.json'))),
  base = process.argv[2] || 'http://127.0.0.1:8000'
;(async () => {
  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
  })
  const report = { passed: false, checked_at: new Date().toISOString() }
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const content = await (
    await page.request.get(base + '/api/projects/' + fixture.project_id + '/reader/content')
  ).json()
  const wait = () => page.waitForTimeout(360)
  async function close() {
    await page.getByRole('button', { name: '关闭面板', exact: true }).click()
    await page.locator('dialog[open]').waitFor({ state: 'hidden' })
    await wait()
  }
  try {
    await page.goto(base + fixture.reader_url)
    await page.getByRole('button', { name: /^开始阅读/ }).click()
    await wait()
    await page.getByRole('button', { name: '设置', exact: true }).click()
    await page.getByRole('button', { name: '开启自动播放对白', exact: true }).click()
    await close()
    assert.equal(await page.evaluate(() => document.querySelector('audio').paused), true)
    let played = false
    for (let i = 0; i < 65; i++) {
      await page.locator('.reader-scroll').evaluate((e) => (e.scrollTop += 90))
      await page.waitForTimeout(300)
      if (await page.evaluate(() => !document.querySelector('audio').paused)) {
        played = true
        break
      }
    }
    assert.equal(played, true, 'slow forward reading should start selected dialogue')
    await page.waitForFunction(() => document.querySelector('audio').currentTime > 0)
    report.automatic_forward_real_audio = true
    await page.getByRole('button', { name: '停止', exact: true }).click()
    await page.locator('.reader-scroll').evaluate((e) => (e.scrollTop -= 130))
    await wait()
    await page.locator('.reader-scroll').evaluate((e) => (e.scrollTop += 130))
    await wait()
    assert.equal(await page.evaluate(() => document.querySelector('audio').paused), true)
    report.backward_does_not_replay = true
    await page.getByRole('button', { name: '打开章节目录', exact: true }).click()
    await page.getByRole('button', { name: '本章对白', exact: true }).click()
    assert.equal(await page.locator('.reader-results>button').count(), 2)
    await page.locator('.reader-results>button').nth(1).click()
    await page.waitForFunction(() => document.querySelector('audio').currentTime > 0)
    const first = await page.evaluate(() => document.querySelector('audio').src)
    await page.evaluate(() => {
      const a = document.querySelector('audio')
      a.currentTime = a.duration - 0.05
    })
    await page.waitForFunction((src) => document.querySelector('audio').src !== src, first)
    await page.waitForFunction(() => document.querySelector('audio').currentTime > 0)
    report.grouped_dialogue_real_queue = true
    await page.screenshot({ path: path.join(out, 'speaking-kongming.png') })
    await page.locator('.reader-scroll').evaluate((e) => (e.scrollTop += 2500))
    await wait()
    assert.equal(await page.evaluate(() => document.querySelector('audio').paused), true)
    assert.equal(await page.locator('.reader-spoken').count(), 0)
    report.scroll_cancels_audio_and_highlight = true
    const shared = await browser.newContext()
    const legacy = await shared.newPage()
    const key = 'storygal-reader:' + content.project.id + ':' + content.project.canonical_sha256
    await legacy.addInitScript(
      ({ key, at }) => localStorage.setItem(key, JSON.stringify({ at, size: 25, leading: 2 })),
      { key, at: content.blocks[3].byte_start },
    )
    await legacy.goto(base + fixture.reader_url)
    await legacy.getByRole('button', { name: /^继续阅读/ }).click()
    await legacy.waitForTimeout(400)
    assert.equal(
      await legacy.locator('.reader-root').getAttribute('data-resume-byte'),
      String(content.blocks[3].byte_start),
    )
    assert.equal(
      await legacy
        .locator('.reader-scroll')
        .evaluate((e) => e.style.getPropertyValue('--reader-size')),
      '25px',
    )
    report.p5_record_migration = true
    const tab2 = await shared.newPage()
    await tab2.goto(base + fixture.reader_url)
    await tab2.waitForTimeout(400)
    assert.ok(
      await legacy
        .getByText('另一窗口保存了阅读记录。当前阅读位置保持不变。', { exact: true })
        .isVisible(),
    )
    assert.equal(
      await legacy.locator('.reader-root').getAttribute('data-resume-byte'),
      String(content.blocks[3].byte_start),
    )
    report.cross_tab_does_not_jump = true
    await shared.close()
    const denied = await browser.newContext()
    await denied.addInitScript(() => {
      Storage.prototype.setItem = function () {
        throw new DOMException('unavailable', 'QuotaExceededError')
      }
    })
    const noStore = await denied.newPage()
    await noStore.goto(base + fixture.reader_url)
    await noStore.getByRole('button', { name: /^开始阅读/ }).click()
    await noStore.getByText('本机存储不可用，本次阅读记录暂不能保存。', { exact: true }).waitFor()
    assert.equal(await noStore.locator('.reader-paragraph').count(), content.blocks.length)
    report.storage_failure_keeps_text = true
    await denied.close()
    const broken = await browser.newPage()
    const image = content.media[content.presentations[0].image_asset_id].url
    await broken.route('**' + image, (r) => r.fulfill({ status: 404, body: 'missing' }))
    await broken.goto(base + fixture.reader_url)
    await broken.getByRole('button', { name: /^开始阅读/ }).click()
    await broken.getByText('场景图片暂不可用，正文仍可阅读。', { exact: true }).waitFor()
    assert.equal(await broken.locator('.reader-paragraph').count(), content.blocks.length)
    report.image_failure_keeps_text = true
    const preview = await browser.newPage()
    await preview.goto(
      base + fixture.reader_url + '?at=' + content.blocks[3].byte_start + '&editing=1',
    )
    await preview.getByRole('button', { name: '记录此处意见', exact: true }).click()
    await preview.getByLabel('此处意见', { exact: true }).fill('P6_PREVIEW_PRIVATE_NOTE')
    await preview.getByRole('button', { name: '保存此处意见', exact: true }).click()
    await preview.getByText('意见已记录，可回制作台定位处理。', { exact: true }).waitFor()
    report.source_preview_editorial = true
    assert.deepEqual(errors, [])
    report.passed = true
  } catch (e) {
    report.error = String(e.stack || e)
    await page.screenshot({ path: path.join(out, 'edge-failure.png') }).catch(() => {})
    throw e
  } finally {
    fs.writeFileSync(path.join(out, 'edge-report.json'), JSON.stringify(report, null, 2))
    await browser.close()
  }
  console.log(JSON.stringify(report, null, 2))
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
