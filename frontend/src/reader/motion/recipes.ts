import type { ReaderContent, ReaderIllustration } from '../../reader-types'

export type Point = readonly [number, number]
export type Polygons = readonly (readonly Point[])[]
type Binding = {
  id: string
  canonicalHash: string
  plateId: string
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

const sha256 = (value: string) => /^[a-f0-9]{64}$/.test(value)
const bounded = (n: number, min: number, max: number) => Number.isFinite(n) && n >= min && n <= max
const point = (p: Point) => p.length === 2 && p.every((n) => bounded(n, 0, 1))
const polygons = (areas: Polygons) =>
  areas.length > 0 &&
  areas.length <= 8 &&
  areas.every((p) => p.length >= 3 && p.length <= 64 && p.every(point))

/** Deliberately small declarative vocabulary with fixed renderer work budgets. */
export function validMotionRecipe(recipe: EnvironmentMotionRecipe): boolean {
  if (
    !sha256(recipe.canonicalHash) ||
    !sha256(recipe.imageHash) ||
    (recipe.normalizedImageHashes || []).length > 2 ||
    !(recipe.normalizedImageHashes || []).every(sha256) ||
    !recipe.plateId ||
    !bounded(recipe.width, 1, 8192) ||
    !bounded(recipe.height, 1, 8192)
  )
    return false
  if (recipe.effect === 'rain-wet-ground')
    return (
      polygons(recipe.areas) &&
      Number.isInteger(recipe.drops) &&
      bounded(recipe.drops, 1, 128) &&
      Number.isInteger(recipe.rings) &&
      bounded(recipe.rings, 0, 16)
    )
  if (recipe.effect !== 'wave-impact-backwash') return false
  return (
    polygons(recipe.water) &&
    recipe.bank.length >= 2 &&
    recipe.bank.length <= 64 &&
    recipe.bank.every((p, i) => point(p) && (!i || p[0] > recipe.bank[i - 1][0])) &&
    recipe.hits.length > 0 &&
    recipe.hits.length <= 6 &&
    recipe.hits.every(
      (h) =>
        bounded(h.x, recipe.bank[0][0], recipe.bank.at(-1)![0]) &&
        bounded(h.phase, 0, 8) &&
        bounded(h.length, 6.5, 20) &&
        bounded(h.gain, 0, 1.3),
    )
  )
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
