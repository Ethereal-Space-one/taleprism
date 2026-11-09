export type Project = {
  id: string
  filename: string
  encoding: string
  rights_status: string
  character_count: number
  byte_length: number
  span_count: number
  unit_count: number
  sha256: string
  canonical_sha256: string
  created_at: string
}
export type Span = { id: number; byte_start: number; byte_end: number; kind: string; text: string }
export type Unit = {
  id: number
  byte_start: number
  byte_end: number
  text: string
  speaker_id: string | null
}
export type Evidence = { byte_start: number; byte_end: number; quote?: string }
export type Character = {
  id: string
  display_name: string
  aliases: string[]
  description: string
  status: 'candidate' | 'confirmed' | 'rejected' | 'merged'
  evidence: Evidence[]
  active_figure_id: string | null
  merged_into: string | null
  origin: string
}
export type Dialogue = {
  id: string
  text: string
  byte_start: number
  byte_end: number
  outer_start: number
  outer_end: number
  speaker_id: string | null
  suggested_speaker_id: string | null
  status: 'pending' | 'reviewed'
  confidence: number
  evidence: Evidence[]
  context_before: string
  context_after: string
  origin: string
}
export type Asset = {
  id: string
  character_id: string
  kind: 'reference' | 'figure' | 'reference_and_figure'
  status: 'pending' | 'accepted' | 'rejected'
  width: number
  height: number
  license: string
  sha256: string
  url: string
  origin: string
  label?: string
  sample_key?: string
  portrait_state?: string
}
export type ReviewState = {
  revision: number
  characters: Character[]
  dialogues: Dialogue[]
  assets: Asset[]
  pending_count: number
  last_analysis: {
    model: string
    completed_at: string
    requests: number
    cache_hits: number
  } | null
}
export type ModelStatus = { configured: boolean; provider: string; model: string; base_url: string }
export type PresentationUnit = Unit & {
  speaker_name?: string | null
  figure_asset_id?: string | null
}
export type TextData = { text: string; spans: Span[]; units: PresentationUnit[] }
export type Job = {
  id: string
  kind: 'export' | 'reader_export' | 'analysis' | 'speech'
  state: 'running' | 'failed' | 'completed'
  error: string | null
  created_at: string
  result: {
    export_id?: string
    format?: string
    archive_sha256?: string
    file_count?: number
    play_url?: string
    download_url?: string
    checks?: Record<string, unknown>
    review_revision?: number
    speech_revision?: number
    visual_revision?: number
    reader_revision?: number
    generated?: number
    reused?: number
  } | null
}

export async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(
      typeof body.detail === 'string' ? body.detail : '请求未完成，请检查文件后重试。',
    )
  }
  return response.json()
}
