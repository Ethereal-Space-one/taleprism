// Actual React/React Query interaction regressions in JSDOM. This intentionally
// stubs Canvas runtime callbacks. It is NOT browser, layout or art acceptance.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const { createRequire } = require('node:module')
const Module = require('node:module')
const { JSDOM } = require('jsdom')

const repo = path.resolve(__dirname, '../..')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'taleprism-motion-dom-'))
let dom, root, queryClient
const originalLoad = Module._load
const savedGlobals = Object.fromEntries(
  ['window', 'document', 'HTMLElement', 'Event', 'MouseEvent', 'navigator', 'fetch', 'IS_REACT_ACT_ENVIRONMENT']
    .map((name) => [name, Object.getOwnPropertyDescriptor(global, name)]),
)

async function main() {
  const compiled = spawnSync(path.join(repo, 'frontend/node_modules/.bin/tsc'), [
    '--module', 'commonjs', '--target', 'ES2022', '--jsx', 'react-jsx', '--strict',
    '--skipLibCheck', '--esModuleInterop', '--outDir', temp,
    path.join(repo, 'frontend/src/reader/ArrangementEditor.tsx'),
    path.join(repo, 'frontend/src/reader/MotionDirector.tsx'),
  ], { encoding: 'utf8' })
  assert.equal(compiled.status, 0, compiled.stdout + compiled.stderr)
  fs.symlinkSync(path.join(repo, 'frontend/node_modules'), path.join(temp, 'node_modules'), 'dir')

  dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: 'http://qa.invalid/' })
  Object.assign(global, {
    window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement,
    Event: dom.window.Event, MouseEvent: dom.window.MouseEvent, IS_REACT_ACT_ENVIRONMENT: true,
  })
  Object.defineProperty(global, 'navigator', { value: dom.window.navigator, configurable: true })
  window.confirm = () => true // These explicit reloads deliberately discard edit-only drafts.
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })
  const frontendRequire = createRequire(path.join(repo, 'frontend/package.json'))
  const React = frontendRequire('react')
  const { act } = React
  const { createRoot } = frontendRequire('react-dom/client')
  const { QueryClient, QueryClientProvider } = frontendRequire('@tanstack/react-query')
  let firstFrame, reviewCycle, starts = 0, stops = 0
  Module._load = function (name, ...args) {
    if (name.endsWith('.css')) return {}
    if (name === './motion/runtime') return {
      supportsEnvironmentMotion: () => true,
      startEnvironmentMotion(_image, _canvas, _viewport, _recipe, frame, cycle) {
        starts++; firstFrame = frame; reviewCycle = cycle
        return () => stops++
      },
    }
    return originalLoad.call(this, name, ...args)
  }
  const { MotionDirector } = require(path.join(temp, 'reader/MotionDirector.js'))
  const { ArrangementEditor } = require(path.join(temp, 'reader/ArrangementEditor.js'))
  Module._load = originalLoad

  const asset = { id: 'a', kind: 'scene', status: 'accepted', sha256: '1'.repeat(64), width: 160, height: 90, url: '/synthetic.png' }
  const paragraph = { byte_start: 0, byte_end: 99, text: '傍晚的雨斜着落进站台，远方的路灯还没有点亮。', preview: '傍晚的雨斜着落进站台' }
  const content = {
    project: { canonical_sha256: '2'.repeat(64) }, config: { illustrations: [] },
    media: { a: { id: 'a', type: 'image', sha256: asset.sha256, width: 160, height: 90 } },
    presentations: [],
  }
  const all = (selector) => [...document.querySelectorAll(selector)]
  const button = (text) => all('button').find((b) => b.textContent.includes(text))
  const tick = () => new Promise((resolve) => setTimeout(resolve, 10))
  async function click(element) {
    assert.ok(element, 'expected control exists')
    assert.equal(element.disabled, false, element.textContent)
    await act(async () => element.dispatchEvent(new MouseEvent('click', { bubbles: true })))
  }
  async function fill(element, value) {
    await act(async () => {
      const prototype = element.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype
        : element.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype
      Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, String(value))
      element.dispatchEvent(new Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }))
    })
  }
  async function point(x, y) {
    await fill(all('input[type=number]')[0], x)
    await fill(all('input[type=number]')[1], y)
    await click(button('添加坐标点'))
  }
  async function openDirector() {
    await act(async () => {
      const details = document.querySelector('.motion-director')
      details.open = true
      details.dispatchEvent(new Event('toggle'))
      document.querySelector('.motion-director-map img').dispatchEvent(new Event('load'))
    })
  }

  // A real new-creator editing loop, including keyboard coordinate fallback.
  let published = null, pending = false
  const reportPending = (_id, value) => { pending = value }
  function Harness() {
    const [plate, setPlate] = React.useState({ id: 'p', after_byte: 99, image_asset_id: 'a', title: 'Synthetic image', description: '', motion: null })
    content.config.illustrations = [plate]
    return React.createElement(MotionDirector, {
      plate, asset, state: { paragraphs: [paragraph] }, content, onPendingChange: reportPending,
      onChange(motion) { published = motion; setPlate((old) => ({ ...old, motion })) },
    })
  }
  root = createRoot(document.getElementById('root'))
  await act(async () => root.render(React.createElement(Harness)))
  await openDirector()
  const review = () => document.querySelector('input[type=checkbox]')
  assert.equal(review().checked, false)
  assert.equal(review().disabled, true)
  assert.equal(button('纳入章节草稿').disabled, true, 'incomplete recipe cannot be included')
  await fill(all('select')[1], 0)
  await fill(all('textarea')[1], '左侧雨区不覆盖人物手部，人物和重要道具保持稳定。')
  await point(0, 0); await point(30, 0); await point(30, 100); await point(0, 100); await point(10, 50)
  assert.equal(pending, true, 'unapplied points are reported to outer editor')
  await click(button('撤回最后一点'))
  assert.match(document.body.textContent, /当前标点 4 个/)
  await click(button('闭合并加入范围'))
  await click(button('标接雨湿地'))
  await point(0, 80); await point(30, 80); await point(30, 100); await point(0, 100)
  await click(button('闭合并加入范围'))
  await fill(all('input[type=range]')[1], 4)
  assert.equal(button('纳入章节草稿').disabled, false, 'valid unreviewed drafts may save static')
  assert.equal(review().disabled, true, 'geometry alone never constitutes review')
  await click(button('打开动效对照'))
  assert.equal(starts, 0, 'comparison starts static')
  await click(button('开启动效'))
  assert.equal(starts, 1)
  assert.equal(review().disabled, true, 'opt-in without rendered cycle is insufficient')
  await act(async () => firstFrame?.())
  assert.equal(review().disabled, true, 'one rendered frame is not a full cycle')
  await act(async () => reviewCycle())
  assert.equal(review().disabled, false)
  await click(review()); await click(button('纳入章节草稿'))
  assert.equal(published.reviewed, true)
  assert.equal(published.ground.length, 1)
  assert.equal(pending, false)
  await fill(all('input[type=range]')[0], 50)
  assert.equal(review().checked, false, 'parameter edits invalidate approval')
  assert.equal(review().disabled, true)
  assert.equal(pending, true)
  await click(button('放弃本面板修改'))
  assert.equal(review().checked, true, 'discard restores previously included approval')
  assert.equal(pending, false)
  const approved = published
  await click(button('只用静图'))
  assert.equal(published, null, 'static is an explicit override, not demo fallback')
  await act(async () => root.unmount()); root = null
  assert.ok(stops >= 1, 'preview resources disposed')

  // Real React Query delayed PATCH: a response acknowledges only its snapshot.
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { gcTime: 0 } } })
  let submitted, finish, sampleSubmitted, finishSample
  global.fetch = async (_url, options) => {
    if (options?.method === 'POST' && String(_url).endsWith('/choreography/sample')) {
      sampleSubmitted = JSON.parse(options.body)
      return new Promise((resolve) => { finishSample = (next) => resolve(new Response(JSON.stringify(next), { status: 200, headers: { 'Content-Type': 'application/json' } })) })
    }
    if (options?.method === 'PATCH') {
      submitted = JSON.parse(options.body)
      return new Promise((resolve) => { finish = () => resolve(new Response('{"saved":true}', { status: 200, headers: { 'Content-Type': 'application/json' } })) })
    }
    return new Response('{"revision":0,"issues":[]}', { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  let state = {
    revision: 0, chibi_sample: false,
    assets: [asset, { ...asset, id: 'b', sha256: '3'.repeat(64), url: '/synthetic-b.png' }],
    paragraphs: [paragraph, { ...paragraph, byte_start: 100, byte_end: 199, text: '雨已经停了，旅人收起伞，走向另一边明亮的街口。' }],
    config: { title: 'QA', subtitle: '', cover_asset_id: null, scenes: [], map_profile: null, illustrations: [{ id: 'p', after_byte: 99, image_asset_id: 'a', title: 'Original', description: '', motion: approved }], presentations: [], map_entries: [] },
  }
  content.config = state.config
  const element = () => React.createElement(QueryClientProvider, { client: queryClient }, React.createElement(ArrangementEditor, { projectId: 'p', state, content }))
  const title = () => all('label').find((label) => label.textContent.trim() === '插图名称').querySelector('input')
  root = createRoot(document.getElementById('root'))
  await act(async () => { root.render(element()); await tick() })
  await fill(title(), 'A included before save')
  assert.equal(button('保存章节编排').disabled, false)
  await openDirector()
  await fill(all('.motion-director textarea')[1], '还未纳入章节的新观察修改，应当阻止保存造成遗漏。')
  assert.equal(button('保存章节编排').disabled, true, 'unapplied direction blocks outer save')
  await click(button('放弃本面板修改'))
  assert.equal(button('保存章节编排').disabled, false)
  await act(async () => { button('保存章节编排').click(); await tick() })
  assert.equal(submitted.illustrations[0].title, 'A included before save')
  await fill(title(), 'B included during save')
  await act(async () => { finish(); await tick() })
  assert.equal(button('保存章节编排').disabled, false, 'newer unsaved B remains dirty/saveable after A succeeds')
  // A refreshed server copy must not erase B while B remains dirty.
  state = { ...state, revision: 1, config: { ...state.config, illustrations: submitted.illustrations } }
  await act(async () => { root.render(element()); await tick() })
  assert.equal(title().value, 'B included during save')
  assert.equal(button('保存章节编排').disabled, false)
  const labelledSelect = (text) => all('label').find((label) => label.firstChild?.textContent.trim() === text).querySelector('select')
  await fill(labelledSelect('插图素材'), 'b')
  assert.match(document.querySelector('.motion-director summary').textContent, /静图/,
    'changing image clears the reviewed direction and remounts a static editor')
  assert.equal(all('.motion-director input[type=checkbox]')[0].checked, false)
  // Explicit reload is the only permitted replacement of a newer local draft.
  state = { ...state, revision: 2, config: { ...state.config, illustrations: submitted.illustrations } }
  await act(async () => { root.render(element()); await tick() })
  await click(button('载入最新配置'))
  assert.match(document.querySelector('.motion-director summary').textContent, /已复核/)
  await fill(labelledSelect('放在此段之后'), 199)
  assert.match(document.querySelector('.motion-director summary').textContent, /静图/,
    'changing context clears the reviewed direction instead of reusing old review')
  assert.equal(all('.motion-director input[type=checkbox]')[0].checked, false)

  // Sample-application responses are also snapshots, not permission to erase
  // edits made while the request was in flight. Only the sample endpoint is fake.
  state = { ...state, chibi_sample: true }
  await act(async () => { root.render(element()); await tick() })
  await click(button('载入最新配置'))
  const applySample = () => button('应用赤壁人物与事件编排')
  assert.equal(applySample().disabled, false)
  await openDirector()
  await fill(all('.motion-director textarea')[1], '仅在本动效面板的新观察，尚未纳入章节也不能被样例覆盖。')
  assert.equal(applySample().disabled, true, 'unapplied local motion blocks sample application')
  await click(button('放弃本面板修改'))
  assert.equal(applySample().disabled, false)
  await act(async () => { applySample().click(); await tick() })
  assert.equal(sampleSubmitted.revision, 2)
  await fill(title(), 'Newer outer edit while sample is pending')
  const localDuringSample = '样例请求期间的新动效观察，必须保留人物保护和本面板草稿。'
  await fill(all('.motion-director textarea')[1], localDuringSample)
  const lateSample = { ...state, revision: 3, config: { ...state.config, illustrations: state.config.illustrations.map((plate) => ({ ...plate, title: 'LATE SAMPLE MUST NOT ERASE NEWER EDITS' })) } }
  state = lateSample
  await act(async () => { root.render(element()); finishSample(lateSample); await tick() })
  assert.equal(title().value, 'Newer outer edit while sample is pending')
  assert.equal(all('.motion-director textarea')[1].value, localDuringSample)
  assert.equal(button('保存章节编排').disabled, true, 'local pending direction still blocks global save')
  await click(button('放弃本面板修改'))
  assert.equal(button('保存章节编排').disabled, false, 'newer outer edit remains dirty after late sample')

  // Exercise the pending-motion guard independently of the outer edit counter.
  await click(button('载入最新配置'))
  assert.equal(applySample().disabled, false)
  await openDirector()
  const priorSampleTitle = title().value
  await act(async () => { applySample().click(); await tick() })
  assert.equal(sampleSubmitted.revision, 3)
  const localOnly = '这次只改动本动效面板，不改变外层字段，旧样例响应仍不得覆盖。'
  await fill(all('.motion-director textarea')[1], localOnly)
  const secondLateSample = { ...state, revision: 4, config: { ...state.config, illustrations: state.config.illustrations.map((plate) => ({ ...plate, title: 'SECOND LATE SAMPLE MUST NOT WIN' })) } }
  state = secondLateSample
  await act(async () => { root.render(element()); finishSample(secondLateSample); await tick() })
  assert.equal(title().value, priorSampleTitle, 'local-only editing prevents sample draft replacement')
  assert.equal(all('.motion-director textarea')[1].value, localOnly)
  assert.equal(button('保存章节编排').disabled, true)
  await act(async () => root.unmount()); root = null
  queryClient.clear(); queryClient = null
  console.log('Reader motion DOM: real React point/ground editing, cycle-gated review, edit invalidation, pending/apply/discard/static, cleanup, and delayed save/sample newer-draft preservation, local-only sample guard and image/context invalidation passed. Canvas runtime is stubbed; not browser/visual acceptance.')
}

main().catch((error) => { console.error(error); process.exitCode = 1 }).finally(async () => {
  Module._load = originalLoad
  if (root) {
    const frontendRequire = createRequire(path.join(repo, 'frontend/package.json'))
    await frontendRequire('react').act(async () => root.unmount())
  }
  queryClient?.clear()
  dom?.window.close()
  for (const [name, descriptor] of Object.entries(savedGlobals)) {
    if (descriptor) Object.defineProperty(global, name, descriptor)
    else delete global[name]
  }
  fs.rmSync(temp, { recursive: true, force: true })
})
