import type { ReaderContent, ReaderBlock, ReaderPresentation } from '../reader-types'

const encoder = new TextEncoder()
export const byteLength = (s: string) => encoder.encode(s).length
export type Position = { byte: number; offset: number; plate?: string; imageOffset?: number }
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
  const b = data.blocks.find(
    (b) => typeof p?.byte === 'number' && b.byte_start <= p.byte && p.byte < b.byte_end,
  )
  if (!b) return { byte: data.blocks[0].byte_start, offset: 0 }
  let byte = b.byte_start
  for (const c of b.text) {
    const next = byte + byteLength(c)
    if (next > p!.byte!) break
    byte = next
  }
  return {
    byte: Math.min(byte, b.byte_end - byteLength([...b.text].at(-1)!)),
    offset: Math.max(-2, Math.min(2, Number(p?.offset) || 0)),
    ...(data.config.illustrations?.some((i) => i.id === p?.plate && i.after_byte === b.byte_end)
      ? { plate: p!.plate, imageOffset: Math.max(0, Math.min(1, Number(p?.imageOffset) || 0)) }
      : {}),
  }
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
          .filter((m: any) => typeof m.id === 'string' && typeof m.text === 'string')
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
export function search(data: ReaderContent, query: string) {
  if (!query) return []
  return data.blocks
    .flatMap((b) => {
      const results = []
      let index = b.text.indexOf(query)
      while (index >= 0 && results.length < 300) {
        results.push({
          byte: b.byte_start + byteLength(b.text.slice(0, index)),
          text: b.text.slice(Math.max(0, index - 12), index + query.length + 35),
        })
        index = b.text.indexOf(query, index + Math.max(1, query.length))
      }
      return results
    })
    .slice(0, 300)
}

export function highlightedRuns(block: ReaderBlock, query: string) {
  return block.runs.flatMap((run) => {
    if (!query || !run.text.includes(query)) return [{ ...run, match: false }]
    const parts = []
    let index = 0
    while (index < run.text.length) {
      const found = run.text.indexOf(query, index),
        stop = found < 0 ? run.text.length : found
      if (stop > index)
        parts.push({
          ...run,
          text: run.text.slice(index, stop),
          byte_start: run.byte_start + byteLength(run.text.slice(0, index)),
          byte_end: run.byte_start + byteLength(run.text.slice(0, stop)),
          match: false,
        })
      if (found < 0) break
      parts.push({
        ...run,
        text: query,
        byte_start: run.byte_start + byteLength(run.text.slice(0, found)),
        byte_end: run.byte_start + byteLength(run.text.slice(0, found + query.length)),
        match: true,
      })
      index = found + query.length
    }
    return parts
  })
}
