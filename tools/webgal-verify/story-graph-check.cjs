const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')

const root = path.resolve(__dirname, '../..')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'tale-graph-check-'))
try {
  const compile = spawnSync(
    path.join(root, 'frontend/node_modules/.bin/tsc'),
    [
      '--module', 'commonjs', '--target', 'ES2022', '--strict', '--skipLibCheck', '--outDir', temp,
      path.join(root, 'frontend/src/reader/storyGraph.ts'),
    ],
    { encoding: 'utf8' },
  )
  assert.equal(compile.status, 0, compile.stdout + compile.stderr)
  const { resolveStoryGraph, sliceStoryGraph } = require(path.join(temp, 'reader/storyGraph.js'))
  const raw = fs.readFileSync(path.join(root, 'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'))
  const text = raw.toString('utf8')
  const fixture = {
    project: { canonical_sha256: crypto.createHash('sha256').update(raw).digest('hex') },
    blocks: Array.from(text.matchAll(/[^\r\n]+/g), (m) => {
      const start = Buffer.byteLength(text.slice(0, m.index))
      return { text: m[0], byte_start: start, byte_end: start + Buffer.byteLength(m[0]) }
    }),
  }
  const graph = resolveStoryGraph(fixture)
  assert.ok(graph, 'every curated quote must resolve uniquely on the pinned public edition')
  assert.deepEqual(graph.phases.map((x) => x.evidence.end), [4848, 15376, 25374])
  const cut = (at) => sliceStoryGraph(graph, at)
  const names = (v) => v.factions.flatMap((f) => f.members.map((m) => m.name))
  const ids = (v) => v.relations.map((r) => r.id)
  const chapterIds = (v) => v.threads.flatMap((t) => t.nodes.map((n) => n.id))
  assert.deepEqual(cut(0), { chapter: null, factions: [], relations: [], phases: [], threads: [] })
  assert.equal(cut(62).chapter, null)
  assert.equal(cut(63).chapter.label, '第四十九回')
  assert.deepEqual(cut(4847).phases, [])
  assert.deepEqual(cut(4848).phases.map((p) => p.id), ['prepare'])
  assert.ok(names(cut(4848)).includes('黄盖'))
  assert.ok(!names(cut(4848)).includes('诸葛亮'))
  assert.ok(ids(cut(4848)).includes('affiliation-unknown'))
  assert.ok(!ids(cut(9890)).includes('sides'))
  assert.ok(ids(cut(9891)).includes('sides'))
  assert.ok(!ids(cut(9891)).includes('affiliation-unknown'))
  assert.ok(ids(cut(13428)).includes('believed'))
  assert.ok(!ids(cut(13428)).includes('attack'))
  assert.ok(!chapterIds(cut(13428)).includes('cao-realizes'))
  assert.ok(!ids(cut(15376)).includes('believed'))
  assert.ok(ids(cut(15376)).includes('attack'))
  assert.ok(!ids(cut(15376)).includes('release'))
  assert.ok(!cut(15376).factions.find((f) => f.id === 'cao').members.some((m) => m.name === '黄盖'))
  assert.equal(cut(16145).chapter.label, '第四十九回')
  assert.equal(cut(16146).chapter.label, '第五十回')
  assert.deepEqual(chapterIds(cut(16146)), [])
  assert.ok(!ids(cut(25178)).includes('release'))
  assert.ok(ids(cut(25179)).includes('release'))
  assert.deepEqual(cut(25373).phases.map((x) => x.id), ['prepare', 'fire'])
  assert.deepEqual(cut(25374).phases.map((x) => x.id), ['prepare', 'fire', 'huarong'])
  assert.ok(!chapterIds(cut(25374)).includes('return'))
  assert.ok(chapterIds(cut(27872)).includes('return'))
  assert.ok(!ids(cut(4848)).includes('release'), 'moving back must hide outcomes again')

  function verifyEvidence(o, position) {
    if (!o || typeof o !== 'object') return
    if ('quote' in o) {
      assert.ok(o.end <= position)
      assert.equal(raw.subarray(o.start, o.end).toString('utf8'), o.quote)
    }
    for (const v of Object.values(o)) verifyEvidence(v, position)
  }
  for (const spot of [0, 4848, 8616, 13428, 15376, 16146, 25178, 25374, 27872]) {
    verifyEvidence(cut(spot), spot)
  }
  assert.equal(resolveStoryGraph({ ...fixture, project: { canonical_sha256: 'other' } }), null)
  assert.equal(resolveStoryGraph({ ...fixture, blocks: fixture.blocks.slice(0, -4) }), null)
  const duplicate = fixture.blocks.find((b) => b.text.includes('長歎一聲，並皆放去'))
  assert.equal(resolveStoryGraph({ ...fixture, blocks: [...fixture.blocks, duplicate] }), null)
  assert.deepEqual(ids(cut(Infinity)), [])
  assert.deepEqual(ids(cut(NaN)), [])
  console.log('Story graph: edition and exact UTF-8 anchors, chapter boundary, identity vs cooperation, fading beliefs, and no future outcome on forward/back navigation passed.')
} finally {
  fs.rmSync(temp, { force: true, recursive: true })
}
