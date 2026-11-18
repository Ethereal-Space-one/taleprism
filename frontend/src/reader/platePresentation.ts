import type { ReaderContent, ReaderIllustration } from '../reader-types'
import { chibiPlatePresentation } from './graphs/chibiPlatePresentation'

export type PlatePresentation = {
  /** A render-only boundary. Never write it back into the production illustration. */
  displayAfterByte: number
  /** The later of the semantic evidence boundary and the render boundary. */
  disclosureByte: number
  /** Original source position, retained for image bookmarks and reading records. */
  sourceByte: number
  /** Observed image content, distinct from the existing narrative description. */
  visualDescription: string | null
}

export type PlatePresentationRecipe = {
  canonicalHash: string
  plates: {
    id: string
    appliedId?: string
    imageAsset: string
    imageHash: string
    sourceStart: number
    sourceEnd: number
    evidence: string
    visualDescription: string
    displayAfter?: {
      introduction: string
      paragraphs: { start: number; end: number; text: string }[]
    }
  }[]
}

const utf8 = new TextEncoder()

/** Read-only proof shared by the description/poem and shoreline consumers. */
export function verifiedPlateEntry(
  data: ReaderContent,
  plate: ReaderIllustration,
  recipe: PlatePresentationRecipe,
) {
  if (recipe.canonicalHash !== data.project.canonical_sha256) return null
  const entries = recipe.plates.filter((r) => r.id === plate.id || r.appliedId === plate.id)
  if (entries.length !== 1) return null
  const entry = entries[0]
  const same = data.config.illustrations?.filter(
    (p) => p.id === entry.id || p.id === entry.appliedId,
  )
  const asset = data.media[plate.image_asset_id]
  if (
    same?.length !== 1 ||
    same[0].id !== plate.id ||
    plate.after_byte !== entry.sourceEnd ||
    plate.image_asset_id !== entry.imageAsset ||
    asset?.type !== 'image' ||
    asset.id !== entry.imageAsset ||
    asset.sha256 !== entry.imageHash ||
    ('status' in asset && asset.status !== 'accepted')
  )
    return null
  const sources = data.blocks.filter((b) => b.byte_end === entry.sourceEnd)
  if (sources.length !== 1) return null
  const source = sources[0]
  if (
    source.byte_start !== entry.sourceStart ||
    utf8.encode(source.text).length !== source.byte_end - source.byte_start
  )
    return null
  // A citation must occur once within the expected source block, never elsewhere.
  const at = source.text.indexOf(entry.evidence)
  if (
    at < 0 ||
    source.text.indexOf(entry.evidence, at + 1) >= 0 ||
    data.blocks.some((b) => b !== source && b.text.includes(entry.evidence))
  )
    return null
  return entry
}

/**
 * Curated presentation is opt-in for one exact public edition and reviewed image.
 * Source/config/evidence are never rewritten. Unknown or edited plates keep their
 * original placement and descriptions; no title-based or numeric-only guessing.
 */
export function resolvePlatePresentations(
  data: ReaderContent,
  recipes: readonly PlatePresentationRecipe[] = [chibiPlatePresentation],
): ReadonlyMap<string, PlatePresentation> {
  const plates = data.config.illustrations || []
  const recipe = recipes.find((item) => item.canonicalHash === data.project.canonical_sha256)
  const resolve = (plate: ReaderIllustration): PlatePresentation => {
    const sourceBlocks = data.blocks.filter((block) => block.byte_end === plate.after_byte)
    const source = sourceBlocks.length === 1 ? sourceBlocks[0] : undefined
    const lastCharacter = source && [...source.text].at(-1)
    const result: PlatePresentation = {
      displayAfterByte: plate.after_byte,
      disclosureByte: plate.after_byte,
      sourceByte: lastCharacter
        ? plate.after_byte - utf8.encode(lastCharacter).length
        : plate.after_byte,
      visualDescription: null,
    }
    const entry = recipe && verifiedPlateEntry(data, plate, recipe)
    if (!entry || !source) return result
    result.visualDescription = entry.visualDescription
    const display = entry.displayAfter
    if (!display || !source.text.endsWith(display.introduction)) return result
    const startIndex = data.blocks.indexOf(source)
    const validParagraphs = display.paragraphs.every((anchor, index) => {
      const block = data.blocks[startIndex + index + 1]
      return (
        block?.byte_start === anchor.start &&
        block.byte_end === anchor.end &&
        block.text === anchor.text &&
        utf8.encode(block.text).length === block.byte_end - block.byte_start &&
        data.blocks.filter((candidate) => candidate.byte_end === anchor.end).length === 1
      )
    })
    const boundary = display.paragraphs.at(-1)?.end
    if (validParagraphs && boundary !== undefined && boundary >= plate.after_byte) {
      result.displayAfterByte = boundary
      result.disclosureByte = Math.max(plate.after_byte, boundary)
    }
    return result
  }
  return new Map(plates.map((plate) => [plate.id, resolve(plate)]))
}
