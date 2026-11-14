// Synthetic, read-only browser regression for the real built ReaderApp.
// Run npm --prefix frontend run build first, then this file. No backend/content packs needed.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const http = require('node:http')
const os = require('node:os')
const path = require('node:path')
const { chromium } = require('playwright')

const root = path.resolve(__dirname, '../..')
const dist = path.join(root, 'frontend/dist')
const shots = fs.mkdtempSync(path.join(os.tmpdir(), 'taleprism-image-viewer-'))
const dimensions = [[1800, 1000], [900, 1600], [1200, 1200], [2000, 500]]
const titles = ['横幅样张', '竖幅样张', '方幅样张', '超宽样张' + '长标题'.repeat(20)]
let byte = 0
const blocks = dimensions.map((_, i) => {
  const text = `第${i + 1}段原文，图像浏览不应改变正文、内联插图或续读位置。`
  const start = byte
  byte += Buffer.byteLength(text)
  return { id: `b${i}`, text, byte_start: start, byte_end: byte, heading: false, audio: [], runs: [{ text, speaker_id: null, take_id: null }] }
})
const fixture = {
  schema_version: 3,
  project: { id: 'viewer-fixture', filename: '浏览回归.txt', sha256: 'synthetic', canonical_sha256: 'synthetic', rights_status: 'local_test', character_count: byte },
  versions: { reader_revision: 1, review_revision: 1, speech_revision: 1 },
  config: { title: '插图浏览回归', subtitle: '合成样张，不使用正式美术', cover_asset_id: null, scenes: [], map_profile: null, reading_layout: 'illustrated', illustrations: dimensions.map((_, i) => ({ id: `plate-${i}`, image_asset_id: `art-${i}`, title: titles[i], description: `四边完整可见的样张 ${i}`, after_byte: blocks[i].byte_end })) },
  blocks, characters: {}, presentations: [], map_entries: [], map: null, preview: false, issues: [],
  media: Object.fromEntries(dimensions.map(([width, height], i) => [`art-${i}`, { id: `art-${i}`, type: 'image', url: `/art/${i}.svg`, sha256: 'synthetic', width, height }])),
}
function svg(i) {
  const [w, h] = dimensions[i]
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><rect width="${w}" height="${h}" fill="#b6d4d3"/><rect x="8" y="8" width="${w - 16}" height="${h - 16}" fill="none" stroke="#e33c27" stroke-width="16"/><path d="M0 0L${w} ${h}M${w} 0L0 ${h}" stroke="#326077" stroke-width="8"/><circle cx="${w / 2}" cy="${h / 2}" r="${Math.min(w, h) / 5}" fill="#e9c855"/></svg>`
}
let releaseRetry = null
let holdRetry = false
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost')
  if (url.pathname === '/reader-content.json') {
    res.setHeader('Content-Type', 'application/json')
    res.end(JSON.stringify(fixture)); return
  }
  const art = /^\/art\/(\d)\.svg$/.exec(url.pathname)
  if (art) {
    if (holdRetry && url.searchParams.has('taleprism_retry')) {
      await new Promise(resolve => {
        const previous = releaseRetry
        releaseRetry = () => { previous?.(); resolve() }
      })
    }
    res.setHeader('Content-Type', 'image/svg+xml')
    res.setHeader('Cache-Control', 'no-store')
    res.end(svg(Number(art[1]))); return
  }
  const file = path.resolve(dist, '.' + (url.pathname === '/' ? '/index.html' : url.pathname))
  if (!file.startsWith(dist + path.sep) || !fs.existsSync(file)) { res.writeHead(404).end(); return }
  res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html')
  let body = fs.readFileSync(file)
  if (file.endsWith('index.html')) body = body.toString().replace('<head>', '<head><meta name="storygal-reader-export" content="/reader-content.json">')
  res.end(body)
})

;(async () => {
  assert.ok(fs.existsSync(path.join(dist, 'index.html')), 'run npm --prefix frontend run build first')
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || (fs.existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined)
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) })
  const page = await browser.newPage({ viewport: { width: 1331, height: 894 } })
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  const canvas = page.locator('.reader-image-viewport')
  const zoom = () => page.getByRole('button', { name: '放大细节 2×', exact: true })
  async function fit(label) {
    await page.locator('.reader-expanded-image').evaluate(img => img.decode())
    const result = await page.locator('.reader-image-dialog').evaluate(dialog => {
      const body = dialog.querySelector('.reader-dialog-body'), viewport = dialog.querySelector('.reader-image-viewport'), image = viewport.querySelector('img')
      const rect = element => { const r = element.getBoundingClientRect(); return { top: r.top, left: r.left, right: r.right, bottom: r.bottom, width: r.width, height: r.height } }
      return {
        dialog: rect(dialog), viewport: rect(viewport), image: rect(image), natural: [image.naturalWidth, image.naturalHeight], objectFit: getComputedStyle(image).objectFit,
        scrolls: [dialog, body, viewport].map(e => [e.scrollWidth - e.clientWidth, e.scrollHeight - e.clientHeight, e.scrollLeft, e.scrollTop]),
        controls: [...dialog.querySelectorAll('button')].map(rect), window: [innerWidth, innerHeight], overflow: document.documentElement.scrollWidth > innerWidth,
      }
    })
    assert.equal(result.objectFit, 'contain', label)
    assert.equal(result.overflow, false, `${label}: page must not overflow horizontally`)
    assert.ok(result.viewport.height > 0, `${label}: an image region remains`)
    assert.ok(result.dialog.top >= 0 && result.dialog.bottom <= result.window[1], `${label}: dialog fits viewport`)
    for (const [dx, dy, x, y] of result.scrolls) {
      assert.ok(dx <= 1 && dy <= 1 && x === 0 && y === 0, `${label}: default view has no outer or inner scrolling: ${JSON.stringify(result.scrolls)}`)
    }
    assert.ok(Math.abs(result.image.width - result.viewport.width) < 1 && Math.abs(result.image.height - result.viewport.height) < 1, `${label}: contain operates in the bounded image region`)
    const scale = Math.min(result.image.width / result.natural[0], result.image.height / result.natural[1])
    assert.ok(scale * result.natural[0] <= result.viewport.width + 1 && scale * result.natural[1] <= result.viewport.height + 1, `${label}: complete uncropped artwork fits both axes`)
    for (const r of result.controls) assert.ok(r.top >= 0 && r.bottom <= result.window[1] && r.left >= 0 && r.right <= result.window[0], `${label}: close/zoom/previous/next stay reachable`)
    assert.equal(await canvas.getAttribute('aria-label'), '完整插图')
    return result
  }
  async function pan(label) {
    await zoom().click()
    const enlarged = await canvas.evaluate(e => {
      const image = e.querySelector('img').getBoundingClientRect()
      e.scrollTo(e.scrollWidth, e.scrollHeight)
      return { x: e.scrollLeft, y: e.scrollTop, w: e.clientWidth, h: e.clientHeight, iw: image.width, ih: image.height, body: e.parentElement.scrollTop }
    })
    assert.ok(enlarged.x > 0 && enlarged.y > 0, `${label}: only explicit zoom enables panning`)
    assert.ok(enlarged.iw >= enlarged.w * 1.99 && enlarged.ih >= enlarged.h * 1.99, `${label}: both axes enlarge 2x`)
    assert.equal(enlarged.body, 0, `${label}: panning never scrolls dialog body`)
    assert.equal(await canvas.getAttribute('aria-label'), '插图细节，可横向和纵向移动')
  }
  try {
    await page.goto(`http://127.0.0.1:${server.address().port}/`)
    await page.getByRole('button', { name: /^开始阅读/ }).click()
    assert.equal(await page.locator('.reader-paragraph-text').allTextContents().then(x => x.join('')), blocks.map(b => b.text).join(''))
    const inline = page.locator('.reader-plate-art').first()
    await inline.scrollIntoViewIfNeeded()
    await inline.locator('img').evaluate(img => img.decode())
    const inlineBefore = await inline.evaluate(e => ({ width: e.clientWidth, height: e.clientHeight }))
    await inline.click()
    const resume = await page.locator('.reader-root').getAttribute('data-resume-byte')
    const desktop = await fit('1331x894 first expanded landscape')
    await page.screenshot({ path: path.join(shots, 'desktop-fit.png') })
    let cases = 0
    for (const [width, height] of [[1331, 894], [375, 667], [320, 568], [667, 320], [320, 320], [1024, 400]]) {
      await page.setViewportSize({ width, height })
      for (let i = 0; i < dimensions.length; i++) {
        // First plate is selected at the beginning of every size pass.
        await fit(`${width}x${height} plate ${i}`)
        await pan(`${width}x${height} plate ${i}`)
        if (i < dimensions.length - 1) {
          await page.getByRole('button', { name: '下一幅', exact: true }).click()
          await fit(`${width}x${height}: new plate resets zoom and scroll`)
        } else {
          await page.getByRole('button', { name: '恢复完整画面', exact: true }).click()
          await fit(`${width}x${height}: fit restores scroll origin`)
        }
        cases++
      }
      if (width === 667) await page.screenshot({ path: path.join(shots, 'short-fit.png') })
      for (let i = 0; i < dimensions.length - 1; i++) await page.getByRole('button', { name: '上一幅', exact: true }).click()
    }
    await page.setViewportSize({ width: 1331, height: 894 })
    // A real retry request is held so loading and final recovery are independently observed.
    await page.locator('.reader-expanded-image').dispatchEvent('error')
    await page.getByText('这幅画面暂不可用，正文与续读位置已保留。', { exact: true }).waitFor()
    holdRetry = true
    await page.getByRole('button', { name: '重试横幅样张', exact: true }).click()
    await page.getByText('正在重新载入画面…', { exact: true }).first().waitFor()
    assert.equal(await page.getByRole('button', { name: '关闭面板', exact: true }).isVisible(), true)
    holdRetry = false; releaseRetry?.()
    await page.getByText('正在重新载入画面…', { exact: true }).first().waitFor({ state: 'hidden' })
    await fit('recovered image still defaults to fit')
    await page.keyboard.press('Escape')
    await page.locator('dialog[open]').waitFor({ state: 'hidden' })
    assert.equal(await inline.evaluate(e => e === document.activeElement), true, 'Escape restores opener focus')
    assert.deepEqual(await inline.evaluate(e => ({ width: e.clientWidth, height: e.clientHeight })), inlineBefore, 'inline image geometry is unchanged')
    assert.equal(await page.locator('.reader-root').getAttribute('data-resume-byte'), resume)
    await page.goForward()
    await fit('browser forward restores viewer')
    await page.goBack()
    await page.locator('dialog[open]').waitFor({ state: 'hidden' })
    await page.getByRole('button', { name: '设置', exact: true }).click()
    await page.getByRole('button', { name: /^本章画卷/ }).click()
    assert.equal(await page.locator('.reader-art-dialog.reader-image-dialog').count(), 0, 'gallery is not constrained by viewer-only layout')
    assert.equal(await page.locator('.reader-gallery-item').count(), dimensions.length)
    await page.locator('.reader-gallery-item').first().getByRole('button').first().click()
    await fit('gallery opens fit viewer')
    await page.getByRole('button', { name: '关闭面板', exact: true }).click()
    await page.locator('.reader-gallery').waitFor()
    assert.equal(await page.locator('.reader-root').getAttribute('data-resume-byte'), resume, 'gallery navigation preserves reading position')
    assert.deepEqual(errors, [])
    console.log(`Reader image viewer: ${cases} aspect/viewport cases passed; default complete fit, no nested scroll/overflow, pinned controls, explicit 2x pan, new-plate reset, retry/loading/recovery, Escape/focus, Back/Forward, inline layout and gallery preserved.`)
    console.log(`1331x894 canvas: ${Math.round(desktop.viewport.width)}x${Math.round(desktop.viewport.height)}; screenshots: ${shots}`)
  } catch (error) {
    await page.screenshot({ path: path.join(shots, 'failure.png') }).catch(() => {})
    console.error(`Failure screenshot: ${path.join(shots, 'failure.png')}`)
    throw error
  } finally {
    holdRetry = false; releaseRetry?.()
    await browser.close()
    await new Promise(resolve => server.close(resolve))
  }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1 })
