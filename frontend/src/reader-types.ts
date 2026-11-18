export type ReaderScene = {
  id: string
  title: string
  start_byte: number
  asset_id: string
  character_ids: string[]
}
export type ReaderPresentation = {
  id: string
  scene_id: string
  start_byte: number
  kind: 'environment' | 'dialogue' | 'event'
  image_asset_id: string
  place_label: string
  time_label: string
  cast: { character_id: string; figure_asset_id: string; slot: 'left' | 'right' }[]
}
export type ReaderMapEntry = {
  id: string
  byte_start: number
  byte_end: number
  label: string
  phase_id: string
  place_ids: string[]
}
export type ReaderEchoAnchor = { paragraph: number; quote: string }
export type ReaderEchoFold = { earlier: ReaderEchoAnchor; later: ReaderEchoAnchor }
export type ReaderConfig = {
  title: string
  subtitle: string
  cover_asset_id: string | null
  scenes: ReaderScene[]
  map_profile: 'chibi' | null
  presentations?: ReaderPresentation[]
  map_entries?: ReaderMapEntry[]
  reading_layout?: 'split' | 'illustrated'
  illustrations?: ReaderIllustration[]
  echo_fold?: ReaderEchoFold | null
}
export type ReaderIllustration = {
  id: string
  after_byte: number
  image_asset_id: string
  title: string
  description: string
  // Omitted preserves legacy exact-image recipes; null is an explicit static direction.
  motion?: IllustrationMotion | null
}
export type MotionPoint = readonly [number, number]
export type MotionPolygons = readonly (readonly MotionPoint[])[]
type MotionDirectionBase = {
  version: 1
  image_sha256: string
  source_sha256: string
  after_byte: number
  width: number
  height: number
  evidence: string
  note: string
  reviewed: boolean
}
export type IllustrationMotion = MotionDirectionBase &
  (
    | {
        effect: 'rain-wet-ground'
        areas: MotionPolygons
        ground: MotionPolygons
        drops: number
        rings: number
      }
    | {
        effect: 'wave-impact-backwash'
        water: MotionPolygons
        bank: readonly MotionPoint[]
        hits: readonly { x: number; phase: number; length: number; gain: number }[]
      }
  )
export type ReaderAsset = {
  id: string
  kind: 'cover' | 'scene'
  status: 'pending' | 'accepted' | 'rejected'
  sha256: string
  width?: number
  height?: number
  license: string
  url: string
  sample_key?: string
  label?: string
}
export type ReaderState = {
  revision: number
  chibi_sample: boolean
  config: ReaderConfig
  assets: ReaderAsset[]
  figures?: {
    id: string
    character_id: string
    status: string
    label?: string
    portrait_state?: string
  }[]
  paragraphs: { byte_start: number; byte_end: number; text: string; preview: string }[]
}
export type ReaderCharacter = { id: string; name: string; figure_id: string | null }
export type ReaderClip = {
  take_id: string
  byte_start: number
  byte_end: number
  speaker_id: string
  duration: number
}
export type ReaderNarration = { id: string; duration: number; label: string }
export type ReaderBlock = {
  source_gap_before?: string
  soundscape?: ReaderNarration & { description: string }
  narration?: ReaderNarration
  id: string
  byte_start: number
  byte_end: number
  text: string
  heading: boolean
  runs: {
    byte_start: number
    byte_end: number
    text: string
    speaker_id: string | null
    take_id: string | null
  }[]
  audio: ReaderClip[]
}
export type MapPlace = {
  id: string
  label: string
  x: number
  y: number
  today: string
  description: string
  source_ids: string[]
}
export type ReaderMapData = {
  title: string
  subtitle: string
  note: string
  viewBox: string
  river: string
  places: MapPlace[]
  phases: { id: string; title: string; description: string }[]
  phase_anchors: number[]
  sources: { id: string; title: string; url: string | null; note: string }[]
}
export type ReaderContent = {
  schema_version: number
  presentations: ReaderPresentation[]
  map_entries: ReaderMapEntry[]
  project: {
    id: string
    filename: string
    sha256: string
    canonical_sha256: string
    rights_status: string
    character_count: number
  }
  versions: { reader_revision: number; review_revision: number; speech_revision: number }
  config: ReaderConfig
  blocks: ReaderBlock[]
  characters: Record<string, ReaderCharacter>
  media: Record<
    string,
    {
      id: string
      type: 'image' | 'figure' | 'audio'
      origin?: string
      credit?: string
      url: string
      sha256: string
      label?: string
      portrait_state?: string
      license?: string
      duration?: number
      width?: number
      height?: number
    }
  >
  map: ReaderMapData | null
  preview: boolean
  issues: string[]
}
