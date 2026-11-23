import type { ReaderIllustration } from '../reader-types'
import type { PlatePresentation } from './platePresentation'

/** Ephemeral lightbox state only. It must never become part of the reading record. */
export type ImageVisit = {
  asset: string | null
  plate: string | null
  openedPlate: string | null
  pendingPlate: string | null
  openedAsset: string | null
  boundary: number
  whole: boolean
  pending: string | null
}

export function openImageVisit(
  asset: string | null,
  boundary: number,
  whole = false,
  plate: string | null = null,
): ImageVisit {
  return {
    asset,
    plate,
    openedPlate: plate,
    pendingPlate: null,
    openedAsset: asset,
    boundary: Number.isSafeInteger(boundary) && boundary >= 0 ? boundary : -1,
    whole,
    pending: null,
  }
}

/** Stage images are not placed illustrations. A repeated asset has no unique title or alt. */
export function placedImage(visit: ImageVisit | null, plates: readonly ReaderIllustration[]) {
  return visit?.plate
    ? plates.find((p) => p.id === visit.plate && p.image_asset_id === visit.asset)
    : undefined
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
  plate: string | null = null,
): ImageVisit {
  // An inline plate is already visible at its source anchor, which can be one
  // codepoint before its display boundary. Back/Next may freely revisit it.
  const reached =
    (asset === visit.openedAsset && plate === visit.openedPlate) ||
    imageReached(disclosureByte, visit.boundary)
  return visit.whole || reached
    ? { ...visit, asset, plate, pending: null, pendingPlate: null }
    : { ...visit, pending: asset, pendingPlate: plate }
}

export function confirmImageDisclosure(visit: ImageVisit): ImageVisit {
  return visit.pending
    ? {
        ...visit,
        asset: visit.pending,
        plate: visit.pendingPlate,
        whole: true,
        pending: null,
        pendingPlate: null,
      }
    : visit
}

export function cancelImageDisclosure(visit: ImageVisit): ImageVisit {
  return { ...visit, pending: null, pendingPlate: null }
}

/** A whole-gallery permission is not a browser-history grant. On Forward,
 * reopen an unread target behind a notice, without mounting the image or copy. */
export function restoreImageVisit(
  asset: string | null,
  plate: string | null,
  previouslyWhole: boolean,
  boundary: number,
  disclosureByte: number,
) {
  if (asset && plate && previouslyWhole) {
    return requestImage(openImageVisit(null, boundary), asset, disclosureByte, plate)
  }
  return openImageVisit(asset, boundary, false, plate)
}
