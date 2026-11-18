// Run the actual forward-encounter clock against controlled manuscript geometry,
// input events, storage and timers. No book data, media, DOM library or network.
const a = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { spawnSync } = require('node:child_process')
const root = path.resolve(__dirname, '../..')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'taleprism-cues-'))
const original = { setTimeout, clearTimeout }
const rect = (top, height, left = 0) => ({ top, bottom: top + height, height, left, right: left + 640, width: 640 })
function events() {
  const table = new Map()
  return {
    addEventListener(k, f) { if (!table.has(k)) table.set(k, new Set()); table.get(k).add(f) },
    removeEventListener(k, f) { table.get(k)?.delete(f) },
    emit(k, v = {}) { for (const f of table.get(k) || []) f(v) },
  }
}
try {
  const compile = spawnSync(path.join(root, 'frontend/node_modules/.bin/tsc'), [
    '--strict', '--module', 'commonjs', '--target', 'ES2022', '--skipLibCheck', '--outDir', temp,
    path.join(root, 'frontend/src/reader/useReadingCues.ts'),
  ], { encoding: 'utf8' })
  a.equal(compile.status, 0, compile.stdout + compile.stderr)
  fs.symlinkSync(path.join(root, 'frontend/node_modules'), path.join(temp, 'node_modules'), 'dir')
  const { readingCueConductor } = require(path.join(temp, 'useReadingCues.js'))

  let now = 0, serial = 0
  const clock = new Map(), storage = new Map()
  global.setTimeout = (f, after) => { const id = ++serial; clock.set(id, [now + after, f]); return id }
  global.clearTimeout = (id) => clock.delete(id)
  function advance(ms) {
    const end = now + ms
    for (;;) {
      const next = [...clock].sort((v, w) => v[1][0] - w[1][0])[0]
      if (!next || next[1][0] > end) break
      now = next[1][0]
      clock.delete(next[0])
      next[1][1]()
    }
    now = end
  }
  global.window = { innerWidth: 640, innerHeight: 600, sessionStorage: {
    getItem: (k) => storage.get(k), setItem: (k, v) => storage.set(k, v),
  } }
  global.Node = { DOCUMENT_POSITION_FOLLOWING: 4 }
  global.document = { ...events(), hidden: false }
  function book(edition, rows, lastY = 2700) {
    let cuts = 0
    const hits = [], nodes = []
    const reader = {
      ...events(), scrollTop: 0, clientHeight: 500, scrollHeight: Math.max(500, lastY + 120),
      isConnected: true, getBoundingClientRect: () => rect(40, 500),
      getElementsByClassName: () => [{ getBoundingClientRect: () => rect(40 + lastY - reader.scrollTop - 30, 30) }],
      querySelectorAll: () => nodes.filter((el) => el.enabled),
    }
    for (const [idx, [kind, key, top, h]] of rows.entries()) {
      nodes.push({
        idx, top, h, left: 0, enabled: true, isConnected: true, querySelector: () => null,
        dataset: { ['auto' + kind[0].toUpperCase() + kind.slice(1)]: key },
        getBoundingClientRect() { return rect(40 + this.top - reader.scrollTop, this.h, this.left) },
        compareDocumentPosition: (el) => el.idx > idx ? 4 : 2,
      })
    }
    const opts = { edition, running: true, root: { current: reader }, onCue: (kind, key) => hits.push(kind + ':' + key), onDiscontinuity: () => cuts++ }
    const cues = readingCueConductor(edition, () => opts)
    function move(y) { reader.scrollTop = y; reader.emit('scroll') }
    function scroll(y) { reader.emit('wheel', { deltaY: y - reader.scrollTop }); move(y) }
    const detach = cues.attach(reader)
    return { opts, cues, hits, cuts: () => cuts, nodes, reader, move, scroll, detach }
  }

  // The first sound attempt is synchronous with the opening gesture; on a short
  // whole work the later fold waits for reading time, even below the normal band.
  const rows = [['sound', '0', 20, 44], ['motion', 'reviewed-plate', 88, 130], ['echo', '209', 410, 32]]
  let b = book('editionA', rows, 409)
  b.opts.running = false // React still showing the cover during start(fresh).
  b.cues.begin(false, true, '0')
  a.deepEqual(b.hits, ['sound:0'])
  b.opts.running = true
  advance(699); a.equal(b.hits.length, 1)
  advance(1); a.deepEqual(b.hits, ['sound:0', 'motion:reviewed-plate'])
  advance(4000); a.equal(b.hits.length, 2)
  advance(900); a.deepEqual(b.hits, ['sound:0', 'motion:reviewed-plate', 'echo:209'])
  a.ok(![...storage.values()][0].includes('reviewed-plate'))
  b.cues.consume('echo', '209'); b.scroll(20); advance(5000); a.equal(b.hits.length, 3)
  b.detach()
  b = book('editionA', rows, 409)
  b.cues.begin(false, true, '0'); advance(10000)
  b.scroll(10); advance(2000); a.deepEqual(b.hits, [], 'reload and forward do not replay')
  b.cues.begin(true, true, '0'); advance(6000); a.equal(b.hits.length, 3, 'fresh reread deliberately resets')
  b.detach()

  b = book('editionB', [['sound', '480', 510, 64], ['motion', 'picked', 1000, 200], ['sound', '1800', 1780, 50], ['echo', '2300', 2300, 32]], 2310)
  b.cues.begin(false, false)
  b.move(250); advance(1200); a.deepEqual(b.hits, [], 'restore is not a forward encounter')
  b.scroll(300); advance(219); a.equal(b.hits.length, 0)
  advance(1); a.deepEqual(b.hits, ['sound:480'])
  b.scroll(250); b.scroll(320); advance(850); a.equal(b.hits.length, 1, 'reverse-plus-forward same gesture')
  a.ok(b.cuts() >= 1)
  b.scroll(480); advance(70); b.scroll(670); advance(70); b.scroll(880); advance(2000)
  a.equal(b.hits.length, 1, 'multi-frame fling cannot play its traversed OR landing cues')
  b.scroll(910); advance(250); a.deepEqual(b.hits, ['sound:480', 'motion:picked'], 'a new slow encounter')
  b.cues.invalidate(); b.move(1600); advance(2000); a.equal(b.hits.length, 2, 'jump cannot play')
  b.scroll(1610); advance(230); a.equal(b.hits.at(-1), 'sound:1800')
  b.scroll(1750); advance(230); b.scroll(1930); advance(230); b.scroll(1950); advance(450)
  a.ok(!b.hits.includes('echo:2300'), 'one-frame arrival at bottom is not enough')
  b.scroll(1940); advance(4000); a.ok(!b.hits.includes('echo:2300'), 'reverse cancels dwell')
  b.scroll(1950); advance(1050); a.equal(b.hits.at(-1), 'echo:2300', 'bottom clamp: the fold is below mid-screen but visible')
  b.detach()

  // Suppress a pending quotation on manual handling, hidden document, disabled
  // apparatus, detached marker, scrolling behind a dialog or off-window reflow.
  for (const reason of ['manual', 'hide', 'disabled', 'running', 'removed', 'clip', 'zoom', 'horizontal', 'seek', 'detach']) {
    b = book('cancel-' + reason, [['echo', '60', 360, 30]], 350)
    b.cues.begin(false, true); advance(1200)
    const stale = [...clock.values()][0][1]
    if (reason === 'manual') b.cues.consume('echo', '60')
    if (reason === 'hide') { document.hidden = true; document.emit('visibilitychange'); document.hidden = false }
    if (reason === 'disabled') b.nodes[0].enabled = false
    if (reason === 'running') b.opts.running = false
    if (reason === 'removed') b.opts.root.current = null
    if (reason === 'clip') window.innerHeight = 300
    if (reason === 'zoom') window.visualViewport = { offsetTop: 40, height: 245, offsetLeft: 0, width: 640 }
    if (reason === 'horizontal') b.nodes[0].left = 1000
    if (reason === 'seek') b.cues.invalidate()
    if (reason === 'detach') b.detach()
    stale(); advance(9000); a.deepEqual(b.hits, [], reason)
    b.detach(); window.innerHeight = 600; delete window.visualViewport
  }

  // On a phone, a small early wheel can cancel the opening frame and place
  // prose + its following reviewed art in the same band. Do not choose only
  // the plate, backfill an older paragraph, or require another gesture.
  b = book('neighbors', [
    ['sound', 'offscreen', -70, 30], ['sound', 'older-visible', 69, 28],
    ['sound', 'owner', 110, 54], ['motion', 'too-early', 175, 74], ['motion', 'owner-art', 255, 140],
  ])
  b.cues.begin(false, true); advance(500); b.scroll(68); advance(230)
  a.deepEqual(b.hits, ['sound:owner', 'motion:owner-art'])
  b.scroll(78); advance(1200); a.equal(b.hits.length, 2, 'no backlog for older on-screen cues')
  b.detach()

  b = book('no-scroll-wheel', [['echo', 'fitted', 410, 32]], 409)
  b.cues.begin(false, true); advance(180)
  b.reader.emit('wheel', { deltaY: 70 }) // OS delivers no scroll event at the lower limit.
  advance(4100); a.deepEqual(b.hits, ['echo:fitted'])
  b.detach()

  b = book('keyboard', [['sound', '620', 620, 40]])
  b.cues.begin(false, false)
  b.reader.emit('keydown', { key: 'PageDown' }); b.move(485); advance(250)
  a.deepEqual(b.hits, ['sound:620'], 'one deliberate keyboard page can encounter its destination')
  b.detach()

  // The page can be restored away from the opening before the first paint.
  b = book('early-seek', [['echo', '301', 910, 30]])
  b.cues.begin(false, true); b.move(820); advance(6000); a.deepEqual(b.hits, [])
  b.detach()

  b = book('storage', rows, 409)
  for (let i = 0; i < 2090; i++) b.cues.consume('sound', String(i))
  const raw = storage.get('storage:encounters-v1')
  a.ok(raw.length <= 40000); a.equal(JSON.parse(raw).seen.length, 2048)
  a.equal(b.cues.consume('sound', 'never-evict-the-first'), false)
  b.cues.begin(true, true, '0'); a.deepEqual(b.hits, ['sound:0'])
  b.detach()
  window.sessionStorage.getItem = window.sessionStorage.setItem = () => { throw Error('blocked') }
  b = book('no-storage', rows, 409)
  b.cues.begin(false, true, '0'); b.cues.begin(false, true, '0'); a.deepEqual(b.hits, ['sound:0'])
  b.detach()
  console.log('PASS: forward cue encounters, viewport gates, dwell races, keyboard, bounded once-only ledger')
} finally {
  Object.assign(global, original)
  fs.rmSync(temp, { recursive: true, force: true })
}
