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
}
export type ReaderIllustration = {
  id: string
  after_byte: number
  image_asset_id: string
  title: string
  description: string
}
export type ReaderAsset = {
  id: string
  kind: 'cover' | 'scene'
  status: 'pending' | 'accepted' | 'rejected'
  sha256: string
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
export type ReaderBlock = {
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
