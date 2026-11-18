import type { IllustrationMotion, ReaderContent, ReaderIllustration } from '../../reader-types'

export type Point = readonly [number, number]
export type Polygons = readonly (readonly Point[])[]
type Binding = {
  id: string
  canonicalHash: string
  plateId: string
  /** The reviewed source boundary, required for automatic presentation. */
  afterByte?: number
  imageAsset?: string
  imageHash: string
  normalizedImageHashes?: readonly string[]
  width: number
  height: number
}
export type ShoreRecipe = Binding & {
  effect: 'wave-impact-backwash'
  water: Polygons
  bank: readonly Point[]
  hits: readonly { x: number; phase: number; length: number; gain: number }[]
}
export type RainRecipe = Binding & {
  effect: 'rain-wet-ground'
  areas: Polygons
  ground?: Polygons
  drops: number
  rings: number
}
export type EnvironmentMotionRecipe = ShoreRecipe | RainRecipe

// Render-only, image-version-local recipes. No executable strings, URLs, global
// camera motion or arbitrary imported effect parameters. Regions were placed on
// these exact 1672 × 941 originals in the private shore/weather studies.
const bank = [
  [0.1, 1],
  [0.16, 0.942],
  [0.22, 0.896],
  [0.275, 0.851],
  [0.33, 0.802],
  [0.382, 0.763],
  [0.428, 0.722],
  [0.475, 0.689],
  [0.525, 0.657],
  [0.585, 0.627],
  [0.63, 0.607],
  [0.656, 0.601],
] as const
export const environmentMotionRecipes: readonly EnvironmentMotionRecipe[] = [
  {
    id: 'river-overlook-shore-v1',
    canonicalHash: 'ad97df377de9a9f5f2680253666ec6d9a6d2b8be055ee94a92643a4b16043341',
    plateId: 'river-overlook',
    afterByte: 63,
    imageAsset: 'da59592b-3675-45ae-aefe-867b01d0a2e3',
    imageHash: 'e615364cdee1f0fad4236afbf44aa1d5b0bd338cba14acaa01c2cf2506042c07',
    width: 1672,
    height: 941,
    effect: 'wave-impact-backwash',
    bank,
    water: [[[0, 0.505], [0.66, 0.495], ...bank.slice().reverse(), [0, 1]]],
    hits: [
      { x: 0.235, phase: 0.01, length: 7.1, gain: 1.22 },
      { x: 0.354, phase: 0.51, length: 7.1, gain: 1.07 },
      { x: 0.467, phase: 1.23, length: 7.1, gain: 0.71 },
      { x: 0.542, phase: 1.79, length: 7.1, gain: 0.48 },
    ],
  },
  {
    id: 'arrival-rain-v1',
    canonicalHash: '1b2e65bfef863fa666d525aae620793d72038e0442ae4bb5a88f2e12ddbd5880',
    plateId: 'plan-arrival',
    afterByte: 526,
    // The generic pack builder assigns upload UUIDs afresh. Exact source,
    // applied plate ID and image SHA bind this recipe across valid imports.
    imageHash: '556de6cf96af3220dab851317af0bc2e6d290034d17b0a23ddc9575d45905145',
    // Reader.upload re-encodes RGB pixels as PNG. Bind only the exact known
    // Linux/macOS encoder outputs, never arbitrary dimensions or filename.
    normalizedImageHashes: [
      '7bd8cc49a2a3dd412c876d6b20063c2496f2db4289a51937fa206e8c1060318f',
      '2dc65d6e43f987fdb4b908e43fb34fb37f66aaf8c271d21f6b40ea5658c4ddec',
    ],
    width: 1672,
    height: 941,
    effect: 'rain-wet-ground',
    drops: 98,
    rings: 12,
    // Explicit wet platform only. Never infer ground from the lower image half.
    ground: [
      [
        [0.793, 0.691],
        [0.815, 0.701],
        [0.898, 0.965],
        [0.89, 0.99],
        [0.792, 0.99],
      ],
    ],
    areas: [
      [
        [0.576, 0.257],
        [0.718, 0.193],
        [0.715, 0.665],
        [0.667, 0.655],
        [0.672, 0.493],
        [0.674, 0.392],
        [0.638, 0.342],
      ],
      [
        [0.755, 0.178],
        [0.786, 0.171],
        [0.787, 0.592],
        [0.761, 0.64],
      ],
      [
        [0.806, 0.216],
        [0.829, 0.18],
        [0.871, 0.152],
        [0.903, 0.131],
        [0.947, 0.057],
        [0.975, 0],
        [1, 0],
        [1, 1],
        [0.943, 1],
        [0.889, 0.797],
        [0.812, 0.69],
      ],
    ],
  },
]

