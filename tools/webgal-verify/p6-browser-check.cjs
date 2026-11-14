const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const { spawnSync } = require('node:child_process')
const { chromium } = require('playwright')
const root = path.resolve(__dirname, '../..'),
  out = path.join(root, 'data/verification/p6')
const base = process.argv[2] || 'http://127.0.0.1:8000'
const fixture = JSON.parse(fs.readFileSync(path.join(out, 'fixture.json')))
const report = {
  passed: false,
  project_id: fixture.project_id,
  checked_at: new Date().toISOString(),
}
const visible = (t) =>
  t
    .replace(/^\uFEFF/, '')
    .split(/\r\n|\r|\n/)
    .map((l) => l.replace(/^[ \t\u3000]+|[ \t\u3000]+$/g, ''))
    .join('')
;(async () => {
  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const prefix = '/api/projects/' + fixture.project_id
  async function call(url, method = 'GET', data) {
    const r = await page.request.fetch(base + url, { method, data })
    assert.ok(r.ok(), await r.text())
    return r.json()
  }
  const content = await call(prefix + '/reader/content')
  async function wait() {
    await page.waitForTimeout(360)
  }
  async function open(name) {
    await page
      .getByRole('button', { name: name === '目录' ? '打开章节目录' : name, exact: true })
      .click()
    await page.locator('dialog[open]').waitFor()
  }
  async function close(to) {
    await page.getByRole('button', { name: '关闭面板', exact: true }).click()
    if (to) await page.locator('#reader-panel-title').filter({ hasText: to }).waitFor()
    else await page.locator('dialog[open]').waitFor({ state: 'hidden' })
    await wait()
  }
  async function scene(title) {
    await open('目录')
    await page
      .locator('.reader-contents')
      .getByRole('button', { name: new RegExp('^' + title) })
      .click()
    await wait()
  }
  async function raw() {
    return page.locator('.reader-root').evaluate((e) => ({
      at: Number(e.dataset.viewByte),
      resume: Number(e.dataset.resumeByte),
      visiting: e.dataset.visiting === 'true',
    }))
  }
  async function overflow() {
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
    )
  }
  let server
  try {
    await page.goto(base + fixture.reader_url)
    await page.getByRole('button', { name: /^开始阅读/ }).click()
    await wait()
    assert.equal(await page.locator('.reader-portraits figure').count(), 0)
    report.correct_opening_cast = true
    assert.equal(
      await page
        .locator('.reader-paragraph-text')
        .evaluateAll((es) => es.map((e) => e.textContent).join('')),
      visible(
        fs.readFileSync(
          path.join(root, 'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'),
          'utf8',
        ),
      ),
    )
    report.original_text_equal = true
    await page.locator('.reader-scroll').evaluate((e) => {
      e.scrollTop = 650
    })
    await wait()
    const A = await raw()
    assert.ok(A.resume > content.blocks[0].byte_start)
    await open('搜索')
    await page.getByLabel('查找原文', { exact: true }).fill('黃蓋用刀一招')
    await page.locator('.reader-results>button').first().click()
    await wait()
    const B = await raw()
    assert.ok(B.visiting)
    assert.equal(B.resume, A.resume)
    assert.equal(await page.locator('.reader-portraits figure').count(), 0)
    await page.screenshot({ path: path.join(out, 'fire-1440.png') })
    await scene('山林败走')
    const C = await raw()
    assert.ok(C.visiting)
    assert.equal(C.resume, A.resume)
    await page.goBack()
    await wait()
    assert.equal((await raw()).at, B.at)
    await page.goBack()
    await wait()
    assert.equal((await raw()).at, A.at)
    assert.equal((await raw()).visiting, false)
    report.nested_history_returns = true
    await open('搜索')
    await page.getByLabel('查找原文', { exact: true }).fill('黃蓋用刀一招')
    await page.locator('.reader-results>button').first().click()
    await wait()
    await page.reload()
    await page.getByRole('button', { name: /^继续阅读/ }).click()
    await wait()
    assert.equal((await raw()).at, A.resume)
    report.temporary_visit_preserves_resume = true
    await scene('山林败走')
    await page.getByRole('button', { name: '从这里继续', exact: true }).click()
    await wait()
    const adopted = await raw()
    assert.equal(adopted.visiting, false)
    assert.equal(adopted.resume, adopted.at)
    await page.reload()
    await page.getByRole('button', { name: /^继续阅读/ }).click()
    await wait()
    assert.equal((await raw()).at, adopted.resume)
    report.explicit_continue_persists = true
    await open('收藏')
    await page.getByRole('button', { name: '在当前阅读处加书签', exact: true }).click()
    await close()
    await page.evaluate(() => {
      const spans = document.querySelectorAll('[data-source-start]')
      const r = document.createRange()
      r.setStart(spans[1].firstChild, 2)
      r.setEnd(spans[2].firstChild, 5)
      const s = getSelection()
      s.removeAllRanges()
      s.addRange(r)
      document
        .querySelector('.reader-scroll')
        .dispatchEvent(new PointerEvent('pointerup', { bubbles: true }))
    })
    await page.getByRole('button', { name: '保存原文摘录', exact: true }).click()
    await open('收藏')
    assert.equal(await page.locator('.reader-mark').count(), 2)
    report.bookmark_and_cross_run_excerpt = true
    await close()
    const before = await raw()
    await open('设置')
    await page.getByLabel('正文字号', { exact: true }).fill('25')
    await page.getByRole('button', { name: '收起场景画面', exact: true }).click()
    await close()
    assert.equal(await page.locator('.reader-stage').count(), 0)
    assert.equal((await raw()).at, before.at)
    await open('设置')
    await page.getByRole('button', { name: '展开场景画面', exact: true }).click()
    await close()
    report.layout_keeps_source_anchor = true
    await open('设置')
    await page.getByRole('button', { name: '查看战区地图', exact: true }).click()
    await page.locator('.map-phases>button').nth(2).click()
    assert.equal(
      await page.locator('.map-phases>button').nth(2).getAttribute('aria-pressed'),
      'true',
    )
    await close('阅读设置') // back to settings
    await close()
    assert.equal((await raw()).at, before.at)
    report.map_free_phase_and_nested_dialog = true
    await open('目录')
    await page.getByRole('button', { name: '本章对白', exact: true }).click()
    await page.locator('.reader-results>button').first().click()
    await wait()
    await page.waitForFunction(() => document.querySelector('audio').currentTime > 0)
    assert.equal(await page.evaluate(() => document.querySelector('audio').paused), false)
    const singleAt = await raw()
    await open('设置')
    assert.equal(
      await page.getByRole('button', { name: '开启自动播放对白', exact: true }).count(),
      1,
    )
    const time = await page.evaluate(() => document.querySelector('audio').currentTime)
    await page.waitForTimeout(200)
    assert.ok(
      Math.abs((await page.evaluate(() => document.querySelector('audio').currentTime)) - time) <
        0.1,
    )
    await close()
    assert.equal(await page.evaluate(() => document.querySelector('audio').paused), true)
    await page.getByRole('button', { name: '继续播放', exact: true }).click()
    await page.waitForFunction(() => !document.querySelector('audio').paused)
    report.real_audio_suspend_resume_and_single_mode = true
    await page.getByRole('button', { name: '停止', exact: true }).click()
    await page.locator('.reader-scroll').evaluate((e) => (e.scrollTop = e.scrollHeight))
    await wait()
    await page.getByRole('button', { name: '标记本轮阅读完成', exact: true }).click()
    assert.equal(
      await page.getByRole('button', { name: '本轮已完成 · 撤销' }).getAttribute('aria-pressed'),
      'true',
    )
    report.reader_completion_explicit = true
    for (const w of [320, 375, 414, 768, 1440]) {
      await page.setViewportSize({ width: w, height: 1000 })
      await wait()
      await overflow()
      await page.screenshot({ path: path.join(out, `reading-${w}.png`) })
      await open('设置')
      await overflow()
      await page.screenshot({ path: path.join(out, `settings-${w}.png`) })
      await close()
    }
    report.viewports = [320, 375, 414, 768, 1440]
    await page.setViewportSize({ width: 320, height: 640 })
    await page.getByRole('button', { name: '← 封面', exact: true }).click()
    await wait()
    await overflow()
    assert.ok(await page.getByRole('button', { name: /^继续阅读/ }).isVisible())
    await page.screenshot({ path: path.join(out, 'cover-320x640.png') })
    const maker = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    maker.on('pageerror', (e) => errors.push(e.message))
    await maker.goto(base)
    await maker.evaluate((id) => localStorage.setItem('storygal-project', id), fixture.project_id)
    await maker.reload()
    await maker.getByRole('button', { name: '独立阅读器', exact: true }).click()
    await maker.getByRole('heading', { name: '章节编排与位置意见' }).waitFor()
    await maker
      .getByLabel('在所选原文位置记录意见', { exact: true })
      .fill('P6_BROWSER_PRIVATE_NOTE')
    await maker.getByRole('button', { name: '保存位置意见', exact: true }).click()
    await maker.getByText('P6_BROWSER_PRIVATE_NOTE · 未处理', { exact: true }).waitFor()
    await maker
      .locator('.reader-editorial-item')
      .filter({ hasText: 'P6_BROWSER_PRIVATE_NOTE · 未处理' })
      .last()
      .getByRole('button', { name: '确认已处理', exact: true })
      .click()
    await maker.getByText('P6_BROWSER_PRIVATE_NOTE · 已处理', { exact: true }).last().waitFor()
    await maker.screenshot({ path: path.join(out, 'maker-1440.png'), fullPage: true })
    for (const w of [320, 375, 414, 768]) {
      await maker.setViewportSize({ width: w, height: 1000 })
      await maker.waitForTimeout(120)
      assert.equal(
        await maker.evaluate(() => document.documentElement.scrollWidth > innerWidth),
        false,
      )
      await maker.screenshot({ path: path.join(out, `maker-${w}.png`), fullPage: true })
    }
    report.editorial_ui = true
    // Keep only automated fixture comments current; never writes final human review.
    let notes = await call(prefix + '/reader/editorial')
    for (const i of notes.issues.filter(
      (i) => i.note === 'P6_BROWSER_PRIVATE_NOTE' || i.note === 'P6_PREVIEW_PRIVATE_NOTE',
    )) {
      notes = await call(prefix + '/reader/editorial', 'POST', {
        revision: notes.revision,
        id: i.id,
        anchor: i.anchor,
        category: i.category,
        note: i.note,
        state: 'resolved',
        reason: '',
      })
    }
    const jobStart = await call(prefix + '/reader/exports', 'POST')
    let job
    for (let i = 0; i < 200; i++) {
      job = (await call(prefix + '/jobs')).find((j) => j.id === jobStart.job_id)
      if (job.state !== 'running') break
      await page.waitForTimeout(100)
    }
    assert.equal(job.state, 'completed', JSON.stringify(job))
    const download = await page.request.get(base + job.result.download_url)
    const zip = path.join(out, 'storygal-reader-p6.zip')
    fs.writeFileSync(zip, await download.body())
    const unpack = path.join(out, 'standalone', job.id)
    fs.mkdirSync(unpack, { recursive: true })
    assert.equal(spawnSync('unzip', ['-q', '-o', zip, '-d', unpack]).status, 0)
    const verified = spawnSync('python3', ['verify_package.py'], { cwd: unpack, encoding: 'utf8' })
    assert.equal(verified.status, 0, verified.stdout + verified.stderr)
    const exported = JSON.parse(fs.readFileSync(path.join(unpack, 'reader.json')))
    assert.ok(!JSON.stringify(exported).includes('P6_BROWSER_PRIVATE_NOTE'))
    report.package_integrity_and_private_data = true
    server = http.createServer((req, res) => {
      const f = path.resolve(
        unpack,
        '.' +
          decodeURIComponent(req.url.split('?')[0] === '/' ? '/index.html' : req.url.split('?')[0]),
      )
      if (!f.startsWith(unpack + path.sep) || !fs.existsSync(f)) {
        res.writeHead(404).end()
        return
      }
      res.setHeader(
        'Content-Type',
        f.endsWith('.js')
          ? 'application/javascript'
          : f.endsWith('.css')
            ? 'text/css'
            : f.endsWith('.json')
              ? 'application/json'
              : f.endsWith('.png')
                ? 'image/png'
                : f.endsWith('.wav')
                  ? 'audio/wav'
                  : 'text/html',
      )
      fs.createReadStream(f).pipe(res)
    })
    await new Promise((r) => server.listen(0, '127.0.0.1', r))
    const port = server.address().port
    const standalone = await browser.newPage()
    const api = []
    standalone.on('request', (r) => {
      if (new URL(r.url()).pathname.startsWith('/api/')) api.push(r.url())
    })
    standalone.on('pageerror', (e) => errors.push(e.message))
    await standalone.goto(`http://127.0.0.1:${port}/`)
    await standalone.getByRole('button', { name: /^开始阅读/ }).click()
    assert.equal(
      await standalone
        .locator('.reader-paragraph-text')
        .evaluateAll((es) => es.map((e) => e.textContent).join('')),
      visible(
        fs.readFileSync(
          path.join(root, 'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'),
          'utf8',
        ),
      ),
    )
    await standalone.getByRole('button', { name: '设置', exact: true }).click()
    await standalone.getByRole('button', { name: '查看战区地图', exact: true }).click()
    await standalone.locator('.map-phases>button').nth(2).click()
    await standalone.getByRole('button', { name: '关闭面板', exact: true }).click()
    await standalone.locator('#reader-panel-title').filter({ hasText: '阅读设置' }).waitFor()
    await standalone.getByRole('button', { name: '关闭面板', exact: true }).click()
    await standalone.locator('dialog[open]').waitFor({ state: 'hidden' })
    await standalone.getByRole('button', { name: '打开章节目录', exact: true }).click()
    await standalone.getByRole('button', { name: '本章对白', exact: true }).click()
    await standalone.locator('.reader-results>button').first().click()
    await standalone.waitForFunction(() => document.querySelector('audio').currentTime > 0)
    assert.deepEqual(api, [])
    report.standalone_text_map_real_audio_without_api = true
    assert.equal((await call(prefix + '/delivery')).records.length, 0)
    report.manual_review_left_pending = true
    assert.deepEqual(errors, [])
    report.passed = true
    report.reader_url = fixture.reader_url
    report.export_url = job.result.play_url
    report.download_url = job.result.download_url
    report.export_id = job.id
    report.files = job.result.file_count
  } catch (e) {
    report.error = String(e.stack || e)
    await page.screenshot({ path: path.join(out, 'failure.png') }).catch(() => {})
    throw e
  } finally {
    fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2))
    if (server) server.close()
    await browser.close()
  }
  console.log(JSON.stringify(report, null, 2))
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
