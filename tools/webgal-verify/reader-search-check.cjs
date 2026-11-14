const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
const root = path.resolve(__dirname, '../..')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'reader-search-check-'))
const frontend = path.join(root, 'frontend')

async function main() {
  require(path.join(frontend, 'node_modules/esbuild')).buildSync({
    entryPoints: ['search', 'model'].map((name) => path.join(frontend, `src/reader/${name}.ts`)),
    outdir: temp, bundle: true, platform: 'node', format: 'cjs', logLevel: 'silent',
  })
  const m = require(path.join(temp, 'model.js'))
  const { createSearchMatcher } = require(path.join(temp, 'search.js'))
  const match = createSearchMatcher()
  const exact = m.literalMatches
  const block = (text, start = 0, runs = [text]) => {
    let at = start
    return { id: `p${start}`, text, byte_start: start, byte_end: start + m.byteLength(text),
      heading: false, audio: [], runs: runs.map((text, i) => {
        const byte_start = at
        at += m.byteLength(text)
        return { text, byte_start, byte_end: at, speaker_id: `speaker${i}`, take_id: `take${i}` }
      }) }
  }
  const data = (...texts) => {
    let at = 0
    return { blocks: texts.map((text) => { const b = block(text, at); at = b.byte_end; return b }) }
  }
  const search = (data, query, matcher = match) => m.search(data, query, matcher)
  const oldSearch = (data, query) => !query ? [] : data.blocks.flatMap((b) => {
    const results = []
    let index = b.text.indexOf(query)
    while (index >= 0 && results.length < 300) {
      results.push({ byte: b.byte_start + m.byteLength(b.text.slice(0, index)),
        text: b.text.slice(Math.max(0, index - 12), index + query.length + 35) })
      index = b.text.indexOf(query, index + Math.max(1, query.length))
    }
    return results
  }).slice(0, 300)
  const raw = fs.readFileSync(path.join(root, 'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'))
  const text = raw.toString('utf8')
  const chibi = { blocks: Array.from(text.matchAll(/[^\r\n]+/g), (v) =>
    block(v[0], Buffer.byteLength(text.slice(0, v.index)))) }
  assert.equal(oldSearch(chibi, '诸葛亮').length, 0, 'original bug: source edition is Traditional')
  assert.equal(oldSearch(chibi, '諸葛亮').length, 9)
  const simplified = search(chibi, '诸葛亮'), traditional = search(chibi, '諸葛亮')
  assert.equal(simplified.length, 9)
  assert.deepEqual(simplified, traditional)
  for (const r of simplified) {
    assert.equal(raw.subarray(r.byte, r.byte + 9).toString('utf8'), '諸葛亮')
    assert.ok(r.text.includes('諸葛亮') && !r.text.includes('诸葛亮'))
  }
  for (const query of ['', '诸葛亮', '諸葛亮', '曰：「', '孔明', '曹操', '。', '不存在', ' '])
    assert.deepEqual(search(chibi, query, exact), oldSearch(chibi, query), `exact regression: ${query}`)
  assert.equal(search(data('诸葛亮'), '諸葛亮').length, 1, 'both query directions work on custom Chinese')
  assert.equal(search(data('諸葛亮'), '诸葛亮', exact).length, 0)
  assert.equal(search(data('諸葛亮'), '諸葛亮', exact).length, 1)
  const punctuation = data('諸葛亮曰：「甲，乙。」 AbC café e\u0301 Ａ ①')
  assert.equal(search(punctuation, '诸葛亮曰：「甲，乙。」').length, 1)
  for (const query of ['诸葛亮曰：“甲，乙。”', '甲乙', '甲,乙', '甲， 乙', 'abc', 'cafe', 'é Ａ', 'A 1'])
    assert.equal(search(punctuation, query).length, 0, `do not normalize non-Han: ${query}`)
  assert.equal(search(data('滑鼠 計程車'), '鼠标').length, 0, 'no regional vocabulary rewrite')
  assert.equal(search(data('諸', '葛亮'), '诸葛亮').length, 0, 'no joining separate paragraphs')
  for (const query of ['发', '發', '髮']) {
    assert.equal(search(data('發髮发'), query).length, 3, 'many-to-one ambiguity is explicit')
    assert.equal(search(data('發髮发'), query, exact).length, 1, 'exact mode distinguishes every form')
  }
  assert.equal(search(data('乾坤乾燥'), '干坤').length, 0, 'phrase dictionary preserves 乾坤')
  assert.equal(search(data('乾坤乾燥'), '干燥').length, 1)
  assert.equal(search(data('乾坤乾燥'), '乾').length, 2, 'literal partial matches are never lost')
  assert.equal(search(data('發發發發'), '发发').length, 2, 'non-overlap and deterministic ordering')
  assert.equal(search(data('諸'.repeat(310)), '诸').length, 300)
  assert.equal(search(data(...Array(310).fill('諸')), '诸').length, 300, 'global result cap')
  assert.deepEqual(search(data('😀'), '\ud83d', exact), [], 'never split surrogate pairs')
  const parts = ['😀e\u0301⼀神丽諸', '葛亮/諸', '葛亮']
  const unicode = block(parts.join(''), 17, parts)
  const unicodeData = { blocks: [unicode] }
  const hits = search(unicodeData, '诸葛亮')
  assert.equal(hits.length, 2)
  const encoded = Buffer.from(unicode.text)
  for (const hit of hits)
    assert.equal(encoded.subarray(hit.byte - 17, hit.byte - 17 + 9).toString('utf8'), '諸葛亮')
  assert.equal(search(unicodeData, '神丽诸葛亮').length, 1, 'astral→BMP folded offsets remain original')
  assert.equal(search(unicodeData, '⼀').length, 1, 'non-Han compatibility radical remains literal')
  assert.equal(search(unicodeData, '一').length, 0)
  for (const matcher of [match, exact]) {
    const runs = m.highlightedRuns(unicode, matcher === match ? '诸葛亮' : '諸葛亮', matcher)
    assert.equal(runs.map((r) => r.text).join(''), unicode.text)
    assert.equal(runs.filter((r) => r.match).map((r) => r.text).join(''), '諸葛亮諸葛亮')
    for (const r of runs) {
      assert.equal(encoded.subarray(r.byte_start - 17, r.byte_end - 17).toString('utf8'), r.text)
      assert.equal(r.speaker_id, `speaker${r.take_id.slice(4)}`, 'metadata survives splitting')
    }
  }
  const snippets = search(data('😀'.repeat(30) + '諸葛亮' + '😀'.repeat(30)), '诸葛亮')
  assert.ok(snippets.every((r) => r.text.isWellFormed()), 'context snippets never clip a surrogate')
  // Exhaustively guard the only mapping assumption. Pin upgrades must pass this,
  // in addition to the runtime count-change fallback in search.ts.
  const { configs } = await import(pathToFileURL(path.join(frontend,
    'node_modules/opencc-js/dist/esm-lib/preset/t2cn.js')))
  let entries = 0
  for (const group of [...configs.t2s.normalizationChain, ...configs.t2s.conversionChain])
    for (const dictionary of group)
      for (const line of dictionary.split('|')) {
        const [from, to] = line.split(' ')
        assert.equal([...from].length, [...to].length, `scalar count changed: ${from} → ${to}`)
        entries++
      }
  assert.equal(entries, 4991)
  console.log('Reader search: Chibi 0→9, exact legacy behavior, literal punctuation/non-Han, ambiguity, Unicode UTF-8 anchors and cross-run highlights passed; audited 4,991 t2s mappings.')
}
main().finally(() => fs.rmSync(temp, { force: true, recursive: true })).catch((e) => { console.error(e); process.exitCode = 1 })