export const sha256 = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
export const bounded = (n: unknown, min: number, max: number): n is number =>
  typeof n === 'number' && Number.isFinite(n) && n >= min && n <= max
export const point = (p: unknown): p is Point =>
  Array.isArray(p) && p.length === 2 && p.every((n) => bounded(n, 0, 1))
const cross = (a: Point, b: Point, c: Point) =>
  (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
const onSegment = (a: Point, b: Point, c: Point) =>
  Math.abs(cross(a, b, c)) < 1e-10 &&
  c[0] >= Math.min(a[0], b[0]) - 1e-10 &&
  c[0] <= Math.max(a[0], b[0]) + 1e-10 &&
  c[1] >= Math.min(a[1], b[1]) - 1e-10 &&
  c[1] <= Math.max(a[1], b[1]) + 1e-10
const intersects = (a: Point, b: Point, c: Point, d: Point) => {
  const abC = cross(a, b, c),
    abD = cross(a, b, d),
    cdA = cross(c, d, a),
    cdB = cross(c, d, b)
  return (
    (abC * abD < 0 && cdA * cdB < 0) ||
    onSegment(a, b, c) ||
    onSegment(a, b, d) ||
    onSegment(c, d, a) ||
    onSegment(c, d, b)
  )
}
export function maskContainsPoint(p: Point, polygon: readonly Point[]): boolean {
  let inside = false
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[j],
      b = polygon[i]
    if (onSegment(a, b, p)) return true
    if (
      a[1] > p[1] !== b[1] > p[1] &&
      p[0] < ((b[0] - a[0]) * (p[1] - a[1])) / (b[1] - a[1]) + a[0]
    )
      inside = !inside
  }
  return inside
}
export function masksOverlap(a: Polygons, b: Polygons): boolean {
  return a.some((p) =>
    b.some(
      (q) =>
        p.some((point) => maskContainsPoint(point, q)) ||
        q.some((point) => maskContainsPoint(point, p)) ||
        p.some((v, i) =>
          q.some((w, j) => intersects(v, p[(i + 1) % p.length], w, q[(j + 1) % q.length])),
        ),
    ),
  )
}
/** Simple masks only: no zero-area polygons, overlapping edges or self crossings. */
export function simplePolygon(value: unknown): value is readonly Point[] {
  if (!Array.isArray(value) || value.length < 3 || value.length > 64 || !value.every(point))
    return false
  const p: Point[] = value
  let area = 0
  for (let i = 0; i < p.length; i++) {
    const a = p[i],
      b = p[(i + 1) % p.length]
    if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-8) return false
    const prev = p[(i + p.length - 1) % p.length]
    if (
      Math.abs(cross(prev, a, b)) <= 1e-10 &&
      (a[0] - prev[0]) * (b[0] - a[0]) + (a[1] - prev[1]) * (b[1] - a[1]) < 0
    )
      return false
    area += a[0] * b[1] - b[0] * a[1]
    for (let j = i + 1; j < p.length; j++) {
      if (j === i + 1 || (i === 0 && j === p.length - 1)) continue
      if (intersects(a, b, p[j], p[(j + 1) % p.length])) return false
    }
  }
  return Math.abs(area) > 1e-8
}
export const polygons = (areas: unknown): areas is Polygons =>
  Array.isArray(areas) && areas.length > 0 && areas.length <= 8 && areas.every(simplePolygon)

