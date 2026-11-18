// Builds and extracts a real private test ZIP, not a mock HTTP page. No network or private inputs.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const http = require('node:http')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const { pathToFileURL } = require('node:url')
const { chromium } = require('playwright')
const root = path.resolve(__dirname, '../..')
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'Taleprism 空格 # '))
const py = process.env.PYTHON || path.join(root, 'backend/.venv/bin/python')
const output = path.join(dir, '完整解压')
const check = (...args) => spawnSync(py, args, { cwd: root, encoding: 'utf8' })
function passed(job) {
  assert.equal(job.status, 0, job.stderr + job.stdout)
}
// Mirror a host mounting the whole extracted folder below an arbitrary prefix.
async function checkHosted(browser, expected) {
  const allowed = JSON.parse(fs.readFileSync(path.join(output, 'storygal-delivery.json'))).files
  const prefix = '/library/example/'
  const files = []
  const server = http.createServer((req, res) => {
    const name = decodeURIComponent(req.url.split('?')[0]).slice(prefix.length)
    if (!req.url.startsWith(prefix) || !Object.hasOwn(allowed, name))
      return res.writeHead(404).end()
    files.push(name)
    const mime = {
      '.html': 'text/html',
      '.js': 'text/javascript',
      '.css': 'text/css',
      '.png': 'image/png',
      '.wav': 'audio/wav',
    }
    res.setHeader('Content-Type', mime[path.extname(name)] || 'application/octet-stream')
    fs.createReadStream(path.join(output, name)).pipe(res)
  })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const context = await browser.newContext()
  try {
    const origin = 'http://127.0.0.1:' + server.address().port
    const page = await context.newPage()
    const unexpected = []
    await context.route('**/*', (r) => {
      if (
        r
          .request()
          .url()
          .startsWith(origin + prefix)
      )
        return r.continue()
      unexpected.push(r.request().url())
      return r.abort()
    })
    page.on('pageerror', (e) => unexpected.push(e.message))
    await page.goto(origin + prefix + 'index.html')
    await page.getByRole('button', { name: /^开始阅读/ }).click()
    await page.locator('.reader-plate-art img').evaluate((i) => i.decode())
    assert.equal(
      await page
        .locator('.reader-paragraph-text')
        .allTextContents()
        .then((x) => x.join('')),
      expected,
    )
    assert.ok(files.includes('assets/reader.js') && !files.includes('reader.json'))
    assert.deepEqual(unexpected, [])
  } finally {
    await context.close()
    await new Promise((resolve) => server.close(resolve))
  }
}
async function main() {
  passed(check(path.join(__dirname, 'portable-reader-fixture.py'), output))
  const verify = () => check('-I', '-B', path.join(output, 'verify_package.py'), output)
  passed(verify())
  const reader = JSON.parse(fs.readFileSync(path.join(output, 'reader.json')))
  const assetPath = (type) =>
    path.join(output, Object.values(reader.media).find((a) => a.type === type).url)
  const photo = assetPath('image'),
    voice = Object.values(reader.media).find((a) => a.origin === 'paragraph_narration'),
    ambience = Object.values(reader.media).find((a) => a.origin === 'paragraph_soundscape'),
    sound = path.join(
      output,
      Object.values(reader.media).find((a) => a.type === 'audio' && a.id !== voice.id && a.id !== ambience.id).url,
    )
  const url = pathToFileURL(path.join(output, 'index.html')).href
  const errors = [],
    network = [],
    requests = []
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined })
  try {
    const context = await browser.newContext({ offline: true, reducedMotion: 'no-preference' })
    const page = await context.newPage()
    page.setDefaultTimeout(7000)
    context.on('request', (r) => {
      requests.push([r.resourceType(), r.url()])
      if (/^https?:/i.test(r.url()) || ['xhr', 'fetch', 'websocket'].includes(r.resourceType()))
        network.push(r.url())
    })
    page.on('pageerror', (e) => errors.push(e.message))
    const open = async (p) => {
      await p.goto(pathToFileURL(path.join(output, 'index.html')).href)
      // Test the independent manual controls; default autoplay has its own browser checks.
      await p.getByRole('button', { name: '安静阅读', exact: true }).click()
    }
    await open(page)
    const text = reader.blocks.map((b) => b.text).join('')
    assert.equal(
      await page
        .locator('.reader-paragraph-text')
        .allTextContents()
        .then((x) => x.join('')),
      text,
    )
    assert.ok(text.includes('</ScRiPt> & <字>。'))
    assert.equal(await page.locator('audio').getAttribute('src'), null)
    assert.equal(await page.locator('.reader-image-motion').count(), 0)
    const art = page.getByRole('button', { name: '放大插图：水洼' })
    await art.locator('img').evaluate((i) => i.decode())
    assert.equal(await art.locator('img').evaluate((i) => i.naturalWidth), 1800)
    await art.click()
    const motion = page.getByRole('button', { name: '开启动效' })
    assert.equal(await motion.getAttribute('aria-pressed'), 'false')
    const canvas = page.locator('.reader-image-motion')
    assert.equal(await canvas.isHidden(), true)
    await motion.click()
    await canvas.waitFor({ state: 'visible' })
    await page.getByRole('button', { name: '关闭动效' }).click()
    await canvas.waitFor({ state: 'hidden' })
    await motion.click()
    await canvas.waitFor({ state: 'visible' })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await canvas.waitFor({ state: 'hidden' })
    assert.equal(await motion.isDisabled(), true)
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    assert.equal(await motion.getAttribute('aria-pressed'), 'false')
    await page.getByRole('button', { name: '关闭面板' }).click()
    const audio = page.locator('audio')
    const narration = page.getByRole('button', { name: /听这一段：第/ })
    const play = page.locator('.reader-inline-audio button').first()
    assert.equal(await audio.count(), 1)
    assert.ok(
      !requests.some(([, u]) => u.endsWith('.wav')),
      'no WAV requested before choosing a cue',
    )
    const scenery = page.getByRole('button', { name: /听此处声景：第/ })
    await scenery.click()
    await page.waitForFunction((id) => {
      const a=document.querySelector('audio')
      return a.currentSrc.includes(id) && a.currentTime>.1 && !a.paused
    }, ambience.id)
    assert.equal(await page.locator('audio').count(), 1)
    await narration.click()
    assert.equal(await scenery.count(), 1, 'narration supersedes ambience; no audio overlap')
    await page.waitForFunction((id) => {
      const a = document.querySelector('audio')
      return a.currentSrc.endsWith(id + '.wav') && a.currentTime > 0 && !a.paused
    }, voice.id)
    await page.getByRole('button', { name: /暂停朗读：第/ }).click()
    assert.equal(await audio.evaluate((a) => a.paused), true)
    await page.getByRole('button', { name: /继续朗读：第/ }).click()
    await page.getByRole('button', { name: /暂停朗读：第/ }).waitFor()
    // A normal dialogue interrupts a live narration instead of mixing two audio tracks.

    await play.click()
    await page.waitForFunction(() => document.querySelector('audio').currentTime > 0)
    await page.waitForFunction(
      (id) => {
        const a = document.querySelector('audio')
        return a.currentSrc.endsWith(id + '.wav') && !a.paused && a.currentTime > 0
      },
      path.basename(sound, '.wav'),
    )
    assert.equal(await audio.evaluate((a) => a.currentSrc.startsWith('file:') && !a.error), true)
    await narration.click()
    await page.waitForFunction(
      (id) => document.querySelector('audio').currentSrc.endsWith(id + '.wav'),
      voice.id,
    )
    await page.getByRole('button', { name: /停止朗读：第/ }).click()
    assert.equal(await audio.getAttribute('src'), null)
    await page.getByRole('button', { name: '设置', exact: true }).click()
    await page.getByRole('button', { name: '收起段落朗读入口' }).click()
    await page.getByRole('button', { name: '关闭面板' }).click()
    assert.equal(await narration.count(), 0)
    assert.equal(await scenery.count(), 1, 'hiding narration does not hide soundscapes')
    assert.equal(
      await page
        .locator('.reader-paragraph-text')
        .allTextContents()
        .then((x) => x.join('')),
      text,
    )

    await page.getByRole('button', { name: '搜索', exact: true }).click()
    await page.getByRole('searchbox').fill('门灯')
    await page.getByText('1 个匹配', { exact: true }).waitFor()
    await page.getByRole('button', { name: '关闭面板' }).click()
    await page.getByRole('button', { name: /^(收藏|书签)$/ }).click()
    await page.getByRole('button', { name: '在当前阅读处加书签' }).click()
    await page.waitForFunction(() =>
      Object.entries(localStorage).some(
        ([k, v]) => k.startsWith('storygal-reader:') && JSON.parse(v).marks.length === 1,
      ),
    )
    await page.reload()
    await page.getByRole('button', { name: /^(开始|继续)阅读/ }).click()
    assert.equal(await audio.getAttribute('src'), null)
    assert.deepEqual(network, [])
    assert.deepEqual(errors, [])
    assert.ok(!requests.some(([, u]) => u.endsWith('/reader.json')), 'zero JSON fetching')
    const imageBytes = fs.statSync(photo).size
    const htmlBytes = fs.statSync(path.join(output, 'index.html')).size
    assert.ok(
      imageBytes > 1000000 && htmlBytes < imageBytes / 10,
      'large media not copied into HTML',
    )
    // Recover from a dropped folder without losing text. A fresh browser context is required
    // so previously loaded file URLs are not satisfied from its private memory cache.
    const damaged = path.join(dir, '缺少素材')
    fs.cpSync(output, damaged, { recursive: true })
    const missingPhoto = path.join(damaged, path.relative(output, photo))
    fs.unlinkSync(missingPhoto)
    fs.unlinkSync(path.join(damaged, path.relative(output, sound)))
    fs.unlinkSync(path.join(damaged, voice.url))
    fs.unlinkSync(path.join(damaged, ambience.url))
    const bad = check('-I', '-B', path.join(damaged, 'verify_package.py'), damaged)
    assert.notEqual(bad.status, 0)
    await context.close()
    const recovery = await browser.newContext({ offline: true })
    const broken = await recovery.newPage()
    broken.setDefaultTimeout(7000)
    broken.on('pageerror', (e) => errors.push(e.message))
    broken.on('request', (r) => {
      if (/^https?:/i.test(r.url()) || ['xhr', 'fetch', 'websocket'].includes(r.resourceType()))
        network.push(r.url())
    })
    await broken.goto(pathToFileURL(path.join(damaged, 'index.html')).href)
    await broken.getByRole('button', { name: '安静阅读', exact: true }).click()
    await broken.getByText('这幅插图暂不可用，正文仍可阅读。').waitFor()
    await broken.getByRole('button',{name:/听此处声景：第/}).click()
    await broken.getByText('声景暂不可用，正文仍可阅读。').waitFor()
    await broken.getByRole('button', { name: /听这一段：第/ }).click()
    await broken.getByText('录音暂不可用，正文仍可阅读。').waitFor()
    await broken.locator('.reader-inline-audio button').first().click()
    await broken
      .getByText(/声音.*(暂未播放|不可用)，可重试/)
      .first()
      .waitFor()
      .catch(async (e) => {
        throw Error(e.message + '\nObserved: ' + (await broken.locator('body').innerText()))
      })
    assert.equal(
      await broken
        .locator('.reader-paragraph-text')
        .allTextContents()
        .then((x) => x.join('')),
      text,
    )
    fs.copyFileSync(photo, missingPhoto)
    await broken
      .getByRole('button', { name: /重试.*水洼/ })
      .first()
      .click()
    await broken.locator('.reader-plate-art img').evaluate((i) => i.decode())
    assert.deepEqual(network, [])
    assert.deepEqual(errors, [])
    await checkHosted(browser, text)
    console.log(
      JSON.stringify({
        passed: true,
        protocol: new URL(url).protocol,
        browser: browser.version(),
        actualCreatorExport: true,
        hostedSubdirectory: true,
        offline: true,
        httpFetchXhrRequests: network.length,
        largeImageBytes: imageBytes,
        htmlBytes,
        utf8Text: true,
        foldedSearch: true,
        bookmarkReload: true,
        motionOptInAndReduced: true,
        privateDirectionOmittedAndManualPause: true,
        generatedWavPlayback: true,
        manualNarrationOnly: true,
        ambienceAndSpeechExclusive: true,
        mutualAudioExclusion: true,
        hideCuePreservesText: true,
        narrationFailureKeepsText: true,
        privateCreditAndFilenameExcluded: true,
        missingMediaTextAndRetry: true,
        corruptedInventoryRejected: true,
      }),
    )
  } finally {
    await browser.close()
  }
}
main()
  .catch((e) => {
    console.error(e)
    process.exitCode = 1
  })
  .finally(() => fs.rmSync(dir, { recursive: true, force: true }))
