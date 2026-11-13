// Run against an isolated workbench with a freshly rebuilt local example.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const { spawnSync } = require('node:child_process')
const { chromium } = require('playwright')
const root = path.resolve(__dirname, '../..')
const base = process.argv[2] || 'http://127.0.0.1:8003'
const version = JSON.parse(fs.readFileSync(path.join(root, 'frontend/package.json'), 'utf8')).version
const out = path.resolve(process.argv[3] || path.join(root, '.release/v' + version))
const archive = path.join(out, 'taleprism-v' + version + '-last-light-project.zip')

;(async () => {
  fs.mkdirSync(out, { recursive: true })
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = [], report = { passed: false, checked_at: new Date().toISOString() }
  let server
  page.on('pageerror', e => errors.push(e.message))
  async function json(url, method = 'GET', data) {
    const r = await page.request.fetch(base + url, { method, data })
    assert.ok(r.ok(), await r.text())
    return r.json()
  }
  async function importUI(buffer, name) {
    const response = page.waitForResponse(r => r.url().endsWith('/api/project-bundles') && r.request().method() === 'POST')
    await page.getByLabel('导入可编辑工程', { exact: true }).setInputFiles({ name, mimeType: 'application/zip', buffer })
    const r = await response
    assert.equal(r.status(), 201, await r.text())
    const project = await r.json()
    await page.getByRole('heading', { name: '章节制作方案', exact: true }).waitFor()
    return project
  }
  async function openShot(index) {
    const s = page.locator('.production-shot').nth(index)
    if (!(await s.evaluate(e => e.open))) await s.locator(':scope > summary').click()
    return s
  }
  async function decision(index, name) {
    const s = await openShot(index)
    if (name === '检查通过') for (const box of await s.locator('.continuity-checklist input').all()) await box.check()
    await s.getByRole('textbox', { name: '连续性检查说明／不通过或撤销原因', exact: true })
      .fill('浏览器回归测试：验证检查状态与后续流程，不作为作品最终艺术验收。')
    const response = page.waitForResponse(r => r.url().endsWith('/continuity-check') && r.request().method() === 'POST')
    await s.getByRole('button', { name, exact: true }).click()
    assert.ok((await response).ok())
    await page.waitForFunction(i => Array.from(document.querySelectorAll('.production-shot')[i].querySelectorAll('textarea'))
      .some(e => e.placeholder.startsWith('记录检查结论') && e.value === ''), index)
  }
  try {
    await page.goto(base)
    const initial = await importUI(fs.readFileSync(archive), 'checked-example.zip')
    let prefix = '/api/projects/' + initial.id
    const checked = await json(prefix + '/production')
    assert.ok(checked.plan.shots.every(s => s.continuity_check.status === 'passed' && s.continuity_check.basis))
    await decision(0, '不通过')
    let state = await json(prefix + '/production')
    assert.deepEqual(state.plan.shots.map(s => s.continuity_check.status), ['rejected', 'revoked', 'revoked'])
    const blocked = await page.request.post(base + prefix + '/production/apply', { data: {
      revision: state.revision, reader_revision: (await json(prefix + '/reader')).revision,
    } })
    assert.equal(blocked.status(), 400)
    await page.getByRole('button', { name: '交付检查', exact: true }).click()
    const issue = page.locator('.delivery-checks article').filter({ hasText: '已应用镜头与制作检查' })
    await issue.getByRole('button', { name: '前往处理', exact: true }).click()
    await page.getByRole('heading', { name: '章节制作方案', exact: true }).waitFor()
    await decision(0, '撤销检查')
    state = await json(prefix + '/production')
    assert.ok(state.plan.shots.every(s => s.continuity_check.status === 'revoked'))
    // A candidate used in the saved composition must restore without approving it.
    const review = await json(prefix + '/review')
    const config = (await json(prefix + '/reader')).config
    const cid = config.scenes.flatMap(s => s.character_ids)[0] || checked.plan.shots[0].actors[0].character_id
    const character = review.characters.find(c => c.id === cid)
    await json(prefix + '/characters/' + cid, 'PATCH', {
      revision: review.revision, display_name: character.display_name, aliases: character.aliases,
      description: character.description, status: 'candidate',
    })
    const draft = await page.request.get(base + prefix + '/bundle')
    assert.ok(draft.ok())
    const restored = await importUI(await draft.body(), 'unfinished-example.zip')
    assert.ok(restored.restore_issues.length)
    await page.getByText('工程仍有待修复内容，原方案与审核状态已保留。请修复并复核后再正式导出。', { exact: true }).waitFor()
    prefix = '/api/projects/' + restored.id
    state = await json(prefix + '/production')
    assert.ok(state.plan.shots.every(s => s.continuity_check.status === 'revoked'))
    const s = await openShot(0)
    await s.locator('.continuity-record').scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(out, 'checks-desktop.png') })
    await page.setViewportSize({ width: 375, height: 950 })
    await s.locator('.continuity-record').scrollIntoViewIfNeeded()
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    await page.screenshot({ path: path.join(out, 'checks-mobile.png') })
    const r = await json(prefix + '/review')
    await json(prefix + '/characters/' + cid, 'PATCH', {
      revision: r.revision, display_name: character.display_name, aliases: character.aliases,
      description: character.description, status: 'confirmed',
    })
    await page.reload()
    await page.getByRole('button', { name: '章节制作方案', exact: true }).click()
    for (const i of [0, 1, 2]) await decision(i, '检查通过')
    const applied = page.waitForResponse(r => r.url().endsWith('/production/apply'))
    await page.getByRole('button', { name: '应用已确认镜头', exact: true }).click()
    assert.ok((await applied).ok())
    assert.ok((await json(prefix + '/delivery')).ready)
    const raw = fs.readFileSync(path.join(root, 'samples/last-light/source.txt'))
    assert.deepEqual(await (await page.request.get(base + prefix + '/source')).body(), raw)
    const jid = (await json(prefix + '/reader/exports', 'POST')).job_id
    let job
    for (let i = 0; i < 100; i++) {
      job = (await json(prefix + '/jobs')).find(j => j.id === jid)
      if (['completed', 'failed'].includes(job.state)) break
      await page.waitForTimeout(100)
    }
    assert.equal(job.state, 'completed', JSON.stringify(job))
    const zip = path.join(out, 'browser-reader.zip'), dir = path.join(out, 'browser-reader', jid)
    fs.writeFileSync(zip, await (await page.request.get(base + job.result.download_url)).body())
    fs.mkdirSync(dir, { recursive: true })
    assert.equal(spawnSync('unzip', ['-q', '-o', zip, '-d', dir]).status, 0)
    const verify = spawnSync('python3', ['verify_package.py'], { cwd: dir, encoding: 'utf8' })
    assert.equal(verify.status, 0, verify.stdout + verify.stderr)
    server = http.createServer((req, res) => {
      const pathname = new URL(req.url, 'http://localhost').pathname
      const file = path.resolve(dir, '.' + decodeURIComponent(pathname === '/' ? '/index.html' : pathname))
      if (!file.startsWith(dir + path.sep) || !fs.existsSync(file)) { res.writeHead(404).end(); return }
      const types = { '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.webp': 'image/webp' }
      res.setHeader('Content-Type', types[path.extname(file)] || 'text/html')
      fs.createReadStream(file).pipe(res)
    })
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
    const independent = await browser.newPage({ viewport: { width: 375, height: 950 } }), apiRequests = []
    independent.on('pageerror', e => errors.push(e.message))
    independent.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/')) apiRequests.push(r.url()) })
    await independent.goto('http://127.0.0.1:' + server.address().port + '/')
    await independent.getByRole('button', { name: /^开始阅读/ }).click()
    for (const img of await independent.locator('.reader-plate img').all()) { await img.scrollIntoViewIfNeeded(); await img.evaluate(e => e.decode()) }
    assert.equal(await independent.locator('.reader-plate').count(), 3)
    assert.equal(await independent.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    const sourceText = raw.toString().split(/\r\n|\r|\n/).map(s => s.replace(/^[ \t\u3000]+|[ \t\u3000]+$/g, '')).join('')
    assert.equal(await independent.locator('.reader-paragraph-text').evaluateAll(es => es.map(e => e.textContent).join('')), sourceText)
    await independent.screenshot({ path: path.join(out, 'reader-mobile.png') })
    assert.deepEqual(apiRequests, [])
    assert.deepEqual(errors, [])
    assert.deepEqual((await json(prefix + '/delivery')).records, [])
    Object.assign(report, { passed: true, explicit_failure_and_revocation: true, downstream_blocked: true,
      draft_restored_with_warning: true, restored_checks_not_promoted: true, recheck_and_export: true,
      source_equal: true, desktop_mobile_no_overflow: true, standalone_without_api: true, page_errors: errors })
  } catch (e) {
    report.error = String(e.stack || e)
    await page.screenshot({ path: path.join(out, 'browser-failure.png') }).catch(() => {})
    throw e
  } finally {
    fs.writeFileSync(path.join(out, 'browser-report.json'), JSON.stringify(report, null, 2) + '\n')
    if (server) server.close()
    await browser.close()
  }
  console.log(JSON.stringify(report, null, 2))
})().catch(e => { console.error(e); process.exit(1) })