/** A bounded runtime guard, including malformed data in hand-edited static packages. */
export function validMotionRecipe(value: unknown): value is EnvironmentMotionRecipe {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const r = value as Record<string, unknown>
  if (
    !sha256(r.canonicalHash) ||
    !sha256(r.imageHash) ||
    typeof r.id !== 'string' ||
    !r.id ||
    typeof r.plateId !== 'string' ||
    !r.plateId ||
    (r.imageAsset !== undefined && typeof r.imageAsset !== 'string') ||
    (r.normalizedImageHashes !== undefined &&
      (!Array.isArray(r.normalizedImageHashes) ||
        r.normalizedImageHashes.length > 2 ||
        !r.normalizedImageHashes.every(sha256))) ||
    !bounded(r.width, 1, 8192) ||
    !Number.isInteger(r.width) ||
    !bounded(r.height, 1, 8192) ||
    !Number.isInteger(r.height) ||
    r.width * r.height > 24000000
  )
    return false
  if (r.effect === 'rain-wet-ground')
    return (
      polygons(r.areas) &&
      (r.ground === undefined ||
        (Array.isArray(r.ground) && r.ground.length <= 8 && r.ground.every(simplePolygon))) &&
      Number.isInteger(r.drops) &&
      bounded(r.drops, 1, 128) &&
      Number.isInteger(r.rings) &&
      bounded(r.rings, 0, 16)
    )
  if (
    r.effect !== 'wave-impact-backwash' ||
    !polygons(r.water) ||
    !Array.isArray(r.bank) ||
    r.bank.length < 2 ||
    r.bank.length > 64 ||
    !r.bank.every(point)
  )
    return false
  const bank: Point[] = r.bank
  if (
    !bank.every((p, i) => !i || p[0] > bank[i - 1][0]) ||
    !Array.isArray(r.hits) ||
    !r.hits.length ||
    r.hits.length > 6
  )
    return false
  return r.hits.every(
    (h) =>
      h &&
      typeof h === 'object' &&
      !Array.isArray(h) &&
      Object.keys(h).length === 4 &&
      Object.keys(h).every((k) => ['x', 'phase', 'length', 'gain'].includes(k)) &&
      bounded(h.x, bank[0][0], bank.at(-1)![0]) &&
      bounded(h.phase, 0, 8) &&
      bounded(h.length, 6.5, 20) &&
      bounded(h.gain, 0, 1.3),
  )
}

// Standalone readers receive bindings and geometry, never the private author notebook.
type RenderOnly<T> = T extends unknown
  ? Omit<T, 'evidence' | 'note'> & { playback_only: true }
  : never
type PlaybackMotion = RenderOnly<IllustrationMotion>

