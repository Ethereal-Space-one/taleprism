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
    path.join(root, 'frontend/src/reader/ReaderGalleryDisclosure.tsx'),
    path.join(root, 'frontend/src/reader/storyGraph.ts'),
  ], { encoding: 'utf8' })
  assert.equal(compile.status, 0, compile.stdout + compile.stderr)
  fs.symlinkSync(path.join(root, 'frontend/node_modules'), path.join(temp, 'node_modules'), 'dir')
  const {
    openImageVisit, restoreImageVisit, placedImage, requestImage, confirmImageDisclosure, cancelImageDisclosure, galleryAtPosition,
  } = require(path.join(temp, 'reader/imageBrowsing.js'))
  const { ReaderImageDisclosure } = require(path.join(temp, 'reader/ReaderImageDisclosure.js'))
  const React = require(path.join(temp, 'node_modules/react'))
  const { ReaderGalleryDisclosure } = require(path.join(temp, 'reader/ReaderGalleryDisclosure.js'))
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
  assert.ok(resolveStoryGraph(fixture), 'historical curated edition has a graph')
  const record = { resume: { byte: 0, offset: 0 }, furthest: 0, marks: [{ id: 'bookmark' }] }
  const before = JSON.stringify(record)
  const original = Object.freeze(openImageVisit('first', record.resume.byte))
  let visit = original
  // Original repro: eight Next clicks at 0% must not quietly reach the fire image.
  for (let i = 0; i < 8; i++) visit = requestImage(visit, 'second', 500)
  assert.equal(visit.asset, 'first')
  assert.equal(visit.pending, 'second')
  assert.equal(visit.whole, false)
  assert.equal(original.pending, null, 'all transitions are immutable')
  visit = cancelImageDisclosure(visit)
  assert.equal(visit.pending, null)
  assert.equal(visit.asset, 'first')
  visit = confirmImageDisclosure(requestImage(visit, 'second', 500))
  assert.equal(visit.asset, 'second')
  assert.equal(visit.whole, true)
  for (let i = 3; i <= 9; i++) visit = requestImage(visit, `image-${i}`, i * 500)
  assert.equal(visit.asset, 'image-9', 'one deliberate confirmation permits the rest of this visit')
  assert.equal(visit.pending, null)
  assert.equal(visit.boundary, 0, 'disclosure is never reading progress')
  assert.equal(JSON.stringify(record), before, 'resume, furthest and bookmarks are untouched')

  visit = openImageVisit('first', 1000)
  visit = requestImage(visit, 'second', 500)
  assert.equal(visit.asset, 'second', 'already reached next images need no confirmation')
  assert.equal(visit.whole, false)
  visit = requestImage(visit, 'third', 1000)
  assert.equal(visit.asset, 'third', 'the exact display boundary counts as reached')
  visit = requestImage(visit, 'later', 1001)
  assert.equal(visit.asset, 'third')
  assert.equal(visit.pending, 'later')
  // A relocated plate uses its later display boundary, not its earlier evidence anchor.
  visit = requestImage(openImageVisit('first', 6014), 'relocated', Math.max(6014, 6136))
  assert.equal(visit.asset, 'first')
  assert.equal(visit.pending, 'relocated')
  visit = requestImage(openImageVisit('inline-current', 6011), 'earlier', 3000)
  visit = requestImage(visit, 'inline-current', 6136)
  assert.equal(visit.asset, 'inline-current', 'the initially visible inline plate remains revisitable')

  for (const boundary of [0, 1000]) {
    visit = openImageVisit('first', boundary)
    assert.equal(visit.whole, false, 'exit/reopen and Back/Forward begin a new bounded visit')
    assert.equal(requestImage(visit, 'future', 2000).asset, 'first')
  }
  visit = requestImage(openImageVisit('gallery-item', 0, true), 'last', 30000)
  assert.equal(visit.asset, 'last', 'the explicitly whole-chapter gallery remains unrestricted')
  const custom = { ...fixture, project: { canonical_sha256: 'other-edition' } }
  assert.equal(resolveStoryGraph(custom), null)
  visit = requestImage(openImageVisit('first', 0), 'future', 2000)
  assert.equal(visit.pending, 'future', 'ordinary books also protect the next unread plate')
  for (const byte of [NaN, Infinity, -1]) {
    assert.equal(requestImage(openImageVisit('first', 0), 'unknown', byte).asset, 'first')
    assert.equal(requestImage(openImageVisit('first', byte), 'later', 1).asset, 'first')
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
  // Gallery uses the same inclusive disclosure boundary, by plate identity,
  // including relocated plates and different plates sharing one image asset.
  const plates = Object.freeze([
    Object.freeze({ id: 'later', image_asset_id: 'shared', after_byte: 2000 }),
    Object.freeze({ id: 'first', image_asset_id: 'shared', after_byte: 500 }),
    Object.freeze({ id: 'relocated', image_asset_id: 'moved', after_byte: 6014 }),
    Object.freeze({ id: 'invalid', image_asset_id: 'invalid', after_byte: NaN }),
  ])
  const presentations = new Map([['relocated', { disclosureByte: 6136 }]])
  const ids = byte => galleryAtPosition(plates, presentations, byte).map(p => p.id)
  assert.deepEqual(ids(0), [], 'zero reached images is an intentional empty state')
  assert.deepEqual(ids(499), [])
  assert.deepEqual(ids(500), ['first'], 'inclusive boundary; shared asset never reveals later title')
  assert.deepEqual(ids(2000), ['later', 'first'], 'original configured order is preserved')
  assert.deepEqual(ids(6014), ['later', 'first'], 'source anchor alone cannot reveal a relocated plate')
  assert.deepEqual(ids(6136), ['later', 'first', 'relocated'])
  assert.deepEqual(ids(500), ['first'], 'moving backward uses current location, never high-water history')
  for (const boundary of [NaN, Infinity, -1, 0.5]) assert.deepEqual(ids(boundary), [])
  assert.equal(plates.length, 4, 'filtering never mutates the production array')

  const shared = [
    { id: 'early', image_asset_id: 'lamp', title: '窗边的灯', description: '' },
    { id: 'late', image_asset_id: 'lamp', title: '她已归来', description: '窗边的灯终于熄灭。' },
  ]
  const opening = openImageVisit('lamp', 100, false, 'early')
  assert.equal(placedImage(opening, shared), shared[0])
  let later = requestImage(opening, 'lamp', 200, 'late')
  assert.equal(later.pendingPlate, 'late', 'the same pixel bytes do not disclose a later caption')
  assert.equal(placedImage(later, shared), shared[0], 'pending lightbox still belongs to the earlier placement')
  assert.equal(placedImage(cancelImageDisclosure(later), shared), shared[0])
  later = confirmImageDisclosure(later)
  assert.equal(placedImage(later, shared), shared[1], 'after consent use the clicked placement, not first matching image')
  assert.equal(placedImage(openImageVisit('lamp', 100), shared), undefined, 'stage-only art never borrows plate copy')
  assert.equal(placedImage(openImageVisit('different-art', 100, false, 'early'), shared), undefined)
  assert.equal(placedImage(requestImage(later, 'lamp', 99, 'early'), shared), shared[0])

  const restored = restoreImageVisit('lamp', 'late', true, 100, 200)
  assert.equal(restored.asset, null, 'history cannot silently restore whole-gallery pixels')
  assert.equal(placedImage(restored, shared), undefined)
  assert.equal(restored.pendingPlate, 'late')
  assert.equal(placedImage(confirmImageDisclosure(restored), shared), shared[1])
  assert.equal(restoreImageVisit('lamp', 'late', true, 200, 200).plate, 'late', 'reached target can reopen')
  // Render only the safe subtree before an intentional whole-gallery reveal.
  // No DOM, history, storage or network is needed for this focused model check.
  function button(tree, label) {
    if (!tree || typeof tree !== 'object') return null
    if (tree.type === 'button' && tree.props.children === label) return tree
    for (const child of React.Children.toArray(tree.props?.children)) {
      const match = button(child, label)
      if (match) return match
    }
    return null
  }
  function mountGallery(totalCount, reachedCount = 1) {
    let revealed = false, tree
    const original = React.useState
    const props = {
      totalCount, reachedCount,
      onCancel: () => calls.push('cancel-gallery'),
      children: whole => {
        calls.push(whole ? 'render-whole' : 'render-reached')
        return React.createElement('div', { className: 'reader-gallery' },
          (whole || reachedCount > 0) && React.createElement('img', { src: '/reached.svg', alt: 'reached-description' }),
          whole && React.createElement('div', {},
            React.createElement('img', { src: '/future-fire.svg', alt: 'future-description' }),
            React.createElement('button', { 'aria-label': '重试后文火船' }, '后文火船')))
      },
    }
    function render() {
      React.useState = () => [revealed, (value) => { revealed = value }]
      try { tree = ReaderGalleryDisclosure(props) } finally { React.useState = original }
    }
    render()
    return {
      html: () => renderToStaticMarkup(tree),
      cancel: () => { button(tree, '返回').props.onClick(); render() },
      confirm: () => { button(tree, '查看全章画卷（含后文）').props.onClick(); render() },
    }
  }
  calls.length = 0
  const gallery = mountGallery(2)
  for (const label of ['读到这里的画面', '1 幅', '全章画卷含后文画面与标题', '尚未读到的场景', '返回', '查看全章画卷（含后文）']) {
    assert.ok(gallery.html().includes(label))
  }
  assert.ok(gallery.html().includes('/reached.svg'), 'reached images are available immediately')
  assert.ok(!/后文火船|future-fire|future-description|<dialog/.test(gallery.html()))
  assert.deepEqual(calls, ['render-reached'], 'only the bounded callback runs at entry')
  gallery.cancel()
  assert.deepEqual(calls, ['render-reached', 'cancel-gallery', 'render-reached'])
  assert.ok(!gallery.html().includes('future-fire'), 'return never reveals or preloads future thumbnails')
  gallery.confirm()
  assert.ok(gallery.html().includes('后文火船'))
  assert.ok(gallery.html().includes('future-fire'), 'deliberate confirmation retains the whole gallery')
  assert.deepEqual(calls, ['render-reached', 'cancel-gallery', 'render-reached', 'render-whole'])
  assert.ok(!mountGallery(2).html().includes('后文火船'), 'reentry and Back/Forward start protected')
  assert.ok(!mountGallery(1).html().includes('全章画卷含后文'), 'no spoiler warning when every picture is reached')
  const empty = mountGallery(2, 0).html()
  assert.ok(empty.includes('当前位置还没有可回看的插图'))
  assert.ok(!empty.includes('<img'), 'zero reached images creates no media subtree')
  assert.equal(JSON.stringify(record), before, 'gallery permission changes no progress, preferences or marks')
  console.log('Image disclosure: repeated Next, reached/display boundaries, one visit-only confirmation, cancel/reopen, per-plate current-position gallery filtering, immediate safe subtree, zero-state, generic story protection, history permission expiry and no pre-reveal future subtree passed.')

} finally {
  fs.rmSync(temp, { force: true, recursive: true })
}
