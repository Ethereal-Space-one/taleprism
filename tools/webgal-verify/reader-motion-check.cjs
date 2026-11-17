// Focused deterministic tests for the real resolver, renderer and canvas lifecycle.
// No DOM shim/dependency, network or reads of personal reading state are needed.
const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const root = path.resolve(__dirname, '../..')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'tale-reader-motion-'))
const saved = Object.fromEntries(['window', 'document', 'ResizeObserver', 'IntersectionObserver', 'requestAnimationFrame', 'cancelAnimationFrame'].map((name) => [name, global[name]]))
try {
  const compile = spawnSync(path.join(root, 'frontend/node_modules/.bin/tsc'), [
    '--module', 'commonjs', '--target', 'ES2022', '--jsx', 'react-jsx', '--strict', '--skipLibCheck', '--outDir', temp,
    path.join(root, 'frontend/src/reader/motion/runtime.ts'),
    path.join(root, 'frontend/src/reader/ReaderExpandedImage.tsx'),
  ], { encoding: 'utf8' })
  assert.equal(compile.status, 0, compile.stdout + compile.stderr)
  const { environmentMotionRecipes: recipes, validMotionRecipe, resolveEnvironmentMotion } = require(path.join(temp, 'reader/motion/recipes.js'))
  const { containedImageBounds, startEnvironmentMotion } = require(path.join(temp, 'reader/motion/runtime.js'))
  const { createMotionRenderer } = require(path.join(temp, 'reader/motion/render.js'))
  const [shore, rain] = recipes
  assert.ok(recipes.every(validMotionRecipe))
  function fixture(r) {
    const asset = r.imageAsset || 'fresh-upload-uuid'
    return {
      project: { canonical_sha256: r.canonicalHash },
      config: { illustrations: [{ id: r.plateId, image_asset_id: asset, after_byte: 63, title: 'title is not identity' }] },
      media: { [asset]: { id: asset, type: 'image', sha256: r.imageHash, url: './media/image.png' } },
    }
  }
  for (const recipe of recipes) {
    const data = fixture(recipe), before = JSON.stringify(data), plate = data.config.illustrations[0]
    assert.equal(resolveEnvironmentMotion(data, plate), recipe)
    data.media[plate.image_asset_id].url = '/api/projects/local/reader/assets/' + plate.image_asset_id
    assert.equal(resolveEnvironmentMotion(data, plate), recipe, 'same hash binding for backend and static URLs')
    data.media[plate.image_asset_id].url = './media/image.png'
    for (const mutate of [
      (d) => { delete d.media[plate.image_asset_id].sha256 },
      (d) => { d.media[plate.image_asset_id].sha256 = 'mismatched' },
      (d) => { d.project.canonical_sha256 = 'another-edition' },
      (d) => { d.config.illustrations[0].id = 'same-title-new-id' },
      (d) => { d.config.illustrations.push({ ...d.config.illustrations[0] }) },
      (d) => { d.media[plate.image_asset_id].type = 'figure' },
      (d) => { d.media[plate.image_asset_id].id = 'wrong-id' },
    ]) {
      const copy = JSON.parse(before); mutate(copy)
      assert.equal(resolveEnvironmentMotion(copy, copy.config.illustrations[0]), null)
    }
    assert.equal(JSON.stringify(data), before, 'resolver must not change source/config/media')
  }
  const relocated = fixture(rain), arrival = relocated.config.illustrations[0]
  relocated.media['new-import-id'] = { ...relocated.media[arrival.image_asset_id], id: 'new-import-id' }
  arrival.image_asset_id = 'new-import-id'
  assert.equal(resolveEnvironmentMotion(relocated, arrival), rain, 'generic rebuild UUIDs are allowed for exact arrival PNG')
  const normalizedArrival = '7bd8cc49a2a3dd412c876d6b20063c2496f2db4289a51937fa206e8c1060318f'
  relocated.media[arrival.image_asset_id].sha256 = normalizedArrival
  assert.equal(resolveEnvironmentMotion(relocated, arrival), rain, 'actual normalized Reader.upload/standalone PNG resolves')
  relocated.media[arrival.image_asset_id].sha256 = 'f' + normalizedArrival.slice(1)
  assert.equal(resolveEnvironmentMotion(relocated, arrival), null, 'unverified PNG encoding remains static')
  assert.equal(validMotionRecipe({ ...rain, normalizedImageHashes: ['invalid'] }), false)
  const swapped = fixture(shore), river = swapped.config.illustrations[0]
  swapped.media.other = { ...swapped.media[river.image_asset_id], id: 'other' }; river.image_asset_id = 'other'
  assert.equal(resolveEnvironmentMotion(swapped, river), null, 'fixed Chibi identity remains exact')
  assert.equal(resolveEnvironmentMotion(fixture(shore), undefined), null)
  assert.equal(validMotionRecipe({ ...rain, drops: 1000000 }), false)
  assert.equal(validMotionRecipe({ ...rain, rings: 1.5 }), false)
  assert.equal(validMotionRecipe({ ...rain, areas: [[[0, 0], [NaN, .5], [1, 1]]] }), false)
  assert.equal(validMotionRecipe({ ...shore, hits: [{ ...shore.hits[0], length: 0 }] }), false)
  assert.equal(validMotionRecipe({ ...shore, bank: [...shore.bank].reverse() }), false)
  assert.equal(validMotionRecipe({ ...rain, effect: 'arbitrary-script' }), false)
  const digest = (file) => crypto.createHash('sha256').update(fs.readFileSync(path.join(root, file))).digest('hex')
  assert.equal(digest('samples/last-light/source.txt'), rain.canonicalHash)
  assert.equal(digest('samples/last-light/arrival-v1.png'), rain.imageHash)
  const recipeFile = JSON.parse(fs.readFileSync(path.join(root, 'samples/last-light/recipe.json')))
  assert.equal('plan-' + recipeFile.shots.find((s) => s.image === 'arrival').id, rain.plateId)
  const review = JSON.parse(fs.readFileSync(path.join(root, 'examples/chibi/visual-review-v0.2.0.json')))
  assert.ok(review.images.some((i) => i.asset_id === shore.imageAsset && i.sha256 === shore.imageHash))
  // Independent reader exports preserve media metadata, while verifying image
  // bytes before rewriting URLs. No API/schema fields were added for motion.
  const exporter = fs.readFileSync(path.join(root, 'backend/src/storygal/reader_export.py'), 'utf8')
  assert.ok(exporter.includes('copy_verified(source, staging / "media" / (aid + ext), asset["sha256"])'))

  assert.deepEqual(containedImageBounds(1000, 1000, 1600, 900), { left: 0, top: 218.75, width: 1000, height: 562.5 })
  assert.deepEqual(containedImageBounds(1000, 400, 1600, 900), { left: 144.44444444444446, top: 0, width: 711.1111111111111, height: 400 })
  assert.equal(containedImageBounds(0, 400, 1600, 900), null)
  assert.equal(containedImageBounds(100, 100, Infinity, 900), null)

  let strokes = 0, maxStrokes = 0, depth = 0
  const context = new Proxy({}, {
    get(_target, name) {
      if (name === 'createRadialGradient') return () => ({ addColorStop() {} })
      return (...args) => {
        for (const v of args) if (typeof v === 'number') assert.ok(Number.isFinite(v), `${name}: non-finite coordinate`)
        if (name === 'save') depth++
        if (name === 'restore') assert.ok(--depth >= 0)
        if (name === 'stroke') strokes++
      }
    },
    set(_target, name, value) {
      if (typeof value === 'number') assert.ok(Number.isFinite(value))
      if (name === 'strokeStyle' || name === 'fillStyle') assert.ok(!String(value).includes('NaN'))
      return true
    },
  })
  const frameCounts = []
  for (const recipe of recipes) {
    const render = createMotionRenderer(context, recipe), counts = []
    for (let t = 0; t <= 14.2; t += .05) {
      strokes = 0; render(t, 1000, 563); assert.equal(depth, 0)
      assert.ok(strokes > 0 && strokes < 1500, 'fixed bounded draw budget')
      counts.push(strokes); maxStrokes = Math.max(maxStrokes, strokes)
    }
    frameCounts.push(counts)
  }
  assert.ok(new Set(frameCounts[0]).size > 8, 'shared tide phase changes approach/impact/backwash work across the cycle')
  assert.equal(new Set(frameCounts[1]).size, 1, 'rain particle count is fixed, not accumulated')

  function events(extra = {}) {
    const listeners = new Map()
    return { ...extra, listeners,
      addEventListener(name, fn) { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn) },
      removeEventListener(name, fn) { listeners.get(name)?.delete(fn) },
      emit(name) { for (const fn of [...(listeners.get(name) || [])]) fn() },
      count() { return [...listeners.values()].reduce((n, set) => n + set.size, 0) },
    }
  }
  let rafId = 0, pending = new Map(), resizers = [], intersections = []
  global.requestAnimationFrame = (fn) => { const id = ++rafId; pending.set(id, fn); return id }
  global.cancelAnimationFrame = (id) => pending.delete(id)
  const media = events({ matches: false })
  global.window = events({ devicePixelRatio: 3, matchMedia: () => media })
  global.document = events({ hidden: false })
  global.ResizeObserver = class {
    constructor(cb) { this.cb = cb; this.targets = new Set(); resizers.push(this) }
    observe(target) { this.targets.add(target) }
    disconnect() { this.targets.clear() }
  }
  global.IntersectionObserver = class {
    constructor(cb) { this.cb = cb; this.targets = new Set(); intersections.push(this) }
    observe(target) { this.targets.add(target) }
    disconnect() { this.targets.clear() }
  }
  const image = events({ complete: false, naturalWidth: 0, naturalHeight: 0, isConnected: true,
    getBoundingClientRect: () => ({ left: 30, top: 50, width: 1000, height: 1000 }) })
  const viewport = { isConnected: true, scrollLeft: 0, scrollTop: 0, clientLeft: 0, clientTop: 0,
    getBoundingClientRect: () => ({ left: 30, top: 50, width: 1000, height: 1000 }) }
  const canvas = { hidden: true, style: {}, width: 0, height: 0, getContext: () => context }
  const tick = (t) => { const callbacks = [...pending.values()]; pending.clear(); callbacks.forEach((cb) => cb(t)) }
  const intersect = (visible) => intersections.at(-1).cb([{ target: viewport, isIntersecting: visible, intersectionRatio: visible ? 1 : 0 }])
  const stop = startEnvironmentMotion(image, canvas, viewport, shore)
  intersect(true)
  assert.equal(pending.size, 0, 'not loaded: static')
  image.complete = true; image.naturalWidth = shore.width; image.naturalHeight = shore.height; image.emit('load')
  assert.equal(pending.size, 1); assert.equal(canvas.hidden, false)
  assert.equal(canvas.style.left, '0px')
  assert.equal(canvas.style.top, `${(1000 - 1000 * 941 / 1672) / 2}px`)
  assert.equal(canvas.width, 1500, 'DPR is capped at 1.5')
  tick(0); tick(50); assert.equal(pending.size, 1, 'exactly one frame scheduled')
  document.hidden = true; document.emit('visibilitychange')
  assert.equal(pending.size, 0); assert.equal(canvas.hidden, true)
  document.hidden = false; document.emit('visibilitychange'); assert.equal(pending.size, 1)
  intersect(false); assert.equal(pending.size, 0); assert.equal(canvas.hidden, true)
  intersect(true); media.matches = true; media.emit('change'); assert.equal(pending.size, 0)
  media.matches = false; media.emit('change'); assert.equal(pending.size, 1)
  image.naturalWidth = 42; image.emit('load'); assert.equal(pending.size, 0, 'wrong actual image dimensions: static')
  image.naturalWidth = shore.width; image.emit('load'); assert.equal(pending.size, 1)
  image.emit('error'); assert.equal(pending.size, 0, 'error: static')
  image.emit('load'); assert.equal(pending.size, 1)
  viewport.isConnected = false; tick(100); assert.equal(pending.size, 0, 'detached viewer: static')
  viewport.isConnected = true; document.emit('visibilitychange')
  stop(); stop(); assert.equal(pending.size, 0); assert.equal(canvas.hidden, true)
  for (const emitter of [image, document, window, media]) assert.equal(emitter.count(), 0, 'listeners released')
  for (const observer of [...resizers, ...intersections]) assert.equal(observer.targets.size, 0, 'observers disconnected')
  intersections[0].cb([{ target: viewport, isIntersecting: true, intersectionRatio: 1 }]); resizers[0].cb()
  assert.equal(pending.size, 0, 'late callbacks after unmount cannot restart motion')
  // Toggle off, zoom, image switch and dialog close all execute this same cleanup.
  for (let visit = 0; visit < 8; visit++) {
    const cleanup = startEnvironmentMotion(image, canvas, viewport, rain)
    intersect(true); assert.equal(pending.size, 1); cleanup(); assert.equal(pending.size, 0)
  }
  // Exercise the actual React component effects with deterministic hook slots.
  // This checks user opt-in, zoom, disclosure, reduced-motion changes, unmount,
  // and ensures animation frames never write React state.
  fs.symlinkSync(path.join(root, 'frontend/node_modules'), path.join(temp, 'node_modules'), 'dir')
  const Module = require('node:module'), originalLoad = Module._load
  let hookIndex = 0, stateWrites = 0, queuedEffects = [], slots = []
  const hooks = {
    useRef(initial) { const i = hookIndex++; return slots[i] ||= { current: initial } },
    useState(initial) {
      const i = hookIndex++; slots[i] ||= { value: initial }
      return [slots[i].value, (v) => { stateWrites++; slots[i].value = typeof v === 'function' ? v(slots[i].value) : v }]
    },
    useEffect(fn, deps) {
      const i = hookIndex++, old = slots[i]
      if (!old || deps.some((d, n) => d !== old.deps[n])) queuedEffects.push(() => {
        old?.cleanup?.(); slots[i] = { deps, cleanup: fn() }
      })
    },
  }
  Module._load = function(name, ...args) { return name === 'react' ? hooks : name === 'react/jsx-runtime' ? { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }), Fragment: 'fragment' } : originalLoad.call(this, name, ...args) }
  let ReaderExpandedImage
  try { ({ ReaderExpandedImage } = require(path.join(temp, 'reader/ReaderExpandedImage.js'))) }
  finally { Module._load = originalLoad }
  const props = { viewportRef: { current: viewport }, src: './media/a.png', alt: 'static artwork',
    zoomed: false, pending: false, recipe: rain, onLoad() {}, onError() {} }
  let buttons = []
  const visitNode = (node) => {
    if (!node || typeof node !== 'object') return
    if (Array.isArray(node)) { node.forEach(visitNode); return }
    if (node.type === 'img') node.props.ref.current = image
    if (node.type === 'canvas') node.props.ref.current = canvas
    if (node.type === 'button') buttons.push(node)
    visitNode(node.props?.children)
  }
  const renderComponent = () => {
    hookIndex = 0; buttons = []; visitNode(ReaderExpandedImage(props))
    const effects = queuedEffects; queuedEffects = []; effects.forEach((fn) => fn())
  }
  const unmount = () => { for (const slot of slots) slot?.cleanup?.(); slots = []; pending.clear() }
  renderComponent(); renderComponent()
  assert.equal(buttons[0].props['aria-pressed'], false)
  assert.equal(pending.size, 0, 'opening viewer defaults static')
  buttons[0].props.onClick(); renderComponent(); intersect(true)
  assert.equal(pending.size, 1); assert.equal(buttons[0].props['aria-pressed'], true)
  const writesBeforeFrames = stateWrites
  tick(200); tick(250); assert.equal(stateWrites, writesBeforeFrames, 'RAF does not update React')
  props.zoomed = true; renderComponent()
  assert.equal(pending.size, 0); assert.equal(canvas.hidden, true)
  assert.equal(buttons[0].props.disabled, true)
  props.zoomed = false; renderComponent(); intersect(true); assert.equal(pending.size, 1)
  props.pending = true; renderComponent(); assert.equal(pending.size, 0, 'pending spoiler choice is static')
  props.pending = false; renderComponent(); intersect(true); assert.equal(pending.size, 1)
  buttons[0].props.onClick(); renderComponent(); assert.equal(pending.size, 0, 'toggle off stops immediately')
  buttons[0].props.onClick(); renderComponent(); intersect(true)
  media.matches = true; media.emit('change'); renderComponent()
  assert.equal(pending.size, 0); assert.equal(buttons[0].props.disabled, true)
  media.matches = false; media.emit('change'); renderComponent()
  assert.equal(pending.size, 0, 'leaving reduced motion never automatically opts back in')
  buttons[0].props.onClick(); renderComponent(); intersect(true); assert.equal(pending.size, 1)
  unmount(); assert.equal(canvas.hidden, true)
  for (const emitter of [image, document, window, media]) assert.equal(emitter.count(), 0)
  renderComponent(); renderComponent(); assert.equal(pending.size, 0, 'next image or reopened viewer resets opt-in')
  unmount()
  assert.equal(startEnvironmentMotion(image, { ...canvas, getContext: () => null }, viewport, rain)(), undefined)
  delete global.IntersectionObserver
  const beforeUnsupported = resizers.length
  startEnvironmentMotion(image, canvas, viewport, rain)()
  assert.equal(resizers.length, beforeUnsupported, 'unsupported browser allocates no observers')
  assert.equal(canvas.hidden, true)

  const app = fs.readFileSync(path.join(root, 'frontend/src/ReaderApp.tsx'), 'utf8')
  const viewer = fs.readFileSync(path.join(root, 'frontend/src/reader/ReaderExpandedImage.tsx'), 'utf8')
  assert.equal((app.match(/<ReaderExpandedImage/g) || []).length, 1)
  assert.ok(app.includes("panel === 'image' && expandedImage"))
  assert.ok(app.includes('pending={!!imageVisit?.pending}'))
  assert.ok(viewer.includes('useState(false)'), 'motion defaults off')
  assert.ok(viewer.replace(/\s+/g, ' ').includes('!enabled || reduced || zoomed || pending'), 'zoom/disclosure disable runtime')
  for (const staticFile of ['ReaderPlate.tsx', 'ReaderContents.tsx']) {
    assert.ok(!fs.readFileSync(path.join(root, 'frontend/src/reader', staticFile), 'utf8').includes('startEnvironmentMotion'))
  }
  assert.ok(!app.includes('wave-impact-backwash') && !app.includes('rain-wet-ground'), 'no story-specific renderer branches in ReaderApp')
  console.log(`Reader motion: exact edition/image binding, generic arrival UUIDs, finite bounded recipes/rendering (max ${maxStrokes} strokes/frame), contain geometry, static fallbacks and repeated lifecycle cleanup passed.`)
} finally {
  for (const [name, value] of Object.entries(saved)) if (value === undefined) delete global[name]; else global[name] = value
  fs.rmSync(temp, { recursive: true, force: true })
}