/** Convert only declarative, bounded image-local parameters. No arbitrary scripts/URLs. */
export function directionRecipe(
  motion: IllustrationMotion | PlaybackMotion,
  plateId: string,
): EnvironmentMotionRecipe {
  const binding = {
    id: 'directed-' + plateId,
    plateId,
    afterByte: motion.after_byte,
    canonicalHash: motion.source_sha256,
    imageHash: motion.image_sha256,
    width: motion.width,
    height: motion.height,
  }
  return motion.effect === 'rain-wet-ground'
    ? {
        ...binding,
        effect: motion.effect,
        areas: motion.areas,
        ground: motion.ground,
        drops: motion.drops,
        rings: motion.rings,
      }
    : {
        ...binding,
        effect: motion.effect,
        water: motion.water,
        bank: motion.bank,
        hits: motion.hits,
      }
}
export function validIllustrationMotion(value: unknown): value is IllustrationMotion {
  return validDirection(value, false)
}
function validPlaybackMotion(value: unknown): value is PlaybackMotion {
  return validDirection(value, true)
}
function validDirection(value: unknown, playback: boolean): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const m = value as Record<string, unknown>
  const base = [
    'version',
    'effect',
    'image_sha256',
    'source_sha256',
    'after_byte',
    'width',
    'height',
    ...(playback ? ['playback_only'] : ['evidence', 'note']),
    'reviewed',
  ]
  const keys = [
    ...base,
    ...(m.effect === 'rain-wet-ground'
      ? ['areas', 'ground', 'drops', 'rings']
      : ['water', 'bank', 'hits']),
  ]
  if (
    Object.keys(m).length !== keys.length ||
    Object.keys(m).some((k) => !keys.includes(k)) ||
    m.version !== 1 ||
    typeof m.reviewed !== 'boolean' ||
    !bounded(m.after_byte, 0, Number.MAX_SAFE_INTEGER) ||
    !Number.isInteger(m.after_byte) ||
    (playback && (m.playback_only !== true || m.reviewed !== true)) ||
    (!playback &&
      !['evidence', 'note'].every(
        (k) =>
          typeof m[k] === 'string' &&
          [...(m[k] as string)].length <= 300 &&
          [...(m[k] as string).replace(/[\s\u001c-\u001f\u0085]/gu, '')].length >= 8,
      ))
  )
    return false
  if (
    m.effect === 'rain-wet-ground' &&
    (!Array.isArray(m.ground) ||
      m.ground.length > 8 ||
      !m.ground.every(simplePolygon) ||
      (Number(m.rings) > 0 && !m.ground.length))
  )
    return false
  return validMotionRecipe(directionRecipe(m as IllustrationMotion, 'authored'))
}

/** Missing/legacy SHA metadata fails closed. Never infer a recipe from a title. */
export function resolveEnvironmentMotion(
  data: ReaderContent,
  plate: ReaderIllustration | undefined,
  recipes: readonly EnvironmentMotionRecipe[] = environmentMotionRecipes,
): EnvironmentMotionRecipe | null {
  if (!plate || data.config.illustrations?.filter((p) => p.id === plate.id).length !== 1)
    return null
  const asset = data.media[plate.image_asset_id]
  if (!asset || asset.type !== 'image' || asset.id !== plate.image_asset_id) return null
  // Explicit static or an unreviewed/invalid authored draft must never fall back to a demo.
  if (Object.prototype.hasOwnProperty.call(plate, 'motion')) {
    const m = plate.motion
    if (
      (!validIllustrationMotion(m) && !validPlaybackMotion(m)) ||
      !m.reviewed ||
      m.after_byte !== plate.after_byte ||
      m.source_sha256 !== data.project.canonical_sha256 ||
      m.image_sha256 !== asset.sha256 ||
      m.width !== asset.width ||
      m.height !== asset.height
    )
      return null
    return directionRecipe(m, plate.id)
  }
  return (
    recipes.find(
      (r) =>
        validMotionRecipe(r) &&
        r.canonicalHash === data.project.canonical_sha256 &&
        r.plateId === plate.id &&
        (!r.imageAsset || r.imageAsset === asset.id) &&
        (r.imageHash === asset.sha256 || r.normalizedImageHashes?.includes(asset.sha256)),
    ) || null
  )
}

/** Reading-time presentation is more conservative than explicit manual inspection. */
export function resolveReadingMotion(
  data: ReaderContent,
  plate: ReaderIllustration,
): EnvironmentMotionRecipe | null {
  const recipe = resolveEnvironmentMotion(data, plate)
  if (!recipe || recipe.afterByte !== plate.after_byte) return null
  const asset = data.media[plate.image_asset_id]
  // Workbench preview exposes status (and may contain pending artwork); strict
  // published editions intentionally omit authoring state after validating it.
  const status = 'status' in asset ? asset.status : undefined
  if (status !== 'accepted' && (status !== undefined || data.preview !== false)) return null
  if (
    recipe.width !== asset.width ||
    recipe.height !== asset.height ||
    data.blocks.filter((b) => b.byte_end === plate.after_byte).length !== 1
  )
    return null
  if (
    plate.motion &&
    'evidence' in plate.motion &&
    !data.blocks.some(
      (b) => b.byte_end <= plate.after_byte && b.text.includes(plate.motion!.evidence),
    )
  )
    return null
  return recipe
}
