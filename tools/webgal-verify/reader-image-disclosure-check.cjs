const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')

const root = path.resolve(__dirname, '../..')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'tale-reader-image-disclosure-'))
try {
  const compile = spawnSync(path.join(root, 'frontend/node_modules/.bin/tsc'), [
    '--module', 'commonjs', '--target', 'ES2022', '--strict', '--skipLibCheck',
    '--jsx', 'react-jsx', '--outDir', temp,
    path.join(root, 'frontend/src/reader/imageBrowsing.ts'),
    path.join(root, 'frontend/src/reader/ReaderImageDisclosure.tsx'),
    path.join(root, 'frontend/src/reader/storyGraph.ts'),
  ], { encoding: 'utf8' })
  assert.equal(compile.status, 0, compile.stdout + compile.stderr)
  fs.symlinkSync(path.join(root, 'frontend/node_modules'), path.join(temp, 'node_modules'), 'dir')
  const {
    openImageVisit, requestImage, confirmImageDisclosure, cancelImageDisclosure,
  } = require(path.join(temp, 'reader/imageBrowsing.js'))
  const { ReaderImageDisclosure } = require(path.join(temp, 'reader/ReaderImageDisclosure.js'))
  const { renderToStaticMarkup } = require(path.join(temp, 'node_modules/react-dom/server'))
  const { resolveStoryGraph } = require(path.join(temp, 'reader/storyGraph.js'))
  const raw = fs.readFileSync(path.join(root, 'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'))
  const text = raw.toString('utf8')
  const fixture = {
    project: { canonical_sha256: require('node:crypto').createHash('sha256').update(raw).digest('hex') },
    blocks: Array.from(text.matchAll(/[^\r\n]+/g), (m) => {
      const byte_start = Buffer.byteLength(text.slice(0, m.index))
      return { text: m[0], byte_start, byte_end: byte_start + Buffer.byteLength(m[0]) }
    }),
  }
  const protectFuture = !!resolveStoryGraph(fixture)
  assert.equal(protectFuture, true, 'the existing exact-edition graph is the only feature gate')
  const record = { resume: { byte: 0, offset: 0 }, furthest: 0, marks: [{ id: 'bookmark' }] }
  const before = JSON.stringify(record)
  const original = Object.freeze(openImageVisit('first', record.resume.byte))
  let visit = original
  // Original repro: eight Next clicks at 0% must not quietly reach the fire image.
  for (let i = 0; i < 8; i++) visit = requestImage(visit, 'second', 500, protectFuture)
  assert.equal(visit.asset, 'first')
  assert.equal(visit.pending, 'second')
  assert.equal(visit.whole, false)
  assert.equal(original.pending, null, 'all transitions are immutable')
  visit = cancelImageDisclosure(visit)
  assert.equal(visit.pending, null)
  assert.equal(visit.asset, 'first')
  visit = confirmImageDisclosure(requestImage(visit, 'second', 500, protectFuture))
  assert.equal(visit.asset, 'second')
  assert.equal(visit.whole, true)
  for (let i = 3; i <= 9; i++) visit = requestImage(visit, `image-${i}`, i * 500, protectFuture)
  assert.equal(visit.asset, 'image-9', 'one deliberate confirmation permits the rest of this visit')
  assert.equal(visit.pending, null)
  assert.equal(visit.boundary, 0, 'disclosure is never reading progress')
  assert.equal(JSON.stringify(record), before, 'resume, furthest and bookmarks are untouched')

  visit = openImageVisit('first', 1000)
  visit = requestImage(visit, 'second', 500, true)
  assert.equal(visit.asset, 'second', 'already reached next images need no confirmation')
  assert.equal(visit.whole, false)
  visit = requestImage(visit, 'third', 1000, true)
  assert.equal(visit.asset, 'third', 'the exact display boundary counts as reached')
  visit = requestImage(visit, 'later', 1001, true)
  assert.equal(visit.asset, 'third')
  assert.equal(visit.pending, 'later')
  // A relocated plate uses its later display boundary, not its earlier evidence anchor.
  visit = requestImage(openImageVisit('first', 6014), 'relocated', Math.max(6014, 6136), true)
  assert.equal(visit.asset, 'first')
  assert.equal(visit.pending, 'relocated')
  visit = requestImage(openImageVisit('inline-current', 6011), 'earlier', 3000, true)
  visit = requestImage(visit, 'inline-current', 6136, true)
  assert.equal(visit.asset, 'inline-current', 'the initially visible inline plate remains revisitable')

  for (const boundary of [0, 1000]) {
    visit = openImageVisit('first', boundary)
    assert.equal(visit.whole, false, 'exit/reopen and Back/Forward begin a new bounded visit')
    assert.equal(requestImage(visit, 'future', 2000, true).asset, 'first')
  }
  visit = requestImage(openImageVisit('gallery-item', 0, true), 'last', 30000, true)
  assert.equal(visit.asset, 'last', 'the explicitly whole-chapter gallery remains unrestricted')
  const custom = { ...fixture, project: { canonical_sha256: 'other-edition' } }
  assert.equal(resolveStoryGraph(custom), null)
  visit = requestImage(openImageVisit('first', 0), 'future', 2000, !!resolveStoryGraph(custom))
  assert.equal(visit.asset, 'future', 'unsupported books keep their existing free browsing')
  for (const byte of [NaN, Infinity, -1]) {
    assert.equal(requestImage(openImageVisit('first', 0), 'unknown', byte, true).asset, 'first')
    assert.equal(requestImage(openImageVisit('first', byte), 'later', 1, true).asset, 'first')
  }

  const calls = []
  const tree = ReaderImageDisclosure({
    onReturn: () => calls.push('return'), onStay: () => calls.push('stay'),
    onConfirm: () => calls.push('confirm'),
  })
  const html = renderToStaticMarkup(tree)
  for (const label of ['后面的插图尚未读到', '返回正文', '继续当前画面', '查看全卷插图']) {
    assert.ok(html.includes(label))
  }
  assert.ok(!/火起三江|<img|<dialog/.test(html), 'the notice contains no future asset, title or nested modal')
  const buttons = tree.props.children[2].props.children
  buttons.forEach((button) => button.props.onClick())
  assert.deepEqual(calls, ['return', 'stay', 'confirm'])
  console.log('Image disclosure: repeated Next, reached/display boundaries, one visit-only confirmation, cancel/reopen, whole gallery, generic fallback and accessible neutral notice passed.')
} finally {
  fs.rmSync(temp, { force: true, recursive: true })
}
