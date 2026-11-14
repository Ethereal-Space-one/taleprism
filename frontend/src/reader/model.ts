import type { ReaderContent, ReaderBlock, ReaderPresentation } from '../reader-types'

const encoder = new TextEncoder()
export const byteLength = (s: string) => encoder.encode(s).length
export type Position = {
  byte: number
  offset: number
  plate?: string
  imageAsset?: string
  imageOffset?: number
}
export type Mark = {
  id: string
  position: Position
  text: string
  ranges?: { start: number; end: number }[]
}
export type Preferences = {
  size: number
  leading: number
  width: number
  stage: boolean
  layout?: 'split' | 'illustrated'
}
export type RecordData = {
  version: 2
  resume: Position
  furthest: number
  preferences: Preferences
  marks: Mark[]
  completed: boolean
  updated: number
}
export type Navigation = { view: Position; resume: Position; furthest: number; visits: Position[] }
export type NavigationAction =
  | { type: 'scroll'; position: Position }
  | { type: 'visit'; position: Position }
  | { type: 'restore'; position: Position; visits: Position[] }
  | { type: 'continue' }
  | { type: 'restart'; position: Position }
export function navigationReducer(s: Navigation, a: NavigationAction): Navigation {
  if (a.type === 'scroll')
    return {
      ...s,
      view: a.position,
      resume: s.visits.length ? s.resume : a.position,
      furthest: s.visits.length ? s.furthest : Math.max(s.furthest, a.position.byte),
    }
  if (a.type === 'visit') return { ...s, view: a.position, visits: [...s.visits, s.view] }
  if (a.type === 'restore') return { ...s, view: a.position, visits: a.visits }
  if (a.type === 'continue')
    return { ...s, resume: s.view, furthest: Math.max(s.furthest, s.view.byte), visits: [] }
  return { view: a.position, resume: a.position, furthest: a.position.byte, visits: [] }
}
export const defaults: Preferences = { size: 21, leading: 1.95, width: 680, stage: true }
export function validPosition(data: ReaderContent, value: unknown): Position {
  const p = value as Partial<Position> | null
  const finite = (value: unknown, fallback = 0) =>
    typeof value === 'number' && Number.isFinite(value) ? value : fallback
  const plate =
    data.config.illustrations?.find((i) =>
      p?.imageAsset ? i.image_asset_id === p.imageAsset && i.id === p.plate : i.id === p?.plate,
    ) ||
    (p?.imageAsset
      ? data.config.illustrations?.find((i) => i.image_asset_id === p.imageAsset)
      : undefined)
  // Image identity wins over an old text anchor when an illustration is moved.
  // Pre-image v2 positions still migrate through their plate ID; text-only v1/v2
  // positions remain text positions instead of guessing which image was intended.
  const b = plate
    ? data.blocks.find((b) => b.byte_end === plate.after_byte)
    : data.blocks.find(
        (b) => typeof p?.byte === 'number' && b.byte_start <= p.byte && p.byte < b.byte_end,
      )
  if (!b) return { byte: data.blocks[0].byte_start, offset: 0 }
  const lastByte = b.byte_end - byteLength([...b.text].at(-1)!)
  if (plate)
    return {
      byte: lastByte,
      offset: 0,
      plate: plate.id,
      imageAsset: plate.image_asset_id,
      imageOffset: Math.max(0, Math.min(1, finite(p?.imageOffset))),
    }
  let byte = b.byte_start
  for (const c of b.text) {
    const next = byte + byteLength(c)
    if (next > p!.byte!) break
    byte = next
  }
  return {
    byte: Math.min(byte, lastByte),
    offset: Math.max(-2, Math.min(2, finite(p?.offset))),
  }
}
export function sameBookmarkPosition(a: Position, b: Position) {
  if (a.plate || b.plate)
    return (
      !!a.plate &&
      !!b.plate &&
      a.plate === b.plate &&
      (!a.imageAsset || !b.imageAsset || a.imageAsset === b.imageAsset) &&
      Math.abs((a.imageOffset || 0) - (b.imageOffset || 0)) < 0.025
    )
  return a.byte === b.byte
}

