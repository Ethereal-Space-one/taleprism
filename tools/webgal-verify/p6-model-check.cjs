const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const root = path.resolve(__dirname, '../..'),
  temp = fs.mkdtempSync(path.join(os.tmpdir(), 'storygal-p6-model-'))
try {
  const compile = spawnSync(
    path.join(root, 'frontend/node_modules/.bin/tsc'),
    [
      '--module',
      'commonjs',
      '--target',
      'ES2022',
      '--skipLibCheck',
      '--outDir',
      temp,
      path.join(root, 'frontend/src/reader/model.ts'),
      path.join(root, 'frontend/src/studio/soundscape.ts'),
    ],
    { encoding: 'utf8' },
  )
  assert.equal(compile.status, 0, compile.stdout + compile.stderr)
  const m = require(path.join(temp, 'reader/model.js'))
  const A = { byte: 3, offset: 0.2 },
    B = { byte: 8, offset: 0 },
    C = { byte: 14, offset: -0.2 }
  let s = { view: A, resume: A, furthest: 3, visits: [] }
  s = m.navigationReducer(s, { type: 'visit', position: B })
  s = m.navigationReducer(s, { type: 'visit', position: C })
  s = m.navigationReducer(s, { type: 'scroll', position: { byte: 16, offset: 0 } })
  assert.deepEqual(s.resume, A)
  assert.equal(s.visits.length, 2)
  s = m.navigationReducer(s, { type: 'restore', position: B, visits: [A] })
  assert.deepEqual(s.resume, A)
  s = m.navigationReducer(s, { type: 'continue' })
  assert.deepEqual(s.resume, B)
  assert.equal(s.visits.length, 0)
  s = m.navigationReducer(s, { type: 'scroll', position: A })
  assert.deepEqual(s.resume, A)
  assert.equal(s.furthest, 8)
  const block = {
    id: 'p',
    byte_start: 3,
    byte_end: 18,
    text: '甲😀乙<script>',
    runs: [{ text: '甲😀乙<script>', speaker_id: null, take_id: null }],
    audio: [],
    heading: false,
  }
  block.byte_end = 3 + m.byteLength(block.text)
  const data = {
    schema_version: 1,
    blocks: [block],
    config: { scenes: [] },
    characters: {},
    map: null,
  }
  const migrated = m.readRecord(data, JSON.stringify({ at: 10, size: 25, leading: 2 }))
  assert.equal(migrated.version, 2)
  assert.equal(migrated.resume.byte, 10)
  assert.equal(migrated.preferences.size, 25)
  assert.equal(m.readRecord(data, '{broken').resume.byte, 3)
  assert.equal(m.validPosition(data, { byte: 8 }).byte, 6)
  assert.equal(m.byteLength('😀'), 4)
  assert.equal(m.search(data, '😀')[0].byte, 6)
  assert.deepEqual(m.search(data, 'absent'), [])
  assert.equal(m.normalizeContent(data).blocks[0].runs[0].byte_end, block.byte_end)
  // A UTF-16 crop can land inside a supplementary character on BOTH edges.
  // The preview is evidence: it must be a literal substring of the source.
  const text = '😀' + 'a'.repeat(11) + '点' + 'b'.repeat(63) + '𠮷' + '尾'
  const start = 100
  const clip = { ...data, blocks: [{ ...block, text, byte_start: start, byte_end: start + Buffer.byteLength(text) }] }
  const target = start + Buffer.byteLength('😀' + 'a'.repeat(11))
  assert.equal(m.quoteAt(clip, target), text.slice(0, -1))
  assert.equal(m.quoteAt(clip, target + 2), m.quoteAt(clip, target), 'continuation bytes do not advance the quote')
  assert.equal(m.quoteAt(clip, clip.blocks[0].byte_end), m.quoteAt(clip, start), 'out-of-block positions agree with record recovery')
  for (const limit of [45, 70]) {
    const prefix = '甲'.repeat(limit - 1)
    assert.equal(m.sourceQuote(prefix + '𠮷乙', 0, 0, limit), prefix + '𠮷', 'arrangement preview')
  }
  const mixed = '\ufeffaé中e\u0301👩🏽‍🚀𠮷'
  let byte = 0, units = 0
  for (const char of mixed) {
    for (let b = 0; b < Buffer.byteLength(char); b++)
      assert.deepEqual(m.textPointAtByte(mixed, byte + b), { byte, index: units })
    for (let u = 0; u < char.length; u++) assert.equal(m.anchorByteAtCaret(mixed, units + u), byte)
    assert.equal(m.sourceQuote(mixed, byte, 0, char.length), char)
    byte += Buffer.byteLength(char)
    units += char.length
  }
  assert.equal(m.anchorByteAtCaret(mixed, mixed.length), byte - Buffer.byteLength('𠮷'), 'end caret stays inside visible source')
  const oldMark = { id: 'old', text: '\ud83d', position: { byte: target, offset: 0 } }
  const healed = m.readRecord(clip, JSON.stringify({ version: 2, marks: [oldMark] })).marks[0]
  assert.deepEqual(healed, { ...oldMark, text: m.quoteAt(clip, target) }, 'repair the old generated label, not its identity or address')
  const largeMark = 'x'.repeat(2999) + '😀'
  const loaded = m.readRecord(data, JSON.stringify({ marks: [{ id: 'big', text: largeMark }] }))
  assert.equal(loaded.marks[0].text, 'x'.repeat(2999), 'strict local storage cap never splits the last scalar')
  const { occurrences, selectedSoundEvidence } = require(path.join(temp, 'studio/soundscape.js'))
  const repeated = '😀𠮷、😀𠮷。'
  assert.deepEqual(occurrences(repeated, '😀𠮷'), [0, 5])
  assert.deepEqual(occurrences('甲甲甲', '甲甲'), [0, 1], 'keep overlapping manual choices')
  assert.deepEqual(occurrences(repeated, '\ud83d'), [], 'reject pasted half-emoji')
  const selected = selectedSoundEvidence(repeated, 6, 8)
  assert.deepEqual(selected, { text: '😀𠮷', occurrence: 2 }, 'both edges snap out and keep the second occurrence')
  const chosenStart = occurrences(repeated, selected.text)[selected.occurrence - 1]
  const chosenByte = m.byteLength(repeated.slice(0, chosenStart))
  assert.equal(chosenByte, 11)
  assert.equal(Buffer.from(repeated).subarray(chosenByte, chosenByte + m.byteLength(selected.text)).toString('utf8'), selected.text)
  assert.equal(selectedSoundEvidence(repeated, 6, 6), null, 'collapsed carets cannot become evidence')
  assert.equal(selectedSoundEvidence('😀'.repeat(301), 1, 601), null, 'enforce the cap after snapping')
  console.log(
    'P6 state transitions, old-record migration, Unicode byte/caret round trips, whole-scalar previews, sound evidence and literal search passed.',
  )
} finally {
  fs.rmSync(temp, { recursive: true, force: true })
}
