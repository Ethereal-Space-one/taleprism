import type { EnvironmentMotionRecipe, Point, Polygons, ShoreRecipe } from './recipes'

const mix = (a: number, b: number, t: number) => a + (b - a) * t
const clamp = (v: number) => Math.max(0, Math.min(1, v))
const smooth = (a: number, b: number, x: number) => {
  const f = clamp((x - a) / (b - a))
  return f * f * (3 - 2 * f)
}
const wave = (t: number, phase = 0) => 0.5 + 0.5 * Math.sin(t + phase)
const noise = (n: number) => {
  const x = Math.sin(n * 147.131 + 83.27) * 43758.5453
  return x - Math.floor(x)
}

type Region = {
  points: readonly Point[]
  minX: number
  maxX: number
  minY: number
  maxY: number
  area: number
}

// All geometry work is bounded by the validated recipe's 8 × 64 vertices.
// Normalize winding so overlapping creator polygons mean a union, not holes.
function maskRegions(polys: Polygons): Region[] {
  return polys.flatMap((points) => {
    const area = points.reduce((sum, [x, y], i) => {
      const next = points[(i + 1) % points.length]
      return sum + x * next[1] - next[0] * y
    }, 0)
    if (!Number.isFinite(area) || !area) return []
    return [
      {
        points: area < 0 ? points.slice().reverse() : points,
        minX: Math.min(...points.map(([x]) => x)),
        maxX: Math.max(...points.map(([x]) => x)),
        minY: Math.min(...points.map(([, y]) => y)),
        maxY: Math.max(...points.map(([, y]) => y)),
        area: Math.abs(area) / 2,
      },
    ]
  })
}

/** Exact interior runs along a horizontal or vertical line; no rejection loop. */
function runs(points: readonly Point[], at: number, vertical = false) {
  const crossings: number[] = []
  for (let i = 0; i < points.length; i++) {
    const a = points[i],
      b = points[(i + 1) % points.length]
    const axis = vertical ? 0 : 1,
      other = vertical ? 1 : 0
    if ((a[axis] <= at && at < b[axis]) || (b[axis] <= at && at < a[axis]))
      crossings.push(mix(a[other], b[other], (at - a[axis]) / (b[axis] - a[axis])))
  }
  crossings.sort((a, b) => a - b)
  const result: [number, number][] = []
  for (let i = 1; i < crossings.length; i += 2)
    if (crossings[i] > crossings[i - 1]) result.push([crossings[i - 1], crossings[i]])
  return result
}

function contains(regions: readonly Region[], x: number, y: number) {
  return regions.some((r) => {
    if (x < r.minX || x > r.maxX || y < r.minY || y > r.maxY) return false
    let inside = false
    for (let i = 0; i < r.points.length; i++) {
      const [ax, ay] = r.points[i],
        [bx, by] = r.points[(i + 1) % r.points.length]
      if (
        Math.abs((x - ax) * (by - ay) - (y - ay) * (bx - ax)) < 1e-12 &&
        x >= Math.min(ax, bx) &&
        x <= Math.max(ax, bx) &&
        y >= Math.min(ay, by) &&
        y <= Math.max(ay, by)
      )
        return true
      if (ay > y !== by > y && x < ax + ((y - ay) * (bx - ax)) / (by - ay)) inside = !inside
    }
    return inside
  })
}

