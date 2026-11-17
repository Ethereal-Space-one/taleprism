import type { ReaderIllustration } from '../reader-types'
import type { PlatePresentation } from './platePresentation'

/** Ephemeral lightbox state only. It must never become part of the reading record. */
export type ImageVisit = {
  asset: string | null
  openedAsset: string | null
  boundary: number
  whole: boolean
  pending: string | null
}

export function openImageVisit(asset: string | null, boundary: number, whole = false): ImageVisit {
  return {
    asset,
    openedAsset: asset,
    boundary: Number.isSafeInteger(boundary) && boundary >= 0 ? boundary : -1,
    whole,
    pending: null,
  }
}

/** Inclusive, validated byte boundary shared by gallery and lightbox browsing. */
export function imageReached(disclosureByte: number, boundary: number): boolean {
  return (
    Number.isSafeInteger(boundary) &&
    boundary >= 0 &&
    Number.isSafeInteger(disclosureByte) &&
    disclosureByte >= 0 &&
    disclosureByte <= boundary
  )
}

/** Current location only, not a high-water or inferred read-history record. */
export function galleryAtPosition(
  plates: readonly ReaderIllustration[],
  presentations: ReadonlyMap<string, PlatePresentation>,
  boundary: number,
): ReaderIllustration[] {
  return plates.filter((plate) =>
    imageReached(presentations.get(plate.id)?.disclosureByte ?? plate.after_byte, boundary),
  )
}

export function requestImage(
  visit: ImageVisit,
  asset: string,
  disclosureByte: number,
  protectFuture: boolean,
): ImageVisit {
  // An inline plate is already visible at its source anchor, which can be one
  // codepoint before its display boundary. Back/Next may freely revisit it.
  const reached = asset === visit.openedAsset || imageReached(disclosureByte, visit.boundary)
  return !protectFuture || visit.whole || reached
    ? { ...visit, asset, pending: null }
    : { ...visit, pending: asset }
}

export function confirmImageDisclosure(visit: ImageVisit): ImageVisit {
  return visit.pending ? { ...visit, asset: visit.pending, whole: true, pending: null } : visit
}

export function cancelImageDisclosure(visit: ImageVisit): ImageVisit {
  return { ...visit, pending: null }
}
