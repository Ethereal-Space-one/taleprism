const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')

const root = path.resolve(__dirname, '../..')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'tale-reader-disclosure-'))
try {
  const compile = spawnSync(
    path.join(root, 'frontend/node_modules/.bin/tsc'),
    [
      '--module', 'commonjs', '--target', 'ES2022', '--strict', '--skipLibCheck',
      '--jsx', 'react-jsx', '--outDir', temp,
      path.join(root, 'frontend/src/reader/ReaderContents.tsx'),
      path.join(root, 'frontend/src/ReaderMap.tsx'),
      path.join(root, 'frontend/src/reader/storyGraph.ts'),
    ],
    { encoding: 'utf8' },
  )
  assert.equal(compile.status, 0, compile.stdout + compile.stderr)
  fs.symlinkSync(path.join(root, 'frontend/node_modules'), path.join(temp, 'node_modules'), 'dir')
  const React = require(path.join(temp, 'node_modules/react'))
  const { renderToStaticMarkup } = require(path.join(temp, 'node_modules/react-dom/server'))
  const { directoryEntries, mapAtPosition } = require(path.join(temp, 'reader/disclosure.js'))
  const { chibiMapDisclosure } = require(path.join(temp, 'reader/graphs/chibiMap.js'))
  const { ReaderContents } = require(path.join(temp, 'reader/ReaderContents.js'))
  const { ReaderMap } = require(path.join(temp, 'ReaderMap.js'))
  const { resolveStoryGraph } = require(path.join(temp, 'reader/storyGraph.js'))
  const raw = fs.readFileSync(path.join(root, 'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'))
  const text = raw.toString('utf8')
  const byteAt = (quote) => {
    assert.ok(text.includes(quote), `missing fixture anchor: ${quote}`)
    return Buffer.byteLength(text.slice(0, text.indexOf(quote)))
  }
  const blocks = Array.from(text.matchAll(/[^\r\n]+/g), (match, index) => {
    const byte_start = Buffer.byteLength(text.slice(0, match.index))
    return {
      id: `block-${index}`, text: match[0], byte_start,
      byte_end: byte_start + Buffer.byteLength(match[0]), heading: /^第.+回/.test(match[0]),
    }
  })
  const sceneSpecs = [
    ['', '帐中问疾'], ['孔明辭別出帳', '南屏山·祭风'], ['黃蓋用刀一招', '火起江面'],
    ['縱馬加鞭', '山林败走'], ['卻說關雲長放了曹操', '夏口复命'],
  ]
  const data = {
    project: { canonical_sha256: require('node:crypto').createHash('sha256').update(raw).digest('hex') },
    blocks,
    config: {
      map_profile: 'chibi',
      scenes: sceneSpecs.map(([quote, title], index) => ({
        id: `scene-${index}`, title, start_byte: byteAt(quote),
      })),
    },
  }
  const protectFuture = !!resolveStoryGraph(data)
  assert.equal(protectFuture, true)
  const chapter = blocks.filter((block) => block.heading)[1]
  const initial = directoryEntries(data, 0, protectFuture)
  assert.equal(initial.chapters[1].title, '第五十回 · 后文标题暂隐')
  assert.equal(initial.chapters[1].byte, chapter.byte_start, 'neutral labels retain jump anchors')
  assert.equal(initial.chapters[0].title, blocks[0].text, 'reached title is verbatim')
  assert.deepEqual(initial.scenes.slice(1).map((scene) => scene.title), [
    '场景 2 · 后文标题暂隐', '场景 3 · 后文标题暂隐', '场景 4 · 后文标题暂隐', '场景 5 · 后文标题暂隐',
  ])
  assert.equal(directoryEntries(data, chapter.byte_start - 1, true).chapters[1].title, initial.chapters[1].title)
  assert.equal(directoryEntries(data, chapter.byte_start, true).chapters[1].title, chapter.text)
  assert.equal(directoryEntries(data, 0, true, true).chapters[1].title, chapter.text)
  assert.equal(directoryEntries(data, 0, true).chapters[1].title, initial.chapters[1].title, 'moving back re-hides titles')
  const custom = { ...data, project: { canonical_sha256: 'not-the-curated-edition' } }
  assert.equal(resolveStoryGraph(custom), null)
  assert.equal(directoryEntries(custom, 0, !!resolveStoryGraph(custom)).chapters[1].title, chapter.text)
  const fallback = { ...data, blocks: [{ ...chapter, text: '自定标题' }] }
  assert.equal(directoryEntries(fallback, 0, true).chapters[0].title, '章节 1 · 后文标题暂隐')

  const originalMap = JSON.parse(fs.readFileSync(path.join(root, 'samples/reader/chibi-map.json'), 'utf8'))
  const ids = ['opposition', 'fire', 'retreat']
  const map = {
    ...originalMap,
    phases: originalMap.phases.map((phase, index) => ({ ...phase, id: ids[index] })),
    phase_anchors: [0, byteAt('黃蓋用刀一招'), blocks.find((block) => block.text.includes('縱馬加鞭')).byte_start],
  }
  const snapshot = JSON.stringify({ data, map })
  const fire = map.phase_anchors[1], retreat = map.phase_anchors[2]
  assert.deepEqual(mapAtPosition(map, 0, chibiMapDisclosure).phases.map((phase) => phase.revealed), [true, false, false])
  assert.equal(mapAtPosition(map, fire - 1, chibiMapDisclosure).phases[1].revealed, false)
  assert.equal(mapAtPosition(map, fire, chibiMapDisclosure).phases[1].title, map.phases[1].title)
  assert.equal(mapAtPosition(map, retreat, chibiMapDisclosure).phases[2].description, map.phases[2].description)
  assert.equal(mapAtPosition(map, 0, chibiMapDisclosure, true).phases[2].description, map.phases[2].description)
  assert.deepEqual(mapAtPosition(map, 0, chibiMapDisclosure).phases.map((phase) => phase.revealed), [true, false, false])
  assert.equal(mapAtPosition(map, 0, null).phases[2].title, map.phases[2].title, 'unsupported works are unchanged')
  for (const invalid of [NaN, Infinity, -1]) {
    assert.ok(mapAtPosition(map, invalid, chibiMapDisclosure).phases.every((phase) => !phase.revealed))
  }

  // A small synchronous hook harness exercises local-only disclosure buttons.
  // No DOM/history/storage is provided: revealing must never navigate or persist.
  function mount(Component, props) {
    const state = []
    let tree
    function render() {
      const original = React.useState
      let cursor = 0
      React.useState = (initial) => {
        const index = cursor++
        if (!(index in state)) state[index] = typeof initial === 'function' ? initial() : initial
        return [state[index], (next) => {
          state[index] = typeof next === 'function' ? next(state[index]) : next
        }]
      }
      try { tree = Component(props) } finally { React.useState = original }
      return tree
    }
    render()
    return { render, get tree() { return tree }, html: () => renderToStaticMarkup(tree) }
  }
  function content(node) {
    if (Array.isArray(node)) return node.map(content).join('')
    if (!node || typeof node === 'boolean') return ''
    return typeof node === 'object' ? content(node.props.children) : String(node)
  }
  function find(node, predicate) {
    if (Array.isArray(node)) return node.flatMap((item) => find(item, predicate))
    if (!node || typeof node !== 'object') return []
    return [...(predicate(node) ? [node] : []), ...find(node.props.children, predicate)]
  }
  const button = (view, label) => {
    const found = find(view.tree, (node) => node.type === 'button' && content(node).includes(label))
    assert.equal(found.length, 1, `one button must match ${label}`)
    return found[0]
  }
  const click = (view, label) => { button(view, label).props.onClick(); view.render() }
  const visits = []
  const contents = mount(ReaderContents, {
    data, at: 0, protectFuture: true, sceneId: 'scene-0',
    onVisit: (byte) => visits.push(byte), onVoices: () => {},
  })
  assert.ok(!contents.html().includes('關雲長義釋曹操'))
  assert.ok(!contents.html().includes('山林败走'))
  assert.ok(contents.html().includes('aria-current="location"'))
  click(contents, '查看完整目录')
  assert.ok(contents.html().includes(chapter.text))
  assert.ok(contents.html().includes('山林败走'))
  assert.deepEqual(visits, [], 'revealing changes no reading position')
  click(contents, '按当前阅读位置显示')
  assert.ok(!contents.html().includes('關雲長義釋曹操'))
  click(contents, '第五十回')
  assert.deepEqual(visits, [chapter.byte_start], 'neutral chapter remains an intentional jump')
  click(contents, '场景 4')
  assert.equal(visits[1], data.config.scenes[3].start_byte)
  const reopenedContents = mount(ReaderContents, {
    data, at: 0, protectFuture: true, onVisit: () => {}, onVoices: () => {},
  })
  assert.ok(!reopenedContents.html().includes('關雲長義釋曹操'), 'new panel defaults to protected titles')

  global.window = { innerWidth: 800 }
  const mapProps = { data: map, at: 0, protectFuture: true }
  const mapView = mount(ReaderMap, mapProps)
  assert.ok(!mapView.html().includes('火攻'), 'no future title, tooltip, route, source note or SVG label')
  assert.ok(!mapView.html().includes('战后撤军'))
  click(mapView, '阶段 2')
  assert.ok(!mapView.html().includes('火攻方向'))
  assert.ok(!mapView.html().includes('map-route map-fire'))
  click(mapView, '江陵')
  assert.ok(mapView.html().includes('今湖北荆州一带'), 'geography remains usable')
  assert.ok(!mapView.html().includes('战后的退军叙事'))
  click(mapView, '查看完整战役')
  assert.ok(mapView.html().includes('火攻推进'))
  assert.ok(mapView.html().includes('map-route map-fire'))
  assert.ok(mapView.html().includes('战后的退军叙事'))
  assert.ok(mapView.html().includes(originalMap.sources[2].title), 'source attribution is retained')
  click(mapView, '战后撤军')
  assert.ok(mapView.html().includes('map-route map-retreat'))
  click(mapView, '按当前阅读位置显示')
  assert.ok(!mapView.html().includes('火攻'))
  assert.ok(!mapView.html().includes('map-route map-retreat'))
  assert.ok(mapView.html().includes('map-route map-march'), 'return to current phase after hiding full battle')
  mapProps.at = retreat
  mapView.render()
  assert.ok(mapView.html().includes('战后撤军'))
  mapProps.at = 0
  mapView.render()
  assert.ok(!mapView.html().includes('战后撤军'), 'back navigation uses current, not furthest position')
  const futureEntry = mount(ReaderMap, {
    ...mapProps, entry: { phase_id: 'retreat', place_ids: ['jiangling'] },
  })
  assert.ok(!futureEntry.html().includes('map-route map-retreat'), 'context entry cannot bypass disclosure')
  assert.ok(!futureEntry.html().includes('战后的退军叙事'))
  const laterMap = mount(ReaderMap, { ...mapProps, at: retreat })
  assert.ok(laterMap.html().includes('map-route map-retreat'), 'reached later stage opens normally')
  click(laterMap, '查看完整战役')
  const reopenedMap = mount(ReaderMap, mapProps)
  assert.ok(!reopenedMap.html().includes('火攻'), 'full-battle reveal is not persistent')
  assert.equal(JSON.stringify({ data, map }), snapshot, 'source, scene and public map data are never mutated')
  delete global.window
  console.log('Reader disclosure: edition-bound neutral directory jumps, exact boundaries, reversible full views, hidden map tooltips/routes/notes, current-position rollback and unchanged source data passed.')
} finally {
  fs.rmSync(temp, { force: true, recursive: true })
}
