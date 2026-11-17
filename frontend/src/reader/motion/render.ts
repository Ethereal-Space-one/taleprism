import type { EnvironmentMotionRecipe, Polygons, ShoreRecipe } from './recipes'

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

/** Canvas-only animation. No React state, source-image writes, network or storage. */
export function createMotionRenderer(
  ctx: CanvasRenderingContext2D,
  recipe: EnvironmentMotionRecipe,
) {
  let width = 1
  let seed = 4071
  const random = () => (seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296
  const drops = Array.from(
    { length: recipe.effect === 'rain-wet-ground' ? recipe.drops : 0 },
    () => [
      0.535 + random() * 0.51,
      random(),
      0.18 + random() * 0.32,
      0.015 + random() * 0.033,
      0.12 + random() * 0.5,
    ],
  )
  const rings = Array.from(
    { length: recipe.effect === 'rain-wet-ground' ? recipe.rings : 0 },
    () => [0.804 + random() * 0.1, 0.635 + random() * 0.255, random(), 0.004 + random() * 0.011],
  )
  function clip(polys: Polygons) {
    ctx.beginPath()
    for (const p of polys) {
      p.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
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
    clip(recipe.areas)
    ctx.lineCap = 'round'
    drops.forEach(([px, py, v, l, a], i) => {
      const y = ((py + t * v) % 1.08) - 0.04,
        x = px - (y + 0.03) * 0.083
      line(x, y, x - l * 0.083, y + l, '218,233,239', a * 0.98, i % 6 === 0 ? 1.35 : 0.75)
    })
    for (const [x, y, phase, size] of rings) {
      const f = (t * 0.73 + phase) % 1
      ctx.strokeStyle = `rgba(211,226,224,${(1 - f) * 0.33})`
      ctx.lineWidth = 0.86 / width
      ctx.beginPath()
      ctx.ellipse(x, y, size * (0.3 + f), size * (0.16 + f * 0.24), 0, 0, Math.PI * 2)
      ctx.stroke()
    }
    ctx.restore()
  }
  function shore(t: number, r: ShoreRecipe) {
    const waterline = (x: number) => {
      for (let i = 1; i < r.bank.length; i++)
        if (x <= r.bank[i][0]) {
          const [x0, y0] = r.bank[i - 1],
            [x1, y1] = r.bank[i]
          return mix(y0, y1, (x - x0) / (x1 - x0))
        }
      return r.bank.at(-1)![1]
    }
    const phase = (h: ShoreRecipe['hits'][number]) =>
      (((t + 2.12 - h.phase) % h.length) + h.length) % h.length
    ctx.lineCap = 'round'
    ctx.save()
    clip(r.water)
    for (const [i, h] of r.hits.entries()) {
      const p = phase(h)
      const reach =
        p < 1.81 ? mix(0.158, 0.004, smooth(0, 1.81, p)) : mix(0.004, 0.108, smooth(2.12, 6.45, p))
      const energy =
        (0.22 + 0.66 * smooth(0.29, 1.82, p)) * (1 - 0.86 * smooth(2.04, 4.43, p)) * h.gain
      const span = (0.052 + h.gain * 0.016) * (0.75 + smooth(0, 2.01, p) * 0.42)
      for (let j = 0; j < 3; j++)
        for (let k = 0; k < 29; k++) {
          const n = noise(i * 139 + j * 72 + k),
            x = h.x + (k / 29 - 0.5) * span * 2 + (n - 0.5) * 0.011
          const scale = 1 - Math.pow(Math.abs((k / 29) * 2 - 1), 1.6)
          const y =
            waterline(x) -
            reach -
            j * 0.018 +
            0.009 * Math.sin(x * 87 + p * 2 + i) +
            0.005 * Math.sin(x * 197 + p * 3 - i) +
            0.006 * Math.sin(k * 2.3 + j * 1.4)
          const a = energy * scale * (0.27 + n * 0.68) * (j === 0 ? 1 : 0.65 / (j + 0.45))
          if (j === 0 && k % 5 === 0) soft(x, y + 0.012, 0.023, 0.024, '72,123,151', a * 0.56)
          line(
            x,
            y,
            x + 0.003 + n * 0.011,
            y + (0.47 - n) * 0.009,
            j === 0 ? '205,232,233' : '99,167,181',
            a,
            (j === 0 ? 1.2 : 0.9) + n * 1.55,
          )
          if (j === 0 && k % 2 === 0)
            line(x + 0.003, y - 0.008, x + 0.015, y - 0.019, '179,213,221', a * 0.62, 1.15 + n)
        }
    }
    ctx.restore()
    // One shared phase drives approach, rupture and return. Splash is allowed
    // above the water mask, but still bounded to the local shoreline impact.
    for (const [i, h] of r.hits.entries()) {
      const elapsed = phase(h) - 1.78
      if (elapsed < 0 || elapsed > 1.26) continue
      const gate = smooth(0, 0.105, elapsed) * (1 - smooth(0.47, 1.26, elapsed))
      for (let j = 0; j < (i === 0 ? 81 : i === 1 ? 60 : 38); j++) {
        const n = noise(j + i * 86),
          q = noise(j * 1.74 + 17),
          z = noise(j * 3.13 + i)
        const local = elapsed - q * 0.16
        if (local < 0) continue
        const x0 = h.x + (n - 0.5) * (0.07 + i * 0.003),
          y0 = waterline(x0) - 0.004
        const swell = (0.072 + 0.131 * z) * h.gain,
          drift = (q - 0.43) * 0.092 - 0.034
        const x = x0 + local * drift,
          y = y0 - local * swell + local * local * 0.145
        if (y > waterline(x) + 0.009 || x > 0.648) continue
        const speed = -swell + 0.29 * local
        const a = gate * (0.28 + z * 0.55) * (1 - 0.34 * smooth(0.26, 0.83, local))
        if (j % 6 === 0) soft(x, y, 0.006 + z * 0.009, 0.009 + z * 0.011, '206,233,230', a * 0.63)
        line(
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
    ctx.save()
    clip(r.water)
    for (const [i, h] of r.hits.entries()) {
      const elapsed = phase(h) - 1.76
      if (elapsed < 0 || elapsed > 5.18) continue
      const e = smooth(0, 0.27, elapsed) * (1 - smooth(1.55, 5.18, elapsed)) * h.gain
      for (let j = 0; j < 92; j++) {
        const n = noise(j + i * 179),
          q = noise(j * 1.71 + i + 5),
          z = noise(j * 2.17 + i + 9)
        const slack = elapsed * (0.011 + 0.013 * q)
        const x = h.x + (n - 0.5) * (0.132 + 0.022 * elapsed) - slack * q
        const y = waterline(x) - 0.004 - q * (0.024 + slack) + 0.004 * Math.sin(elapsed * 2.7 + j)
        if (j % 11 === 0) soft(x, y, 0.018, 0.013, '184,221,226', e * 0.21)
        line(
          x,
          y,
          x + 0.002 + 0.011 * z,
          y + (0.46 - z) * 0.008,
          '221,241,235',
          e * (0.19 + 0.42 * wave(x * 102 + elapsed * 1.5, j * 0.012)) * (0.37 + z * 0.61),
          0.68 + z * 1.35,
        )
      }
    }
    ctx.restore()
  }
  return (seconds: number, w: number, h: number) => {
    width = w
    ctx.clearRect(0, 0, w, h)
    ctx.save()
    ctx.scale(w, h)
    if (recipe.effect === 'rain-wet-ground') rain(seconds)
    else shore(seconds, recipe)
    ctx.restore()
  }
}
