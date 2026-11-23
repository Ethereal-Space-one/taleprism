// Exercise the real screening component and form. JSDOM simulates image decoding,
// focus and the server; this is not native-tab, viewport or backend acceptance.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { createRequire } = require('node:module')
const { JSDOM } = require('jsdom')
const root = path.resolve(__dirname, '../..')
const front = createRequire(path.join(root, 'frontend/package.json'))
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'taleprism-review-dom-'))

async function run() {
  front('esbuild').buildSync({
    entryPoints: [path.join(root, 'frontend/src/PlateScreening.tsx')],
    outfile: path.join(tmp, 'desk.cjs'),
    bundle: true,
    jsx: 'automatic',
    platform: 'node',
    format: 'cjs',
    packages: 'external',
    loader: { '.css': 'empty' },
  })
  fs.symlinkSync(path.join(root, 'frontend/node_modules'), path.join(tmp, 'node_modules'), 'dir')
  const dom = new JSDOM('<main></main>', { url: 'http://localhost:8000/' })
  const { window } = dom
  Object.assign(global, { window, document: window.document, IS_REACT_ACT_ENVIRONMENT: true })
  Object.defineProperty(global, 'navigator', { value: window.navigator, configurable: true })
  const React = front('react'),
    { act } = React
  const { QueryClient, QueryClientProvider } = front('@tanstack/react-query')
  const { createRoot } = front('react-dom/client')
  const { PlateScreening } = require(path.join(tmp, 'desk.cjs'))
  const prefix = '/api/projects/example/plate-screening'
  const row = {
    plate_id: 'p',
    image_asset_id: 'art',
    image_sha256: '1'.repeat(64),
    width: 1672,
    height: 941,
    after_byte: 12,
    paragraph_start: 0,
    decision: 'unassessed',
    evidence: '',
    observation: '',
    action: '',
    protect: '',
    reason: '',
    verification: '',
  }
  const state = {
    revision: 0,
    reader_revision: 2,
    changed: [],
    notices: [],
    worksheet: {
      schema_version: 1,
      work_id: 'example',
      source_sha256: '2'.repeat(64),
      plates: [row],
    },
    display: {
      p: {
        title: '门边',
        description: '灯亮着。',
        alt: '一盏灯落在门边的阴影里。',
        paragraph: '灯亮着。',
        display_after_byte: 24,
        display_paragraph: '门开了。',
        carrier: null,
      },
    },
    report: {
      counts: { total: 1, unassessed: 1 },
      ok: false,
      plates: [{ plate_id: 'p', errors: [] }],
    },
    timing: {
      revision: 0,
      ok: false,
      counts: { total: 1, unchecked: 1, clear: 0, revise: 0 },
      plates: {
        p: { status: 'unchecked', reason: '', evidence: '', binding: '3'.repeat(64), stale: false },
      },
    },
  }
  const writes = []
  global.fetch = async (url, opt) => {
    if (!opt) {
      assert.equal(url, prefix)
      return Response.json(state)
    }
    assert.equal(url, prefix + '/timing')
    assert.equal(opt.method, 'PUT')
    const v = JSON.parse(opt.body)
    assert.equal(v.plate_id, 'p')
    assert.equal(v.binding, state.timing.plates.p.binding)
    assert.equal(v.reader_revision, 2)
    if (v.revision !== state.timing.revision)
      return Response.json({ detail: '另一窗口已保存。' }, { status: 409 })
    writes.push(v)
    const { status, reason, evidence } = v
    Object.assign(state.timing.plates.p, { status, reason, evidence })
    state.timing.revision++
    state.timing.ok = status === 'clear'
    for (const k of ['clear', 'revise', 'unchecked']) state.timing.counts[k] = Number(k === status)
    return Response.json(state)
  }
  let consent = false
  window.confirm = () => consent
  const app = createRoot(document.querySelector('main'))
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const all = (s) => [...document.querySelectorAll(s)]
  const btn = (text) => all('button').find((b) => b.textContent.trim().startsWith(text))
  const tick = () => new Promise((r) => setTimeout(r, 10))
  const press = async (el) => {
    assert.ok(el && !el.matches(':disabled'), 'control available')
    await act(async () => {
      el.click()
      await tick()
    })
  }
  const emitImage = async (type, width = 1672) => {
    const img = document.querySelector('figure img')
    Object.defineProperties(img, {
      naturalWidth: { value: width, configurable: true },
      naturalHeight: { value: 941, configurable: true },
    })
    await act(async () => img.dispatchEvent(new window.Event(type)))
  }
  const input = async (el, text) => {
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set.call(
        el,
        text,
      )
      el.dispatchEvent(new window.Event('input', { bubbles: true }))
    })
  }
  try {
    await act(async () =>
      app.render(
        React.createElement(
          QueryClientProvider,
          { client: cache },
          React.createElement(PlateScreening, { projectId: 'example' }),
        ),
      ),
    )
    await act(tick)
    await press(btn('逐幅审图'))
    const radio = () => all('input[type=radio]')
    assert.equal(
      document.querySelector('blockquote').textContent,
      '门开了。',
      'actual display anchor, not earlier attachment',
    )
    for (const s of ['门边', '灯亮着。', '一盏灯落在门边的阴影里。'])
      assert.ok(document.querySelector('figcaption').textContent.includes(s))
    for (const [type, width] of [
      ['error', 0],
      ['load', 1500],
    ]) {
      await emitImage(type, width)
      assert.equal(document.querySelector('.screening-original'), null)
      assert.ok(radio()[0].matches(':disabled'), 'cannot review a missing or mismatched image')
      await press(btn('重新载入实图'))
    }
    await emitImage('load')
    await press(radio()[1])
    await press(btn('引用上方整段'))
    assert.ok(btn('保存时机判断').matches(':disabled'))
    const why = '图中灰袖在收钥匙，正文还没有写到。'
    await input(all('textarea')[1], why)
    const link = document.querySelector('.screening-original')
    assert.equal(link.href, document.querySelector('figure img').src)
    assert.equal(link.origin, window.location.origin)
    assert.equal(link.target, '_blank')
    assert.equal(link.tabIndex, 0)
    assert.ok(link.relList.contains('noopener'))
    link.focus()
    assert.equal(document.activeElement, link)
    // Native tab creation/navigation is the browser's responsibility. The anchor
    // has no JS click handler; model a return to the still-mounted editing window.
    await act(async () => {
      window.dispatchEvent(new window.Event('blur'))
      window.dispatchEvent(new window.Event('focus'))
    })
    assert.equal(all('textarea')[1].value, why)
    await press(btn('动静选择'))
    assert.equal(all('textarea')[1].value, why, 'declining to discard preserves timing draft')
    await press(btn('保存时机判断'))
    assert.equal(writes.length, 1)
    assert.equal(writes[0].status, 'revise')
    await press(btn('撤回时机判断'))
    assert.equal(writes.length, 1, 'dismissed reset sends nothing')
    consent = true
    await press(btn('撤回时机判断'))
    assert.deepEqual(
      [writes[1].status, writes[1].reason, writes[1].evidence],
      ['unchecked', '', ''],
    )
    await press(radio()[0])
    await press(btn('引用上方整段'))
    await input(all('textarea')[1], '保留我未保存的说明。')
    // Concurrent edit in a different window, after this draft was opened.
    state.timing.revision++
    Object.assign(state.timing.plates.p, {
      status: 'revise',
      evidence: '门开了。',
      reason: '另一窗口的意见。',
    })
    await press(btn('保存时机判断'))
    await act(tick)
    assert.ok(btn('保存时机判断').matches(':disabled'))
    assert.equal(all('textarea')[1].value, '保留我未保存的说明。')
    assert.equal(
      document.querySelector('.screening-original'),
      null,
      'stale draft must not advertise a fresh original',
    )
    assert.equal(writes.length, 2, 'conflict was not overwritten')
    await press(btn('放弃未保存的审图输入'))
    assert.equal(all('textarea')[1].value, '另一窗口的意见。')
    console.log(
      'PASS private timing form: actual reveal prose and copy, failed/mismatched/retried art, same-origin focusable original link, preserved draft, explicit save/reset, rejected stale write.',
    )
  } finally {
    await act(async () => app.unmount())
    cache.clear()
    dom.window.close()
  }
}
run()
  .catch((err) => {
    console.error(err)
    process.exitCode = 1
  })
  .finally(() => fs.rmSync(tmp, { recursive: true, force: true }))
