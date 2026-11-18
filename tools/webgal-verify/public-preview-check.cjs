// Exercise the untouched ZIP payloads. Inputs are prepared by check_public_preview.py.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
let chromium
try {
  ;({ chromium } = require('playwright'))
} catch {
  throw Error('Playwright is missing. Run npm --prefix tools/webgal-verify ci --omit=dev first.')
}

async function walk(
  browser,
  rootDir,
  book,
  { width, quiet = false, reduce = false, mute = false },
) {
  const folder = path.join(rootDir, book)
  const story = JSON.parse(fs.readFileSync(path.join(folder, 'reader.json'), 'utf8'))
  const expected = story.blocks.map((b) => b.text)
  const cues = story.blocks.flatMap((b, i) => (b.soundscape ? [{ idx: i, cue: b.soundscape }] : []))
  assert.equal(cues.length, 1)
  const expectedWav = path.basename(story.media[cues[0].cue.id].url)
  const motion = book === 'the-door-left-open'
  const foldedQuote = story.config.echo_fold?.earlier.quote || ''
  const context = await browser.newContext({
    offline: true,
    serviceWorkers: 'block',
    reducedMotion: reduce ? 'reduce' : 'no-preference',
    viewport: { width, height: width < 600 ? 740 : 620 },
  })
  const errors = [],
    net = []
  const where = JSON.stringify({ book, width, quiet, reduce, mute })
  try {
    await context.addInitScript(() => {
      window.plays = []
      addEventListener(
        'playing',
        (e) => {
          if (e.target instanceof HTMLAudioElement) {
            window.plays.push({ url: e.target.currentSrc, trusted: e.isTrusted })
          }
        },
        true,
      )
    })
    context.on('request', (r) => {
      if (!/^(file|blob|data):/.test(r.url())) net.push(r.url())
    })
    const p = await context.newPage()
    p.setDefaultTimeout(8500)
    p.on('pageerror', (e) => errors.push(e.message))
    p.on('websocket', (w) => net.push(w.url()))
    await p.goto(pathToFileURL(path.join(folder, 'index.html')).href)
    await p.getByRole('button', { name: /^开始阅读/ }).waitFor()
    assert.equal(
      await p.locator('audio[src],canvas.reader-inline-motion,.reader-echo-leaf').count(),
      0,
      'unsafe cover',
    )
    assert.deepEqual(await p.evaluate(() => window.plays), [])
    await p.getByRole('button', { name: quiet ? '安静阅读' : /^开始阅读/ }).click()
    const prose = p.locator('.reader-paragraph-text')
    await prose.first().waitFor()
    assert.deepEqual(await prose.allTextContents(), expected)
    if (quiet) await p.getByRole('button', { name: '继续自动演绎', exact: true }).waitFor()
    if (mute) await p.getByRole('button', { name: '全部静音', exact: true }).click()
    const scroll = p.locator('.reader-scroll')
    const bound = await scroll.boundingBox()
    await p.mouse.move(bound.x + bound.width / 2, bound.y + bound.height * 0.57)
    let observed = {
      wet: 0,
      dry: 0,
      clock: 0,
      fold: '',
      bottom: false,
      loadedPlate: false,
      canvas: false,
    }
    await p.waitForTimeout(750)
    assert.equal(
      await p.locator('.reader-echo-leaf blockquote').count(),
      0,
      'early quote disclosure',
    )
    const snapshot = async () => {
      const s = await p.evaluate(() => {
        const root = document.querySelector('.reader-scroll')
        const a = document.querySelector('audio')
        const c = document.querySelector('canvas.reader-inline-motion:not([hidden])')
        let wet = 0,
          dry = 0
        if (c && c.width && c.height) {
          const bytes = c.getContext('2d').getImageData(0, 0, c.width, c.height).data
          for (let n = 3; n < bytes.length; n += 4) {
            if (bytes[n]) ((n - 3) / 4) % c.width < c.width / 2 ? dry++ : wet++
          }
        }
        const img = document.querySelector('.reader-plate-art img')
        return {
          wet,
          dry,
          clock: a && !a.paused && !a.muted && a.volume > 0 ? a.currentTime : 0,
          fold: document.querySelector('.reader-echo-leaf blockquote')?.textContent || '',
          loadedPlate: !!img?.complete && img.naturalWidth > 0,
          bottom: root.scrollTop + root.clientHeight >= root.scrollHeight - 2,
          canvas: !!c,
        }
      })
      observed = {
        wet: Math.max(observed.wet, s.wet),
        dry: Math.max(observed.dry, s.dry),
        clock: Math.max(observed.clock, s.clock),
        fold: s.fold || observed.fold,
        loadedPlate: s.loadedPlate || observed.loadedPlate,
        bottom: s.bottom,
        canvas: observed.canvas || s.canvas,
      }
    }
    for (let i = 0; i < 70; i++) {
      await snapshot()
      if (observed.bottom) {
        await p.waitForTimeout(2000)
        await snapshot()
        break
      }
      await p.mouse.wheel(0, 80)
      // Genuine forward wheel and dwell: no scrollIntoView, JS play(), autoplay flags
      // or mocked clock. Echo presentation has its own 800 ms editorial delay.
      await p.waitForTimeout(quiet ? 410 : 1180)
    }
    const played = await p.evaluate(() => window.plays)
    assert(
      observed.bottom && observed.loadedPlate,
      where + ': did not read the complete illustrated edition',
    )
    assert.deepEqual(
      played.map((e) => path.basename(e.url)),
      quiet || mute ? [] : [expectedWav],
      where,
    )
    assert(
      played.every((e) => e.trusted),
      where + ': unexpected synthetic media event',
    )
    assert(
      quiet || mute ? observed.clock === 0 : observed.clock > 0.08,
      where + ': no native playback clock',
    )
    if (quiet || reduce || !motion)
      assert.equal(observed.canvas, false, where + ': unexpected animation')
    else assert(observed.wet > 0, where + ': no rendered motion on the reviewed wet road')
    assert.equal(observed.dry, 0, where + ': animation crossed the protected left side')
    assert.equal(observed.fold, quiet ? '' : foldedQuote, where + ': wrong fold')
    assert.equal(await p.locator('dialog[open]').count(), 0)
    if (quiet) {
      await p.getByRole('button', { name: /^听此处声景/ }).click()
      await p.waitForFunction(() => {
        const a = document.querySelector('audio')
        return a && !a.paused && !a.error && a.currentTime > 0.12
      })
      assert.equal(
        await p.evaluate(() => window.plays.length),
        1,
        where + ': quiet mode lost manual playback',
      )
    } else {
      await p.getByRole('button', { name: '暂停自动演绎', exact: true }).click()
      await p.waitForFunction(() => document.querySelector('audio').paused)
      assert.equal(await p.locator('canvas.reader-inline-motion:not([hidden])').count(), 0)
    }
    assert.deepEqual(await prose.allTextContents(), expected)
    assert.deepEqual(net, [], where + ': reader attempted network access')
    assert.deepEqual(errors, [], where + ': page error')
    console.log('PASS', where)
  } finally {
    await context.close()
  }
}

async function main() {
  const [rootDir, executablePath] = process.argv.slice(2)
  const b = await chromium.launch({ executablePath }).catch((error) => {
    throw new Error(
      'Could not launch a local browser. Retry with --chromium /path/to/a/working/chrome ' +
        'on a host that supports headless Chromium. No checks were skipped.\n' +
        error.message,
    )
  })
  try {
    for (const [book, opts] of [
      ['the-door-left-open', { width: 980 }],
      ['the-margin', { width: 390 }],
      ['the-door-left-open', { width: 390, reduce: true }],
      ['the-margin', { width: 980, mute: true }],
      ['the-margin', { width: 390, quiet: true }],
      ['the-door-left-open', { width: 980, quiet: true }],
    ])
      await walk(b, rootDir, book, opts)
    console.log('Verified both public offline reading ZIPs in Chromium', b.version())
  } finally {
    await b.close()
  }
}
main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
