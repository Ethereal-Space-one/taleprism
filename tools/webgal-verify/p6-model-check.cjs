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
  console.log(
    'P6 state transitions, old-record migration, Unicode anchors and literal search passed.',
  )
} finally {
  fs.rmSync(temp, { recursive: true, force: true })
}