export function readRecord(data: ReaderContent, raw: string | null): RecordData {
  let r: any = {}
  try {
    r = JSON.parse(raw || '{}') || {}
  } catch {
    /* Invalid personal storage never blocks reading. */
  }
  const resume = validPosition(data, r.version === 2 ? r.resume : { byte: r.at, offset: 0 })
  const p = r.version === 2 ? r.preferences || {} : r
  const bounded = (v: unknown, fallback: number, lo: number, hi: number) =>
    Number.isFinite(Number(v)) ? Math.min(hi, Math.max(lo, Number(v))) : fallback
  return {
    version: 2,
    resume,
    furthest: Math.max(resume.byte, validPosition(data, { byte: r.furthest }).byte),
    preferences: {
      size: bounded(p.size, 21, 18, 28),
      leading: bounded(p.leading, 1.95, 1.6, 2.3),
      width: bounded(p.width, 680, 480, 960),
      stage: p.stage !== false,
      layout:
        p.layout === 'illustrated' || p.layout === 'split'
          ? p.layout
          : data.config.reading_layout || 'split',
    },
    marks: Array.isArray(r.marks)
      ? r.marks
          .filter((m: any) => m && typeof m.id === 'string' && typeof m.text === 'string')
          .slice(0, 300)
          .map((m: Mark) => ({
            ...m,
            position: validPosition(data, m.position),
            text: m.text.slice(0, 3000),
          }))
      : [],
    completed: r.completed === true,
    updated: Number(r.updated) || 0,
  }
}
export function normalizeContent(d: ReaderContent): ReaderContent {
  if (![1, 2, 3].includes(d.schema_version) || !d.blocks?.length)
    throw Error('此阅读内容的版本暂不受支持。')
  const blocks = d.blocks.map((b) => {
    let at = b.byte_start
    return {
      ...b,
      runs: b.runs.map((r) => {
        const start = at
        at += byteLength(r.text)
        return { ...r, byte_start: start, byte_end: at }
      }),
    }
  })
  const presentations: ReaderPresentation[] =
    d.presentations ||
    d.config.scenes.map((s) => ({
      id: `legacy-${s.id}`,
      scene_id: s.id,
      start_byte: s.start_byte,
      kind: s.character_ids.length ? 'dialogue' : 'environment',
      image_asset_id: s.asset_id,
      place_label: s.title,
      time_label: '',
      cast: s.character_ids.slice(0, 2).flatMap((id, i) =>
        d.characters[id]?.figure_id
          ? [
              {
                character_id: id,
                figure_asset_id: d.characters[id].figure_id!,
                slot: i === 0 ? ('left' as const) : ('right' as const),
              },
            ]
          : [],
      ),
    }))
  return {
    ...d,
    blocks,
    presentations,
    map_entries: d.map_entries || [],
    map: d.map
      ? {
          ...d.map,
          phases: d.map.phases.map((p, i) => ({
            ...p,
            id: p.id || ['opposition', 'fire', 'retreat'][i],
          })),
        }
      : null,
  }
}
export function blockAt(blocks: ReaderBlock[], byte: number) {
  return blocks.find((b) => b.byte_start <= byte && byte < b.byte_end) || blocks[0]
}
export function quoteAt(data: ReaderContent, byte: number) {
  const b = blockAt(data.blocks, byte)
  const n = encoder.encode(b.text).slice(0, Math.max(0, byte - b.byte_start))
  const index = new TextDecoder().decode(n).length
  return b.text.slice(Math.max(0, index - 12), index + 65)
}
// Search offsets are UTF-16 boundaries into the untouched source, never folded text.
export type TextMatch = { start: number; end: number }
export type TextMatcher = (text: string, query: string) => TextMatch[]
const codePointBoundary = (text: string, at: number) =>
  !(at > 0 && /[\uD800-\uDBFF]/.test(text[at - 1]) && /[\uDC00-\uDFFF]/.test(text[at] || ''))
export const literalMatches: TextMatcher = (text, query) => {
  if (!query) return []
  const matches: TextMatch[] = []
  let at = 0
  while (at < text.length) {
    const start = text.indexOf(query, at)
    if (start < 0) break
    const end = start + query.length
    if (codePointBoundary(text, start) && codePointBoundary(text, end)) {
      matches.push({ start, end })
      at = end
    } else at = start + 1
  }
  return matches
}
export function search(data: ReaderContent, query: string, match: TextMatcher = literalMatches) {
  if (!query) return []
  const results: { byte: number; text: string }[] = []
  for (const block of data.blocks) {
    for (const { start, end } of match(block.text, query)) {
      let from = Math.max(0, start - 12),
        to = Math.min(block.text.length, end + 35)
      if (!codePointBoundary(block.text, from)) from--
      if (!codePointBoundary(block.text, to)) to++
      results.push({
        byte: block.byte_start + byteLength(block.text.slice(0, start)),
        text: block.text.slice(from, to),
      })
      if (results.length === 300) return results
    }
  }
  return results
}

export function highlightedRuns(
  block: ReaderBlock,
  query: string,
  match: TextMatcher = literalMatches,
) {
  const matches = query ? match(block.text, query) : []
  let offset = 0
  return block.runs.flatMap((run) => {
    const start = offset
    offset += run.text.length
    const ranges = matches
      .filter((m) => m.start < offset && m.end > start)
      .map((m) => ({
        start: Math.max(0, m.start - start),
        end: Math.min(run.text.length, m.end - start),
      }))
    if (!ranges.length) return [{ ...run, match: false }]
    const parts: (typeof run & { match: boolean })[] = []
    const add = (from: number, to: number, match: boolean) => {
      if (from < to)
        parts.push({
          ...run,
          text: run.text.slice(from, to),
          byte_start: run.byte_start + byteLength(run.text.slice(0, from)),
          byte_end: run.byte_start + byteLength(run.text.slice(0, to)),
          match,
        })
    }
    let at = 0
    for (const range of ranges) {
      add(at, range.start, false)
      add(range.start, range.end, true)
      at = range.end
    }
    add(at, run.text.length, false)
    return parts
  })
}
