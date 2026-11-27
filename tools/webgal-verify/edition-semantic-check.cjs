// Final-payload acceptance: no jsdom, virtual timers, scripted play/dispatch,
// autoplay overrides, forced scrollTop or upstream fixture masquerading as a ZIP.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require('playwright')

async function inspect(browser, job, want, policy) {
  const live = job.url.startsWith('https:')
  const width = policy === 'normal' || policy === 'mute' ? 980 : 390
  const context = await browser.newContext({
    viewport: { width, height: 750 },
    offline: !live,
    serviceWorkers: 'block',
    reducedMotion: policy === 'reduced' ? 'reduce' : 'no-preference',
  })
  const story = JSON.parse(fs.readFileSync(path.join(job.folder, 'reader.json')))
  const errors = [],
    outside = []
  const p = await context.newPage()
  p.setDefaultTimeout(12000)
  p.on('pageerror', (e) => errors.push(String(e)))
  p.on('request', (r) => {
    if (/^https?:/.test(r.url()) && !(live && r.url().startsWith(job.url))) outside.push(r.url())
  })
  try {
    await p.addInitScript(() => {
      window.editionEvents = []
      const intersects = (el) => {
        if (!el) return false
        const sc = document.querySelector('.reader-scroll')?.getBoundingClientRect()
        if (!sc) return false
        const r = el.getBoundingClientRect()
        return r.bottom > Math.max(sc.top, 0) && r.top < Math.min(innerHeight, sc.bottom)
      }
      document.addEventListener(
        'playing',
        (e) => {
          if (e.target.tagName !== 'AUDIO') return
          window.editionEvents.push({
            asset: decodeURIComponent(new URL(e.target.currentSrc).pathname.split('/').pop()),
            trusted: e.isTrusted,
            time: e.target.currentTime,
            visible: [...document.querySelectorAll('[data-auto-sound]')]
              .filter(intersects)
              .map((x) => x.dataset.autoSound),
          })
        },
        true,
      )
      document.addEventListener(
        'toggle',
        (e) => {
          if (e.target.matches('.reader-echo-fold') && e.target.open)
            window.editionEvents.push({
              fold: e.target.dataset.autoEcho,
              visibleFold: intersects(e.target),
            })
        },
        true,
      )
    })
    // Pages may still be fetching artwork when the reader is already usable.
    // Keep interaction timeouts separate from a bounded live network navigation.
    const response = await p.goto(job.url, {
      waitUntil: live ? 'domcontentloaded' : 'load',
      timeout: live ? 60000 : 12000,
    })
    if (live) {
      assert(response?.ok(), 'Live reader document did not return a successful response')
      assert.equal(p.url(), job.url, 'Live reader moved away from the expected address')
    }
    const cover = p.getByRole('button', { name: /^开始阅读/ })
    await cover.waitFor()
    assert.equal(
      await p
        .locator('audio[src],canvas.reader-inline-motion,.reader-echo-leaf blockquote')
        .count(),
      0,
      'Cover must be inert',
    )
    assert.deepEqual(await p.evaluate(() => window.editionEvents), [])
    await (
      policy === 'quiet' ? p.getByRole('button', { name: '安静阅读', exact: true }) : cover
    ).click()
    await p.locator('.reader-paragraph-text').first().waitFor()
    assert.deepEqual(
      await p.locator('.reader-paragraph-text').allTextContents(),
      story.blocks.map((x) => x.text),
    )
    const echoByte = want.echo
      ? String(story.blocks[want.echo.later.paragraph - 1].byte_start)
      : null
    const actual = await p.evaluate(() => {
      const list = (selector) => [...document.querySelectorAll(selector)]
      let prior = -1
      const plates = []
      for (const node of document.querySelector('article.reader-prose').children) {
        if (node.matches('.reader-paragraph')) prior = Number(node.dataset.byteStart)
        if (node.matches('.reader-plate')) {
          const img = node.querySelector('img')
          plates.push([
            node.dataset.illustrationId,
            Number(node.dataset.displayAfterByte),
            prior,
            img?.alt,
          ])
        }
      }
      return {
        sound: list('[data-auto-sound]').map((x) => x.dataset.autoSound),
        motion: list('[data-auto-motion]').map((x) => x.dataset.autoMotion),
        echo: list('[data-auto-echo]').map((x) => x.dataset.autoEcho),
        plates,
      }
    })
    const motions = want.illustrations.filter((x) => x.motion).map((x) => x.id)
    assert.deepEqual(
      actual.sound,
      want.soundscapes.map((x) => String(x.byte)),
      'Sound markers (including intentional silence)',
    )
    assert.deepEqual(actual.echo, echoByte === null ? [] : [echoByte], 'Echo markers')
    assert.deepEqual(actual.motion, motions, 'Actual runtime-eligible motion plates')
    assert.deepEqual(
      actual.plates,
      want.illustrations.map((x) => [
        x.id,
        x.display_after_byte,
        story.blocks.find((b) => b.byte_end === x.display_after_byte)?.byte_start,
        x.description,
      ]),
      'Actual caption/description & preceding paragraph; do not reveal poem art before its verse',
    )
    if (policy === 'mute') await p.getByRole('button', { name: '全部静音', exact: true }).click()
    const allowedSound = !['quiet', 'mute'].includes(policy),
      allowedMotion = !['quiet', 'reduced'].includes(policy),
      allowedEcho = policy !== 'quiet'
    const root = p.locator('.reader-scroll'),
      bb = await root.boundingBox()
    await p.mouse.move(bb.x + bb.width * 0.5, bb.y + bb.height * 0.61)
    const frames = new Map(),
      heard = new Set(),
      opened = new Set()
    let liveArtWaitMs = 0,
      maxClock = 0,
      atTarget = false,
      bottom = false,
      permissionClicks = 0
    const observe = async () => {
      const s = await p.evaluate(() => {
        const seen = []
        for (const c of document.querySelectorAll('canvas.reader-inline-motion:not([hidden])')) {
          if (!c.width || !c.height) continue
          const data = c.getContext('2d').getImageData(0, 0, c.width, c.height).data
          let alpha = 0,
            sig = 2166136261
          for (let n = 3; n < data.length; n += 4)
            if (data[n]) {
              alpha++
              sig = Math.imul(sig ^ n, 16777619) ^ data[n]
            }
          if (alpha)
            seen.push([c.closest('[data-illustration-id]').dataset.illustrationId, alpha, sig])
        }
        const a = document.querySelector('audio'),
          sc = document.querySelector('.reader-scroll'),
          h = sc.getBoundingClientRect()
        const targets = [
          ...sc.querySelectorAll('[data-auto-sound],[data-auto-motion],[data-auto-echo]'),
        ]
        return {
          seen,
          events: window.editionEvents,
          quote: document.querySelector('.reader-echo-leaf blockquote')?.textContent,
          clock: a && !a.muted && !a.paused && a.volume > 0 ? a.currentTime : 0,
          bottom: sc.scrollHeight - sc.clientHeight - sc.scrollTop <= 2,
          step: Math.max(64, Math.floor(Math.min(290, h.height * 0.36))),
          loadingMotion: targets.filter((el) => {
            if (!el.dataset.autoMotion) return false
            const r = el.getBoundingClientRect(), img = el.querySelector('img')
            return img && (!img.complete || !img.naturalWidth)
              && r.bottom > h.top && r.top < h.top + h.height * 0.72
          }).map((el) => el.dataset.autoMotion),
          near: targets.some((el) => {
            const r = el.getBoundingClientRect()
            return r.top < h.top + h.height * 0.72 && r.bottom > h.top + 4
          }),
          beyond: targets.every((el) => el.getBoundingClientRect().bottom < h.top - 5),
        }
      })
      maxClock = Math.max(maxClock, s.clock)
      for (const [id, , sig] of s.seen) {
        assert(allowedMotion && motions.includes(id), 'Unapproved or suppressed frame: ' + id)
        if (!frames.has(id)) frames.set(id, new Set())
        frames.get(id).add(sig)
      }
      for (const e of s.events) {
        if (e.asset) {
          assert(
            allowedSound && e.trusted && e.visible.length,
            'Unprompted, hidden or suppressed playback: ' + JSON.stringify(e),
          )
          heard.add(e.asset)
        } else if (e.fold) {
          assert(
            allowedEcho && e.fold === echoByte && e.visibleFold,
            'Echo disclosed at wrong time',
          )
          opened.add(e.fold)
        }
      }
      if (s.quote) {
        assert(allowedEcho)
        assert.equal(s.quote, want.echo?.earlier.quote, 'Unexpected earlier quote')
      }
      bottom = s.bottom
      atTarget = s.beyond
      return s
    }
    const ids = want.soundscapes.map((v) => story.blocks[v.paragraph - 1].soundscape.id)
    for (let i = 0; i < 360; i++) {
      let s = await observe()
      if (live && s.loadingMotion.length) {
        // A person pausing to inspect a reached illustration does not wheel away
        // while its pixels are still in flight. Do not prefetch or reveal ahead.
        const start = Date.now()
        await p.waitForFunction((ids) => ids.every((id) =>
          [...document.querySelectorAll('[data-auto-motion]')].some((el) => {
            const img = el.querySelector('img')
            return el.dataset.autoMotion === id && img?.complete && img.naturalWidth > 0
          }),
        ), s.loadingMotion, { timeout: 60000 })
        liveArtWaitMs += Date.now() - start
        s = await observe()
      }
      // Dwell where a reader actually reaches material. Allow the ordinary UI
      // one real consent click when policy blocks playback; no JS play().
      if (s.near || bottom) {
        await p.waitForTimeout(980)
        const allow = p.getByRole('button', { name: '开启声音', exact: true })
        if (allowedSound && (await allow.isVisible())) {
          assert.equal(permissionClicks++, 0, 'Repeated permission fallback')
          await allow.click()
        }
        s = await observe()
        if (s.seen.length) {
          await p.waitForTimeout(150)
          await observe()
        }
      }
      const done =
        (!allowedSound || (heard.size === ids.length && maxClock > 0.08)) &&
        (!allowedMotion || motions.every((id) => (frames.get(id)?.size || 0) >= 2)) &&
        (!allowedEcho || !want.echo || opened.size === 1)
      if (bottom) {
        await p.waitForTimeout(2000)
        await observe()
        break
      }
      if (atTarget && done) break
      const short = want.paragraphs <= 6
      await p.mouse.wheel(0, short ? 80 : s.near ? 85 : s.step)
      await p.waitForTimeout(short ? 1180 : s.near ? 310 : 145)
    }
    assert(bottom || atTarget, 'Did not pass every authored encounter')
    const expectedFiles = ids.map((id) => path.basename(story.media[id].url))
    assert.deepEqual([...heard], allowedSound ? expectedFiles : [])
    const played = await p.evaluate(() => window.editionEvents.filter((e) => e.asset))
    assert.deepEqual(
      played.map((e) => e.asset),
      allowedSound ? expectedFiles : [],
      'Unexpected replay',
    )
    assert(
      allowedSound ? maxClock > 0.08 : maxClock === 0,
      'Native audio time did not respect policy',
    )
    assert.deepEqual([...frames.keys()], allowedMotion ? motions : [])
    for (const [id, v] of frames) assert(v.size >= 2, 'Static/nonchanging canvas ' + id)
    assert.equal(
      opened.size,
      allowedEcho && want.echo ? 1 : 0,
      'Expected actual timed echo disclosure; observed ' +
        JSON.stringify(
          await p.evaluate(() => ({
            events: window.editionEvents,
            quote: document.querySelector('.reader-echo-leaf blockquote')?.textContent,
            top: document.querySelector('.reader-scroll').scrollTop,
          })),
        ),
    )
    assert.deepEqual(outside, [])
    assert.deepEqual(errors, [])
    return {
      book: job.slug,
      kind: job.kind,
      policy,
      ...(live ? { live_reached_art_wait_ms: liveArtWaitMs } : {}),
      visible_plates: actual.plates.length,
      sound_play_count: played.length,
      native_audio_advanced: maxClock > 0.08,
      changed_motion: [...frames.keys()],
      echo_reveals: opened.size,
    }
  } finally {
    await context.close()
  }
}

