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
  const idCounts = new Map<string, number>()
  for (const plate of plates) idCounts.set(plate.id, (idCounts.get(plate.id) || 0) + 1)
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
    const entry = recipe?.plates.find((item) => item.id === plate.id)
    if (
      !entry ||
      idCounts.get(plate.id) !== 1 ||
      !source ||
      source.byte_start !== entry.sourceStart ||
      source.byte_end !== entry.sourceEnd ||
      utf8.encode(source.text).length !== source.byte_end - source.byte_start ||
      plate.image_asset_id !== entry.imageAsset ||
      data.media[plate.image_asset_id]?.sha256 !== entry.imageHash
    )
      return result
    // Evidence must resolve once, inside the unchanged semantic anchor paragraph.
    const occurrences = data.blocks.flatMap((block) => {
      const first = block.text.indexOf(entry.evidence)
      if (first < 0) return []
      return block.text.indexOf(entry.evidence, first + 1) < 0 ? [block] : [block, block]
    })
    if (occurrences.length !== 1 || occurrences[0] !== source) return result
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
