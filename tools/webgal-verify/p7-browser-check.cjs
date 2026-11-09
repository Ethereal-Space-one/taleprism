const assert = require('node:assert/strict')
const fs = require('node:fs'),
  path = require('node:path'),
  http = require('node:http')
const { spawnSync } = require('node:child_process')
const { chromium } = require('playwright')
const root = path.resolve(__dirname, '../..'),
  out = path.join(root, 'data/verification/p7')
const fixture = JSON.parse(fs.readFileSync(path.join(out, 'fixture.json'))),
  base = process.argv[2] || 'http://127.0.0.1:8000'
const report = {
  passed: false,
  checked_at: new Date().toISOString(),
  project_id: fixture.project_id,
}
;(async () => {
  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }),
    errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const prefix = '/api/projects/' + fixture.project_id
  async function json(url, method = 'GET', data) {
    const r = await page.request.fetch(base + url, { method, data })
    assert.ok(r.ok(), await r.text())
    return r.json()
  }
  async function close() {
    await page.getByRole('button', { name: '关闭面板', exact: true }).click()
    await page.locator('dialog[open]').waitFor({ state: 'hidden' })
  }
  async function go(quote) {
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    await page.getByLabel('查找原文', { exact: true }).fill(quote)
    await page.locator('.reader-results>button').first().click()
    await page.waitForTimeout(330)
    await page.waitForFunction(() =>
      Array.from(document.querySelectorAll('.reader-background,.reader-portraits img')).every(
        (e) => e.complete && e.naturalWidth > 0,
      ),
    )
  }
  async function names() {
    return page.locator('.reader-portraits figcaption').allTextContents()
  }
  let server
  try {
    const data = await json(prefix + '/reader/content'),
      figures = Object.values(data.media).filter((m) => m.type === 'figure')
    assert.equal(Object.keys(data.characters).length, 6)
    assert.equal(figures.length, 7)
    assert.equal(
      new Set(data.presentations.flatMap((p) => p.cast.map((c) => c.figure_asset_id))).size,
      7,
    )
    assert.equal(data.issues.length, 0)
    assert.equal(data.preview, false)
    assert.equal((await json(prefix + '/review')).pending_count, 152)
    const raw = fs.readFileSync(
      path.join(root, 'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'),
    )
    const source = await page.request.get(base + prefix + '/source')
    assert.deepEqual(await source.body(), raw)
    await page.goto(base + fixture.reader_url)
    await page.getByRole('button', { name: /^开始阅读/ }).click()
    const visible = raw
      .toString()
      .split(/\r\n|\r|\n/)
      .map((s) => s.replace(/^[ \t\u3000]+|[ \t\u3000]+$/g, ''))
      .join('')
    assert.equal(
      await page
        .locator('.reader-paragraph-text')
        .evaluateAll((es) => es.map((e) => e.textContent).join('')),
      visible,
    )
    assert.deepEqual(await names(), [])
    const cases = [
      ['左右救回帳中', ['周瑜'], true, 'zhouyu-ill'],
      ['卻說魯肅見周瑜臥病', ['鲁肃', '周瑜'], true, 'lusu-zhouyu'],
      ['來見孔明，言周瑜猝病之事', ['鲁肃', '孔明'], false, 'lusu-kongming'],
      ['瑜命請入', ['孔明', '周瑜'], true, 'sick-dialogue'],
      ['瑜聞言大喜，矍然而起', ['孔明', '周瑜'], false, 'zhouyu-rises'],
      ['魯肅別去', ['孔明'], false, 'altar'],
      ['下壇入帳中少歇', [], false],
      ['黃蓋已自準備火船二十隻', ['黄盖'], false, 'huanggai-prepares'],
      ['瑜出帳看時時', ['周瑜', '鲁肃'], false, 'wind'],
      ['時雲長在側', ['孔明', '关羽'], false, 'guanyu-orders'],
      ['雲長領了將令', ['孔明'], false],
      ['卻說曹操在大寨中', ['曹操'], false, 'caocao-camp'],
      ['黃蓋在第三隻火船上', ['黄盖'], false, 'huanggai-departure'],
      ['是時東風大作，波浪洶湧', ['曹操'], false],
      ['黃蓋用刀一招', [], false, 'fire'],
      ['正中肩窩，翻身落水', [], false],
      ['為首大將關雲長', ['关羽'], false, 'guanyu-arrival'],
      ['操從其說，即縱馬向前', ['曹操', '关羽'], false, 'huarong'],
      ['於是把馬頭勒回', [], false],
      ['孔明忙離坐席', ['孔明', '关羽'], false, 'return'],
      ['遂叱武士推出斬之', [], false],
    ]
    for (const [quote, expected, ill, shot] of cases) {
      await go(quote)
      assert.deepEqual(await names(), expected, quote)
      assert.equal(
        await page.locator('.reader-portraits figure[data-state="ill-seated"]').count(),
        ill ? 1 : 0,
        quote,
      )
      if (shot) await page.screenshot({ path: path.join(out, shot + '-1440.png') })
    }
    for (const quote of ['瑜命請入', '操從其說，即縱馬向前', '左右救回帳中']) {
      await go(quote)
      const sourceAt = await page.locator('.reader-root').getAttribute('data-view-byte')
      const castBefore = await names()
      for (const width of [320, 375, 414, 768, 1440]) {
        await page.setViewportSize({ width, height: 1000 })
        await page.waitForTimeout(400)
        assert.equal(
          await page.locator('.reader-root').getAttribute('data-view-byte'),
          sourceAt,
          'resize must retain the source anchor',
        )
        assert.deepEqual(await names(), castBefore, 'resize must retain the cast')
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
          false,
        )
        assert.ok((await page.locator('.reader-portraits figure').count()) <= 2)
        await page.screenshot({
          path: path.join(
            out,
            (quote === '左右救回帳中'
              ? 'ill-single'
              : quote === '瑜命請入'
                ? 'ill-pair'
                : 'huarong') +
              '-' +
              width +
              '.png',
          ),
        })
      }
    }
    report.portrait_budget = { identities: 6, figures: 7, max_on_stage: 2 }
    report.source_equal = true
    report.casting_cases = cases.length
    report.jump_and_state_restoration = true
    report.viewports = [320, 375, 414, 768, 1440]
    // The current default Zhou Yu remains standing, even though the scene can select his illness variant.
    const review = await json(prefix + '/review'),
      zhou = review.characters.find((c) => c.display_name === '周瑜')
    assert.equal(review.assets.find((a) => a.id === zhou.active_figure_id).portrait_state, 'base')
    await page.getByRole('button', { name: '设置', exact: true }).click()
    await page.getByRole('button', { name: '本章对白', exact: true }).click()
    await page.locator('.reader-results>button').first().click()
    await page.waitForFunction(() => document.querySelector('audio').currentTime > 0)
    report.real_existing_voice = true
    const maker = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    maker.on('pageerror', (e) => errors.push(e.message))
    await maker.goto(base)
    await maker.evaluate((id) => localStorage.setItem('storygal-project', id), fixture.project_id)
    await maker.reload()
    await maker.getByRole('button', { name: /^人物与审校/ }).click()
    await maker.getByRole('tab', { name: /角色资产/ }).click()
    await maker.getByRole('button', { name: '编辑角色 周瑜', exact: true }).click()
    await maker.getByLabel('Codex 候选图', { exact: true }).selectOption('zhouyu_ill')
    const options = await maker
      .getByLabel('Codex 候选图', { exact: true })
      .locator('option')
      .allTextContents()
    assert.equal(options.length, 2)
    assert.ok(options.some((s) => s.includes('病中半卧')))
    for (const width of [320, 375, 414, 768, 1440]) {
      await maker.setViewportSize({ width, height: 1000 })
      await maker.waitForTimeout(100)
      assert.equal(
        await maker.evaluate(() => document.documentElement.scrollWidth > innerWidth),
        false,
      )
      await maker.screenshot({ path: path.join(out, 'maker-' + width + '.png'), fullPage: true })
    }
    report.state_selector_and_identity_scoped_candidates = true
    const jobId = (await json(prefix + '/reader/exports', 'POST')).job_id
    let job
    for (let i = 0; i < 200; i++) {
      job = (await json(prefix + '/jobs')).find((j) => j.id === jobId)
      if (job.state !== 'running') break
      await page.waitForTimeout(100)
    }
    assert.equal(job.state, 'completed', JSON.stringify(job))
    const zip = path.join(out, 'storygal-reader-p7.zip')
    fs.writeFileSync(zip, await (await page.request.get(base + job.result.download_url)).body())
    const dir = path.join(out, 'standalone', job.id)
    fs.mkdirSync(dir, { recursive: true })
    assert.equal(spawnSync('unzip', ['-q', '-o', zip, '-d', dir]).status, 0)
    const check = spawnSync('python3', ['verify_package.py'], { cwd: dir, encoding: 'utf8' })
    assert.equal(check.status, 0, check.stdout + check.stderr)
    assert.equal(
      JSON.parse(fs.readFileSync(path.join(dir, 'reader.json'))).presentations.length,
      40,
    )
    assert.ok(fs.existsSync(path.join(dir, 'storygal-source/characters/expansion-v1/prompts.json')))
    server = http.createServer((req, res) => {
      const f = path.resolve(
        dir,
        '.' +
          decodeURIComponent(req.url.split('?')[0] === '/' ? '/index.html' : req.url.split('?')[0]),
      )
      if (!f.startsWith(dir + path.sep) || !fs.existsSync(f)) {
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
    const independent = await browser.newPage(),
      requests = []
    independent.on('request', (r) => {
      if (new URL(r.url()).pathname.startsWith('/api/')) requests.push(r.url())
    })
    independent.on('pageerror', (e) => errors.push(e.message))
    await independent.goto('http://127.0.0.1:' + server.address().port + '/')
    await independent.getByRole('button', { name: /^开始阅读/ }).click()
    await independent.getByRole('button', { name: '搜索', exact: true }).click()
    await independent.getByLabel('查找原文', { exact: true }).fill('操從其說，即縱馬向前')
    await independent.locator('.reader-results>button').first().click()
    await independent.waitForTimeout(350)
    assert.deepEqual(await independent.locator('.reader-portraits figcaption').allTextContents(), [
      '曹操',
      '关羽',
    ])
    await independent.getByRole('button', { name: '设置', exact: true }).click()
    await independent.getByRole('button', { name: '本章对白', exact: true }).click()
    await independent.locator('.reader-results>button').first().click()
    await independent.waitForFunction(() => document.querySelector('audio').currentTime > 0)
    assert.deepEqual(requests, [])
    report.resize_source_and_cast_preserved = true
    report.independent_real_audio = true
    report.independent_export = true
    report.prompt_provenance_included = true
    report.files = job.result.file_count
    report.reader_url = fixture.reader_url
    report.export_url = job.result.play_url
    report.download_url = job.result.download_url
    report.export_id = job.id
    assert.equal((await json(prefix + '/delivery')).records.length, 0)
    report.manual_review_left_pending = true
    assert.deepEqual(errors, [])
    report.passed = true
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