async function main() {
  const [infile, chromepath, report] = process.argv.slice(2),
    { jobs, books } = JSON.parse(fs.readFileSync(infile))
  const b = await chromium.launch({ executablePath: chromepath })
  const output = { browser_version: b.version(), results: [] }
  try {
    // Bounded concurrency; each isolated browser context reads a real untouched
    // ZIP or site. Keep test state/disclosures independent between policies.
    const queue = jobs.flatMap((j) =>
      (j.kind === 'cold'
        ? ['normal']
        : j.slug === 'the-door-left-open'
          ? ['normal', 'quiet', 'reduced']
          : j.slug === 'the-margin'
            ? ['normal', 'mute', 'quiet']
            : ['normal', 'quiet']
      ).map((mode) => [j, mode]),
    )
    async function worker() {
      for (let entry; (entry = queue.shift()); ) {
        const [j, mode] = entry
        try {
          const x = await inspect(b, j, j.expected || books[j.slug], mode)
          output.results.push(x)
          console.log('PASS', JSON.stringify(x))
        } catch (e) {
          throw Error(j.slug + '/' + j.kind + '/' + mode + ': ' + (e.stack || e))
        }
      }
    }
    await Promise.all([worker(), worker()])
    fs.writeFileSync(report, JSON.stringify(output) + '\n')
  } finally {
    await b.close()
  }
}
main().catch((e) => {
  console.error(e)
  process.exitCode = 1
})
