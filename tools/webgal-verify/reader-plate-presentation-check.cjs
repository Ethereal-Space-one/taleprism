const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')

const root = path.resolve(__dirname, '../..')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'tale-plate-presentation-'))
try {
  const compile = spawnSync(
    path.join(root, 'frontend/node_modules/.bin/tsc'),
    [
      '--module', 'commonjs', '--target', 'ES2022', '--jsx', 'react-jsx',
      '--strict', '--skipLibCheck', '--outDir', temp,
      ...['platePresentation.ts', 'model.ts', 'ReaderPlate.tsx'].map((name) =>
        path.join(root, 'frontend/src/reader', name),
      ),
    ],
    { encoding: 'utf8' },
  )
  assert.equal(compile.status, 0, compile.stdout + compile.stderr)
  fs.symlinkSync(path.join(root, 'frontend/node_modules'), path.join(temp, 'node_modules'), 'dir')
  const { resolvePlatePresentations } = require(path.join(temp, 'reader/platePresentation.js'))
  const { readRecord, validPosition, search } = require(path.join(temp, 'reader/model.js'))
  const { ReaderPlate } = require(path.join(temp, 'reader/ReaderPlate.js'))
  const React = require(path.join(root, 'frontend/node_modules/react'))
  const { renderToStaticMarkup } = require(path.join(root, 'frontend/node_modules/react-dom/server'))
  const raw = fs.readFileSync(path.join(root, 'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'))
  const text = raw.toString('utf8')
  const rebuild = JSON.parse(fs.readFileSync(path.join(root, 'examples/chibi/rebuild-v0.2.0.json')))
  const review = JSON.parse(fs.readFileSync(path.join(root, 'examples/chibi/visual-review-v0.2.0.json')))
  const fixture = {
    project: { id: 'public-fixture', canonical_sha256: crypto.createHash('sha256').update(raw).digest('hex') },
    blocks: Array.from(text.matchAll(/[^\r\n]+/g), (m, i) => {
      // ReaderContent omits indentation from blocks, not from canonical bytes.
      const blockText = m[0].trim()
      const byte_start = Buffer.byteLength(text.slice(0, m.index + m[0].indexOf(blockText)))
      const byte_end = byte_start + Buffer.byteLength(blockText)
      return {
        id: `b${i}`, text: blockText, byte_start, byte_end, heading: i === 0, audio: [],
        runs: [{ text: blockText, byte_start, byte_end, speaker_id: null, take_id: null }],
      }
    }),
    config: {
      scenes: [],
      illustrations: rebuild.plan.shots.map((s) => ({
        id: s.id, title: s.title, after_byte: s.after_byte,
        image_asset_id: s.image_asset_id, description: s.moment,
      })),
    },
    media: Object.fromEntries(review.images.map((i) => [i.asset_id, {
      id: i.asset_id, type: 'image', sha256: i.sha256, url: `./media/${i.asset_id}.png`,
    }])),
  }
  const before = JSON.stringify(fixture)
  function freeze(value) {
    if (value && typeof value === 'object') {
      Object.values(value).forEach(freeze)
      Object.freeze(value)
    }
    return value
  }
  freeze(fixture)
  const model = resolvePlatePresentations(fixture)
  const plates = fixture.config.illustrations
  const wind = plates.find((p) => p.id === 'wind-in-tent')
  const fire = plates.find((p) => p.id === 'fire-panorama')
  assert.equal(model.size, 12)
  assert.equal(model.get(wind.id).displayAfterByte, 6136)
  assert.equal(model.get(fire.id).displayAfterByte, 16035)
  assert.equal(model.get(wind.id).disclosureByte, 6136)
  assert.equal(model.get(fire.id).disclosureByte, 16035)
  assert.equal(model.get(wind.id).sourceByte, 6011)
  assert.equal(model.get(fire.id).sourceByte, 15971)
  assert.deepEqual(
    plates.filter((p) => model.get(p.id).displayAfterByte !== p.after_byte).map((p) => p.id),
    [wind.id, fire.id],
    'the other ten positions must remain untouched',
  )
  for (const plate of plates) {
    assert.ok(model.get(plate.id).visualDescription?.length > 35)
    assert.notEqual(model.get(plate.id).visualDescription, plate.description)
    assert.ok(model.get(plate.id).disclosureByte >= plate.after_byte)
  }
  const order = fixture.blocks.flatMap((b) => [
    b.text,
    ...plates.filter((p) => model.get(p.id).displayAfterByte === b.byte_end).map((p) => p.id),
  ])
  assert.equal(order[order.indexOf(wind.id) - 1], '不是孔明施妙計，周郎安得逞才能？')
  assert.equal(order[order.indexOf(fire.id) - 1], '火厄盛時遭水厄，棒瘡愈後患金瘡。')
  assert.equal(order[order.indexOf(fire.id) + 1], '未知黃蓋性命如何，且看下文分解。')

  const copy = () => JSON.parse(before)
  function expectOriginal(data, id = wind.id, description = null) {
    const p = data.config.illustrations.find((item) => item.id === id)
    const actual = resolvePlatePresentations(data).get(id)
    assert.equal(actual.displayAfterByte, p.after_byte)
    assert.equal(actual.disclosureByte, p.after_byte)
    if (description === null) assert.equal(actual.visualDescription, null)
  }
  const otherEdition = copy()
  otherEdition.project.canonical_sha256 = 'another-edition'
  for (const p of plates) expectOriginal(otherEdition, p.id)
  const renamed = copy()
  renamed.config.illustrations.find((p) => p.id === wind.id).id = 'same-title-other-plate'
  expectOriginal(renamed, 'same-title-other-plate')
  const editedAnchor = copy()
  editedAnchor.config.illustrations.find((p) => p.id === wind.id).after_byte = 6136
  expectOriginal(editedAnchor)
  const replacedImage = copy()
  replacedImage.media[wind.image_asset_id].sha256 = 'changed-image'
  expectOriginal(replacedImage)
  const replacedAsset = copy()
  replacedAsset.config.illustrations.find((p) => p.id === wind.id).image_asset_id = fire.image_asset_id
  expectOriginal(replacedAsset)
  const missingEvidence = copy()
  const windParagraph = missingEvidence.blocks.find((b) => b.byte_end === wind.after_byte)
  windParagraph.text = windParagraph.text.replace('忽聽風聲響，旗旛轉動。', '甲'.repeat(12))
  expectOriginal(missingEvidence)
  const duplicateEvidence = copy()
  duplicateEvidence.blocks.push({ ...duplicateEvidence.blocks.find((b) => b.byte_end === wind.after_byte), byte_start: 99999, byte_end: 100830 })
  expectOriginal(duplicateEvidence)
  const duplicateIdentity = copy()
  duplicateIdentity.config.illustrations.push({ ...wind })
  expectOriginal(duplicateIdentity)
  const changedParagraphBoundary = copy()
  changedParagraphBoundary.blocks.find((b) => b.byte_end === wind.after_byte).byte_start--
  expectOriginal(changedParagraphBoundary)
  for (const mutate of [
    (d) => { d.blocks.find((b) => b.byte_end === 6136).text = '甲'.repeat(16) },
    (d) => { d.blocks.find((b) => b.byte_end === 6136).byte_start-- },
    (d) => { const i = d.blocks.findIndex((b) => b.byte_end === 6075); [d.blocks[i], d.blocks[i + 1]] = [d.blocks[i + 1], d.blocks[i]] },
    (d) => { d.blocks.push({ ...d.blocks.find((b) => b.byte_end === 6136) }) },
    (d) => { d.blocks.find((b) => b.byte_end === 6014).text = d.blocks.find((b) => b.byte_end === 6014).text.replace('後人有詩曰：', '甲甲甲甲甲甲') },
  ]) {
    const changed = copy()
    mutate(changed)
    expectOriginal(changed, wind.id, 'visual-description-may-still-apply')
    assert.equal(resolvePlatePresentations(changed).get(fire.id).displayAfterByte, 16035,
      'one invalid display recipe must not affect an independent plate')
  }

  // Existing image records keep their logical byte, image identity and in-image
  // offset, while restoration can still locate the moved DOM figure by plate ID.
  const oldPosition = { byte: 6011, offset: 0, plate: wind.id, imageOffset: 0.62 }
  const oldRecord = {
    version: 2, resume: oldPosition, furthest: 6011,
    marks: [{ id: 'old-mark', position: oldPosition, text: '旧插图书签' }],
  }
  const saved = readRecord(fixture, JSON.stringify(oldRecord))
  assert.deepEqual(saved.resume, { ...oldPosition, imageAsset: wind.image_asset_id })
  assert.deepEqual(saved.marks[0].position, saved.resume)
  assert.equal(validPosition(fixture, { byte: 6088 }).byte, 6088)
  const hits = search(fixture, '不是孔明')
  assert.equal(hits[0].byte, 6088)
  assert.equal(raw.subarray(hits[0].byte, hits[0].byte + Buffer.byteLength('不是孔明')).toString('utf8'), '不是孔明')
  assert.equal(JSON.stringify(fixture), before, 'source, production anchors and narrative descriptions must not change')

  // Both focusable image-opening controls receive the observed description, not
  // merely a title. The same text is the image alt; hidden referenced text is
  // intentionally included by aria-describedby in the accessibility tree.
  const noop = () => {}
  const markup = renderToStaticMarkup(React.createElement(ReaderPlate, {
    plate: wind, asset: fixture.media[wind.image_asset_id],
    ...model.get(wind.id), onLoad: noop, onRetry: noop, onError: noop, onOpen: noop,
  }))
  const described = [...markup.matchAll(/aria-describedby="([^"]+)"/g)].map((m) => m[1])
  assert.equal(described.length, 2)
  assert.equal(described[0], described[1])
  assert.ok(markup.includes(`id="${described[0]}" hidden="">${model.get(wind.id).visualDescription}</span>`))
  assert.ok(markup.includes(`alt="${model.get(wind.id).visualDescription}"`))
  assert.ok(markup.includes('data-source-byte="6011"'))
  assert.ok(markup.includes('data-display-after-byte="6136"'))
  assert.ok(!markup.includes(wind.description), 'verified visual description must replace narrative-only alt')
  console.log('Plate presentation: two poem-safe display boundaries, exact edition/image/evidence binding, twelve observed descriptions, unchanged source/bookmarks/search, and described image controls passed.')
} finally {
  fs.rmSync(temp, { force: true, recursive: true })
}
