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
      blocks: [{ byte_start: 0, byte_end: 63, text: '第四十九回　七星壇諸葛祭風　三江口周瑜縱火' }],
      config: { illustrations: [{ id: r.plateId, image_asset_id: asset, after_byte: 63, title: 'title is not identity' }] },
      media: { [asset]: { id: asset, type: 'image', sha256: r.imageHash, width: r.width, height: r.height, url: './media/image.png' } },
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
  const normalizedArrivals = [
    '7bd8cc49a2a3dd412c876d6b20063c2496f2db4289a51937fa206e8c1060318f',
    '2dc65d6e43f987fdb4b908e43fb34fb37f66aaf8c271d21f6b40ea5658c4ddec',
  ]
  assert.deepEqual(rain.normalizedImageHashes, normalizedArrivals, 'only the two exact known encoder outputs are allowed')
  for (const normalizedArrival of normalizedArrivals) {
    relocated.media[arrival.image_asset_id].sha256 = normalizedArrival
    assert.equal(resolveEnvironmentMotion(relocated, arrival), rain, 'known Linux/macOS Reader.upload/standalone PNG resolves')
  }
  const unverifiedArrival = 'f' + normalizedArrivals[0].slice(1)
  relocated.media[arrival.image_asset_id].sha256 = unverifiedArrival
  assert.equal(resolveEnvironmentMotion(relocated, arrival), null, 'unverified PNG encoding remains static')
  assert.equal(validMotionRecipe({ ...rain, normalizedImageHashes: ['invalid'] }), false)
  assert.equal(validMotionRecipe({ ...rain, normalizedImageHashes: [...normalizedArrivals, unverifiedArrival] }), false, 'two-normalized-output cap remains enforced')
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

  // Record actual submitted particle paths, not just a non-empty canvas clip.
  // The old composition-specific renderer passed the work-budget test while
  // rendering nothing in left/top masks and silently rejecting right-side spray.
  function recordedRenderer(recipe) {
    let path = [], mask = null, strokeStyle = '', fillStyle = '', translation = null
    const stack = [], draws = []
    const context = new Proxy({}, {
      get(_target, name) {
        if (name === 'createRadialGradient') return () => ({ addColorStop() {} })
        return (...args) => {
          for (const v of args) if (typeof v === 'number') assert.ok(Number.isFinite(v), `${name}: finite geometry`)
          if (name === 'save') stack.push({ mask, translation })
          if (name === 'restore') { assert.ok(stack.length); ({ mask, translation } = stack.pop()) }
          if (name === 'beginPath') path = []
          if (['moveTo', 'lineTo', 'ellipse', 'closePath'].includes(name)) path.push([name, ...args])
          if (name === 'clip') mask = path.map((p) => [...p])
          if (name === 'translate') translation = args
          if (name === 'stroke') draws.push({ type: 'stroke', path: path.map((p) => [...p]), mask, style: strokeStyle })
          if (name === 'fillRect') draws.push({ type: 'soft', center: translation, mask, style: fillStyle })
        }
      },
      set(_target, name, value) {
        if (typeof value === 'number') assert.ok(Number.isFinite(value))
        if (name === 'strokeStyle') strokeStyle = value
        if (name === 'fillStyle') fillStyle = value
        return true
      },
    })
    const render = createMotionRenderer(context, recipe)
    return (t) => { draws.length = 0; render(t, 1000, 563); assert.equal(stack.length, 0); return JSON.parse(JSON.stringify(draws)) }
  }
  const inPolygon = (points, x, y) => {
    let inside = false
    for (let i = 0; i < points.length; i++) {
      const [ax, ay] = points[i], [bx, by] = points[(i + 1) % points.length]
      if (Math.abs((x - ax) * (by - ay) - (y - ay) * (bx - ax)) < 1e-11 &&
          x >= Math.min(ax, bx) - 1e-11 && x <= Math.max(ax, bx) + 1e-11 &&
          y >= Math.min(ay, by) - 1e-11 && y <= Math.max(ay, by) + 1e-11) return true
      if ((ay > y) !== (by > y) && x < ax + (y - ay) * (bx - ax) / (by - ay)) inside = !inside
    }
    return inside
  }
  const assertMasked = (draws, polygons) => {
    const within = (x, y) => polygons.some((p) => inPolygon(p, x, y))
    for (const draw of draws) {
      assert.ok(draw.mask?.length, 'every streak, ring and soft spray stays canvas-clipped to creator polygons')
      if (draw.type === 'soft') {
        assert.ok(draw.center && within(...draw.center), 'soft particle centers must not be repeatedly drawn outside the mask')
        continue
      }
      for (const [kind, x, y, rx, ry] of draw.path) {
        if (kind === 'moveTo' || kind === 'lineTo') assert.ok(within(x, y), `submitted streak point ${x},${y} is inside mask`)
        if (kind === 'ellipse') {
          assert.ok(rx > 0 && ry > 0, 'rings have actual positive radii')
          for (let a = 0; a < 16; a++)
            assert.ok(within(x + rx * Math.cos(a * Math.PI / 8), y + ry * Math.sin(a * Math.PI / 8)), 'rain rings fit inside their authored mask')
        }
      }
    }
  }
  const leftMask = [[[.015, .08], [.045, .08], [.045, .145], [.015, .145]]]
  const topMask = [[[.12, .015], [.18, .015], [.18, .035], [.12, .035]]]
  const concaveMask = [[[.02, .02], [.1, .02], [.1, .035], [.04, .035], [.04, .12], [.02, .12]]]
  const originalMathRandom = Math.random
  Math.random = () => { throw Error('renderer must not use runtime randomness') }
  try {
    for (const areas of [leftMask, topMask, concaveMask]) {
      const recipe = { ...rain, areas, ground: areas, drops: 24, rings: 5 }, before = JSON.stringify(recipe)
      const render = recordedRenderer(recipe), repeated = recordedRenderer(recipe)
      for (const t of [0, .23, 1.71, 7.09, 1000]) {
        const draws = render(t)
        assert.equal(draws.filter((d) => d.type === 'stroke').length, recipe.drops, 'tiny masks receive every actual rain/contact particle')
        const ringCount = draws.filter((d) => d.path?.some(([kind]) => kind === 'ellipse')).length
        assert.ok(ringCount > 0 && ringCount <= recipe.rings, 'wet-mask contacts alternate falling streaks and real rings')
        assertMasked(draws, areas)
        assert.deepEqual(draws, repeated(t), 'particle layout and phases repeat from the same recipe/time')
        assert.deepEqual(render(t), draws, 'no particle accumulation or time-step state')
      }
      assert.equal(JSON.stringify(recipe), before, 'sampling does not rewrite creator geometry')
    }
    const explicitGround = [[[.019, .12], [.04, .12], [.04, .14], [.019, .14]]]
    const causalRecipe = { ...rain, areas: leftMask, ground: explicitGround, drops: 1, rings: 1 }
    const causal = recordedRenderer(causalRecipe), contactTime = .46 / .73
    const prior = causal(contactTime - .02), contact = causal(contactTime), after = causal(contactTime + .1)
    assert.equal(prior.length, 1)
    assert.ok(!prior.some((d) => d.path?.some(([kind]) => kind === 'ellipse')), 'no ripple before its paired drop reaches ground')
    const contactLine = contact.find((d) => d.path?.some(([kind]) => kind === 'lineTo'))
    const contactRing = contact.find((d) => d.path?.some(([kind]) => kind === 'ellipse'))
    assert.ok(contactLine && contactRing, 'drop contact and first ripple share an actual event')
    const endpoint = contactLine.path.find(([kind]) => kind === 'lineTo').slice(1)
    const initialRing = contactRing.path.find(([kind]) => kind === 'ellipse')
    assert.ok(Math.abs(endpoint[0] - initialRing[1]) < 1e-12 && Math.abs(endpoint[1] - initialRing[2]) < 1e-12,
      'the falling streak endpoint is exactly the ring origin')
    const priorEndpoint = prior[0].path.find(([kind]) => kind === 'lineTo').slice(1)
    assert.ok(priorEndpoint[1] < endpoint[1], 'drop approaches ground before contact')
    const grownRing = after.find((d) => d.path?.some(([kind]) => kind === 'ellipse'))?.path.find(([kind]) => kind === 'ellipse')
    assert.ok(grownRing && grownRing[3] > initialRing[3], 'same-point ripple expands only after contact')
    assert.deepEqual(grownRing.slice(1, 3), initialRing.slice(1, 3))
    for (const draws of [prior, contact, after]) assertMasked(draws, leftMask)
    assertMasked([contactRing, ...after], explicitGround)
    // A sky-only mask, absent wet-ground metadata, empty ground, and disjoint
    // ground all remain falling rain. Screen height never invents a wet surface.
    for (const ground of [undefined, [], [[[.7, .7], [.8, .7], [.8, .9], [.7, .9]]]]) {
      const sky = recordedRenderer({ ...rain, areas: topMask, ground, drops: 8, rings: 16 })
      for (const t of [0, .3, contactTime, 1, 2]) {
        const draws = sky(t)
        assert.equal(draws.length, 8)
        assert.ok(!draws.some((d) => d.path?.some(([kind]) => kind === 'ellipse')), 'no explicit overlapping wet ground means no rings')
        assertMasked(draws, topMask)
      }
    }
    // Opposite input winding must not cancel overlapping allowed regions.
    const nested = [[.022, .1], [.038, .1], [.038, .13], [.022, .13]]
    const windingAreas = [leftMask[0], nested.slice().reverse()]
    const winding = recordedRenderer({ ...rain, areas: windingAreas, ground: [], drops: 8, rings: 2 })(0)
    const windingGround = recordedRenderer({ ...rain, areas: windingAreas, ground: windingAreas, drops: 1, rings: 1 })(contactTime)
      .find((d) => d.path?.some(([kind]) => kind === 'ellipse'))
    const windingWater = recordedRenderer({ ...shore, water: windingAreas, bank: [[.015, .14], [.045, .14]],
      hits: [{ x: .03, phase: 0, length: 7.1, gain: 1 }] })(0).find((d) => d.type === 'stroke')
    const signedArea = (p) => p.reduce((sum, [x, y], i) => sum + x * p[(i + 1) % p.length][1] - p[(i + 1) % p.length][0] * y, 0)
    for (const draw of [winding[0], windingGround, windingWater]) {
      assert.ok(draw, 'rain, wet ground and shoreline all draw within nested union masks')
      const clipPolys = [], current = []
      for (const [kind, x, y] of draw.mask) {
        if (kind === 'moveTo') { current.length = 0; current.push([x, y]) }
        else if (kind === 'lineTo') current.push([x, y])
        else if (kind === 'closePath') clipPolys.push([...current])
      }
      assert.equal(clipPolys.length, 2)
      assert.ok(clipPolys.every((p) => signedArea(p) > 0), 'opposite-winding nested area/ground/water polygons stay a union, not accidental holes')
    }

    const rightShore = { ...shore, water: [[[.82, .06], [.99, .06], [.99, .15], [.82, .15]]],
      bank: [[.83, .145], [.98, .115]], hits: [{ x: .91, phase: 0, length: 7.1, gain: 1.1 }] }
    const tinyShore = { ...shore, water: [[[.015, .012], [.065, .012], [.065, .05], [.015, .05]]],
      bank: [[.018, .048], [.06, .04]], hits: [{ x: .04, phase: 0, length: 7.1, gain: .9 }] }
    for (const recipe of [rightShore, tinyShore]) {
      const before = JSON.stringify(recipe), render = recordedRenderer(recipe), counts = []
      for (let t = 0; t < 7.1; t += .1) {
        const draws = render(t)
        assert.ok(draws.some((d) => d.type === 'stroke'), 'arbitrary shoreline remains visible throughout its cycle')
        assertMasked(draws, recipe.water)
        counts.push(draws.length)
      }
      assert.ok(new Set(counts).size > 8, 'localized approach, impact and backwash retain phase changes')
      const impact = render(0)
      assert.ok(impact.some((d) => d.type === 'stroke' && /rgba\((226,246,242|165,217,227),/.test(d.style)), 'arbitrary shoreline has actual impact spray')
      assert.ok(render(1.3).some((d) => d.type === 'stroke' && d.style.startsWith('rgba(221,241,235,')), 'actual backwash follows impact')
      assert.equal(JSON.stringify(recipe), before)
    }
    const offMaskBank = recordedRenderer({ ...rightShore, bank: [[.83, .9], [.98, .9]] })
    for (const t of [0, 1.3, 4, 6.3]) assert.deepEqual(offMaskBank(t), [], 'off-mask bank must not be relocated to an invented contact line')
    const maximumShore = { ...shore, water: [[[0, 0], [1, 0], [1, 1], [0, 1]]], bank: [[0, .9], [1, .9]],
      hits: Array.from({ length: 6 }, (_, i) => ({ x: .25 + i * .1, phase: 0, length: 7.1, gain: 1.3 })) }
    const maximumRender = recordedRenderer(maximumShore)
    for (let t = 0; t < 7.1; t += .1) {
      const count = maximumRender(t).filter((d) => d.type === 'stroke').length
      assert.ok(count < 1500, 'creator maximum six-hit recipe keeps the fixed draw budget')
      maxStrokes = Math.max(maxStrokes, count)
    }
    const invalidFrame = recordedRenderer(rain)
    for (const t of [NaN, Infinity, -Infinity]) assert.deepEqual(invalidFrame(t), [], 'invalid direct-render time fails without canvas work')
  } finally { Math.random = originalMathRandom }

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
  const beforeMalformed = [resizers.length, intersections.length, pending.size, image.count(), window.count(), document.count()]
  for (const malformed of [null, [], {}, { ...rain, areas: null }, { ...shore, bank: 'not points' }, { ...shore, hits: [null] }]) {
    assert.doesNotThrow(() => startEnvironmentMotion(image, canvas, viewport, malformed)())
    assert.equal(canvas.hidden, true, 'malformed external recipe remains static')
  }
  assert.deepEqual([resizers.length, intersections.length, pending.size, image.count(), window.count(), document.count()], beforeMalformed,
    'malformed recipes allocate no observers, listeners or frames')
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
  // Inline reading encounters are finite and not resumed like an expanded
  // opt-in. Hidden/failed/offscreen/end releases every DOM hook immediately.
  for (const end of ['finite', 'offscreen', 'reduced', 'hidden', 'error', 'slow-load-exit']) {
    let first=0
    image.complete=end!=='slow-load-exit'
    const cleanup=startEnvironmentMotion(image,canvas,viewport,shore,()=>first++,undefined,undefined,'inline-once')
    intersect(true);tick(100)
    assert.equal(first,image.complete?1:0)
    if(end==='finite')tick(8101)
    if(end==='offscreen'||end==='slow-load-exit')intersect(false)
    if(end==='error')image.emit('error')
    if(end==='reduced'){media.matches=true;media.emit('change')}
    if(end==='hidden'){document.hidden=true;document.emit('visibilitychange')}
    assert.equal(canvas.hidden,true,end+' returns to base image')
    assert.equal(pending.size,0,end+' leaves no animation frame')
    for(const e of [image,document,window,media])assert.equal(e.count(),0,end+' releases all listeners')
    for(const o of [...resizers,...intersections])assert.equal(o.targets.size,0,end+' releases observers')
    document.hidden=false;media.matches=false;image.complete=true;image.emit('load');intersect(true)
    assert.equal(pending.size,0,end+' cannot trigger a late replay')
    cleanup()
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
  const plateView = fs.readFileSync(path.join(root, 'frontend/src/reader/ReaderPlate.tsx'), 'utf8')
  assert.match(plateView, /motionArmed && motionSeen && motionRecipe/, 'an eligible recipe alone does not start inline motion')
  assert.ok(!fs.readFileSync(path.join(root, 'frontend/src/reader/ReaderContents.tsx'), 'utf8').includes('ReaderPlateMotion'), 'contents and gallery thumbnails do not animate')
  assert.ok(!app.includes('wave-impact-backwash') && !app.includes('rain-wet-ground'), 'no story-specific renderer branches in ReaderApp')
  console.log(`Reader motion: exact edition/image binding, generic arrival UUIDs, arbitrary polygon-local deterministic particles, explicit-ground causal rain contact/ripples and masked shore spray, finite bounded recipes/rendering (max ${maxStrokes} strokes/frame), contain geometry, static fallbacks and repeated lifecycle cleanup passed.`)
} finally {
  for (const [name, value] of Object.entries(saved)) if (value === undefined) delete global[name]; else global[name] = value
  fs.rmSync(temp, { recursive: true, force: true })
}