function clearance(points: readonly Point[], x: number, y: number) {
  return Math.min(
    ...points.map(([ax, ay], i) => {
      const [bx, by] = points[(i + 1) % points.length]
      const length = (bx - ax) ** 2 + (by - ay) ** 2
      const t = length ? clamp(((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / length) : 0
      return Math.hypot(x - mix(ax, bx, t), y - mix(ay, by, t))
    }),
  )
}

/** Canvas-only animation. No React state, source-image writes, network or storage. */
export function createMotionRenderer(
  ctx: CanvasRenderingContext2D,
  recipe: EnvironmentMotionRecipe,
) {
  let width = 1
  let seed = 4071
  const random = () => (seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296
  const regions = maskRegions(recipe.effect === 'rain-wet-ground' ? recipe.areas : recipe.water)
  const sample = (source: readonly Region[], allowed?: readonly Region[]) => {
    let weight = random() * source.reduce((sum, r) => sum + r.area, 0)
    const region = source.find((r) => (weight -= r.area) <= 0) || source.at(-1)
    if (!region) return null
    const y = mix(region.minY, region.maxY, 0.04 + random() * 0.92)
    let spans = runs(region.points, y)
    if (allowed) {
      const permitted = allowed.flatMap((r) => runs(r.points, y))
      spans = spans.flatMap(([a, b]) =>
        permitted.flatMap(([c, d]): [number, number][] =>
          Math.max(a, c) < Math.min(b, d) ? [[Math.max(a, c), Math.min(b, d)]] : [],
        ),
      )
    }
    let distance = random() * spans.reduce((sum, [a, b]) => sum + b - a, 0)
    const span = spans.find(([a, b]) => (distance -= b - a) <= 0)
    return span ? { region, x: mix(span[0], span[1], 0.08 + random() * 0.84), y } : null
  }
  const fallRun = (region: Region, x: number, y: number) => {
    const u = x + y * 0.083
    const tilted = region.points.map(([px, py]): Point => [px + py * 0.083, py])
    const span = runs(tilted, u, true).find(([a, b]) => y >= a && y <= b)
    return span ? { u, low: span[0], high: span[1] } : null
  }
  const ground = recipe.effect === 'rain-wet-ground' ? maskRegions(recipe.ground || []) : []
  const contactCount =
    recipe.effect === 'rain-wet-ground' && ground.length ? Math.min(recipe.drops, recipe.rings) : 0
  const contacts = Array.from({ length: contactCount }, (_, i) => {
    // Exact horizontal interval intersections, with a fixed retry limit for
    // disjoint/partially overlapping ground. No inferred lower-image wet area.
    for (let attempt = 0; attempt < 16; attempt++) {
      const p = sample(ground, regions)
      if (!p) continue
      const region = regions.find((r) => contains([r], p.x, p.y))
      if (!region) continue
      const run = fallRun(region, p.x, p.y)
      if (!run || p.y - run.low <= 1e-10) continue
      return {
        ...run,
        x: p.x,
        y: p.y,
        phase: i / contactCount,
        length: Math.min(0.015 + random() * 0.033, (p.y - run.low) * 0.35),
        alpha: 0.12 + random() * 0.5,
        size: Math.min(
          0.004 + random() * 0.011,
          clearance(p.region.points, p.x, p.y) / 1.31,
          clearance(region.points, p.x, p.y) / 1.31,
        ),
      }
    }
    return null
  }).filter((p) => p !== null)
  // Each drop follows a complete slanted interior run of its own polygon.
  // A tiny/left/top mask therefore gets real falling streaks, not clipped work
  // generated elsewhere in the image. Particle randomness is initialization-only.
  const drops = Array.from(
    { length: recipe.effect === 'rain-wet-ground' ? recipe.drops - contacts.length : 0 },
    () => {
      const p = sample(regions)
      if (!p) return null
      const run = fallRun(p.region, p.x, p.y)
      return run
        ? {
            ...run,
            phase: random(),
            speed: 0.18 + random() * 0.32,
            length: Math.min(0.015 + random() * 0.033, (run.high - run.low) * 0.35),
            alpha: 0.12 + random() * 0.5,
          }
        : null
    },
  ).filter((p) => p !== null)
  function clip(mask: readonly Region[] = regions) {
    ctx.beginPath()
    for (const { points } of mask) {
      points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
      ctx.closePath()
    }
    ctx.clip()
  }
  function soft(x: number, y: number, rx: number, ry: number, rgb: string, a: number) {
    if (a <= 0 || rx <= 0 || ry <= 0) return
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(rx, ry)
    const g = ctx.createRadialGradient(0, 0, 0, 0, 0, 1)
    g.addColorStop(0, `rgba(${rgb},${clamp(a)})`)
    g.addColorStop(0.52, `rgba(${rgb},${clamp(a * 0.66)})`)
    g.addColorStop(1, `rgba(${rgb},0)`)
    ctx.fillStyle = g
    ctx.fillRect(-1, -1, 2, 2)
    ctx.restore()
  }
  function line(x: number, y: number, x2: number, y2: number, rgb: string, a: number, w: number) {
    ctx.strokeStyle = `rgba(${rgb},${clamp(a)})`
    ctx.lineWidth = w / width
    ctx.beginPath()
    ctx.moveTo(x, y)
    ctx.lineTo(x2, y2)
    ctx.stroke()
  }
  function rain(t: number) {
    if (recipe.effect !== 'rain-wet-ground') return
    ctx.save()
    clip()
    ctx.lineCap = 'round'
    drops.forEach((d, i) => {
      const f = (((d.phase + t * d.speed) % 1) + 1) % 1
      const y = mix(d.low, d.high, f),
        end = Math.min(d.high, y + d.length)
      line(
        d.u - y * 0.083,
        y,
        d.u - end * 0.083,
        end,
        '218,233,239',
        d.alpha * 0.98,
        i % 6 === 0 ? 1.35 : 0.75,
      )
    })
    for (const { u, low, y, phase, length, alpha } of contacts) {
      const f = (((t * 0.73 + phase) % 1) + 1) % 1
      const contact = 0.46
      // The same drop first reaches this explicitly wet endpoint, then becomes
      // its ripple. A single phase prevents unrelated/floating ground rings.
      if (f <= contact + 1e-12) {
        const head = mix(low, y, Math.min(1, f / contact)),
          tail = Math.max(low, head - length)
        line(u - tail * 0.083, tail, u - head * 0.083, head, '218,233,239', alpha * 0.98, 0.9)
      }
    }
    if (contacts.length) {
      ctx.save()
      clip(ground)
      for (const { x, y, phase, size } of contacts) {
        const f = (((t * 0.73 + phase) % 1) + 1) % 1
        if (f < 0.46 - 1e-12) continue
        const ripple = Math.max(0, (f - 0.46) / 0.54)
        ctx.strokeStyle = `rgba(211,226,224,${(1 - ripple) * 0.33})`
        ctx.lineWidth = 0.86 / width
        ctx.beginPath()
        ctx.ellipse(x, y, size * (0.3 + ripple), size * (0.16 + ripple * 0.24), 0, 0, Math.PI * 2)
        ctx.stroke()
      }
      ctx.restore()
    }
    ctx.restore()
  }
  // A shoreline's local water depth and width scale the fixed phase model.
  // No absolute image position is special. The mask includes all allowed spray.
  const waterline = (x: number, r: ShoreRecipe) => {
    if (x <= r.bank[0][0]) return r.bank[0][1]
    for (let i = 1; i < r.bank.length; i++) {
      const [x0, y0] = r.bank[i - 1],
        [x1, y1] = r.bank[i]
      if (x <= x1) return mix(y0, y1, (x - x0) / (x1 - x0))
    }
    return r.bank.at(-1)![1]
  }
  const column = (x: number, r: ShoreRecipe) => {
    const bankY = waterline(x, r)
    let best: {
      x: number
      y: number
      direction: number
      scale: number
      region: Region
      distance: number
    } | null = null
    for (const region of regions) {
      if (x < region.minX || x >= region.maxX) continue
      for (const [low, high] of runs(region.points, x, true)) {
        if (bankY < low - 1e-12 || bankY > high + 1e-12) continue
        const y = Math.max(low, Math.min(high, bankY))
        const distance = Math.abs(y - bankY)
        if (best && distance >= best.distance) continue
        const direction = y - low >= high - y ? -1 : 1
        const depth = direction < 0 ? y - low : high - y
        best = { x, y, direction, scale: Math.min(1, (depth * 0.86) / 0.22), region, distance }
      }
    }
    return best
  }
  const shoreHits =
    recipe.effect === 'wave-impact-backwash'
      ? recipe.hits.flatMap((h, i) => {
          // Preserve the authored contact line. An unrelated/off-mask bank is
          // not relocated to the nearest allowed polygon or image boundary.
          const anchor = column(h.x, recipe)
          if (!anchor) return []
          const sx = Math.min(
            1,
            (anchor.region.maxX - anchor.region.minX) / 0.24,
            (recipe.bank.at(-1)![0] - recipe.bank[0][0]) / 0.28,
            (Math.min(anchor.x - anchor.region.minX, anchor.region.maxX - anchor.x) * 2) / 0.25,
          )
          const span = (0.052 + h.gain * 0.016) * 1.04
          const waves = Array.from({ length: 87 }, (_, index) => {
            const j = Math.floor(index / 29),
              k = index % 29,
              n = noise(i * 139 + j * 72 + k)
            const x = anchor.x + ((k / 29 - 0.5) * span * 2 + (n - 0.5) * 0.011) * sx
            return { j, k, n, col: column(x, recipe) }
          })
          const spray = Array.from({ length: i === 0 ? 81 : i === 1 ? 60 : 38 }, (_, j) => {
            const n = noise(j + i * 86),
              q = noise(j * 1.74 + 17),
              z = noise(j * 3.13 + i)
            return { j, q, z, col: column(anchor.x + (n - 0.5) * 0.076 * sx, recipe) }
          })
          const backwash = Array.from({ length: 92 }, (_, j) => {
            const n = noise(j + i * 179),
              q = noise(j * 1.71 + i + 5),
              z = noise(j * 2.17 + i + 9)
            return { j, n, q, z, col: column(anchor.x + (n - 0.5) * 0.176 * sx, recipe) }
          })
          return [{ h, i, sx, waves, spray, backwash }]
        })
      : []
  function waterLine(...args: Parameters<typeof line>) {
    const [x, y, x2, y2] = args
    // Do not submit repeatedly clipped-away particles. The canvas clip remains
    // authoritative for stroke width and segments across concave mask edges.
    if (
      contains(regions, x, y) &&
      contains(regions, x2, y2) &&
      contains(regions, (x + x2) / 2, (y + y2) / 2)
    )
      line(...args)
  }
  function waterSoft(...args: Parameters<typeof soft>) {
    if (contains(regions, args[0], args[1])) soft(...args)
  }
  function shore(t: number) {
    ctx.lineCap = 'round'
    ctx.save()
    clip()
    for (const { h, i, sx, waves, spray, backwash } of shoreHits) {
      if (!h.gain) continue
      // One shared phase drives approach, rupture and return.
      const p = (((t + 2.12 - h.phase) % h.length) + h.length) % h.length
      const reach =
        p < 1.81 ? mix(0.158, 0.004, smooth(0, 1.81, p)) : mix(0.004, 0.108, smooth(2.12, 6.45, p))
      const energy =
        (0.22 + 0.66 * smooth(0.29, 1.82, p)) * (1 - 0.86 * smooth(2.04, 4.43, p)) * h.gain
      for (const { j, k, n, col } of waves) {
        if (!col) continue
        const { x, direction: d, scale: sy } = col
        const taper = 1 - Math.pow(Math.abs((k / 29) * 2 - 1), 1.6)
        const y =
          col.y +
          d *
            sy *
            (reach +
              j * 0.018 -
              0.009 * Math.sin(x * 87 + p * 2 + i) -
              0.005 * Math.sin(x * 197 + p * 3 - i) -
              0.006 * Math.sin(k * 2.3 + j * 1.4))
        const a = energy * taper * (0.27 + n * 0.68) * (j === 0 ? 1 : 0.65 / (j + 0.45))
        if (j === 0 && k % 5 === 0)
          waterSoft(x, y - d * 0.012 * sy, 0.023 * sx, 0.024 * sy, '72,123,151', a * 0.56)
        waterLine(
          x,
          y,
          x + (0.003 + n * 0.011) * sx,
          y - d * (0.47 - n) * 0.009 * sy,
          j === 0 ? '205,232,233' : '99,167,181',
          a,
          (j === 0 ? 1.2 : 0.9) + n * 1.55,
        )
        if (j === 0 && k % 2 === 0)
          waterLine(
            x + 0.003 * sx,
            y + d * 0.008 * sy,
            x + 0.015 * sx,
            y + d * 0.019 * sy,
            '179,213,221',
            a * 0.62,
            1.15 + n,
          )
      }
      const impact = p - 1.78
      if (impact >= 0 && impact <= 1.26) {
        const gate = smooth(0, 0.105, impact) * (1 - smooth(0.47, 1.26, impact))
        for (const { j, q, z, col } of spray) {
          if (!col) continue
          const local = impact - q * 0.16
          if (local < 0) continue
          const { direction: d, scale: sy } = col
          const swell = (0.072 + 0.131 * z) * h.gain,
            drift = ((q - 0.43) * 0.092 - 0.034) * sx
          const x = col.x + local * drift,
            y = col.y + d * sy * (0.004 + local * swell - local * local * 0.145)
          if (d * (y - col.y) < -0.009 * sy) continue
          const speed = (swell - 0.29 * local) * d * sy
          const a = gate * (0.28 + z * 0.55) * (1 - 0.34 * smooth(0.26, 0.83, local)) * h.gain
          if (j % 6 === 0)
            waterSoft(
              x,
              y,
              (0.006 + z * 0.009) * sx,
              (0.009 + z * 0.011) * sy,
              '206,233,230',
              a * 0.63,
            )
          waterLine(
            x,
            y,
            x + drift * 0.093,
            y + speed * 0.076,
            j % 4 ? '226,246,242' : '165,217,227',
            a,
            1 + z * 1.95,
          )
        }
      }
      const elapsed = p - 1.76
      if (elapsed >= 0 && elapsed <= 5.18) {
        const e = smooth(0, 0.27, elapsed) * (1 - smooth(1.55, 5.18, elapsed)) * h.gain
        for (const { j, q, z, col } of backwash) {
          if (!col) continue
          const { direction: d, scale: sy } = col
          const slack = elapsed * (0.011 + 0.013 * q)
          const x = col.x - slack * q * sx
          const y =
            col.y + d * sy * (0.004 + q * (0.024 + slack) - 0.004 * Math.sin(elapsed * 2.7 + j))
          if (j % 11 === 0) waterSoft(x, y, 0.018 * sx, 0.013 * sy, '184,221,226', e * 0.21)
          waterLine(
            x,
            y,
            x + (0.002 + 0.011 * z) * sx,
            y - d * (0.46 - z) * 0.008 * sy,
            '221,241,235',
            e * (0.19 + 0.42 * wave(x * 102 + elapsed * 1.5, j * 0.012)) * (0.37 + z * 0.61),
            0.68 + z * 1.35,
          )
        }
      }
    }
    ctx.restore()
  }
  return (seconds: number, w: number, h: number) => {
    if (![seconds, w, h].every(Number.isFinite) || w <= 0 || h <= 0) return
    width = w
    ctx.clearRect(0, 0, w, h)
    ctx.save()
    ctx.scale(w, h)
    if (recipe.effect === 'rain-wet-ground') rain(seconds)
    else shore(seconds)
    ctx.restore()
  }
}
