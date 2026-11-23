import type {
  ReaderContent,
  ReaderBlock,
  ReaderPresentation,
  ReaderEchoFold,
} from '../reader-types'

const encoder = new TextEncoder()
export const byteLength = (s: string) => encoder.encode(s).length
// DOM offsets and display limits are UTF-16 units; persistent anchors are UTF-8 bytes.
// Snap only if a boundary bisects a scalar. Never normalize or re-decode the source.
export function utf16Boundary(text: string, offset: number, edge: 'floor' | 'ceil' = 'floor') {
  const at = Math.max(0, Math.min(text.length, offset))
  const left = text.charCodeAt(at - 1),
    right = text.charCodeAt(at)
  return left >= 0xd800 && left <= 0xdbff && right >= 0xdc00 && right <= 0xdfff
    ? at + (edge === 'ceil' ? 1 : -1)
    : at
}
export const sourceSlice = (text: string, start: number, end: number) =>
  text.slice(utf16Boundary(text, start), utf16Boundary(text, end, 'ceil'))

// Anchors name a character, not an insertion point: the paragraph end names its
// last scalar. Return both units from one pass, even for an old mid-scalar byte.
export function textPointAtByte(text: string, offset: number) {
  let byte = 0,
    index = 0
  for (const char of text) {
    const cp = char.codePointAt(0)!
    const next = byte + (cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4)
    if (!(next <= offset) || index + char.length === text.length) break
    byte = next
    index += char.length
  }
  return { byte, index }
}
export function anchorByteAtCaret(text: string, offset: number) {
  return byteLength(text.slice(0, utf16Boundary(text, Math.min(offset, text.length - 1))))
}
export function sourceQuote(text: string, offset: number, before: number, after: number) {
  const { index } = textPointAtByte(text, offset)
  return sourceSlice(text, index - before, index + after)
}
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
  originalLines?: boolean
  showSoundscapes?: boolean
  showNarrations?: boolean
  showEchoFold?: boolean
  creativeAuto?: boolean
  muted?: boolean
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
  if (plate)
    return {
      byte: b.byte_end - byteLength(b.text.slice(utf16Boundary(b.text, b.text.length - 1))),
      offset: 0,
      plate: plate.id,
      imageAsset: plate.image_asset_id,
      imageOffset: Math.max(0, Math.min(1, finite(p?.imageOffset))),
    }
  return {
    byte: b.byte_start + textPointAtByte(b.text, p!.byte! - b.byte_start).byte,
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
      ...(typeof p.originalLines === 'boolean' ? { originalLines: p.originalLines } : {}),
      ...(p.showSoundscapes === false ? { showSoundscapes: false } : {}),
      ...(p.showEchoFold === false ? { showEchoFold: false } : {}),
      ...(p.creativeAuto === false ? { creativeAuto: false } : {}),
      ...(p.muted === true ? { muted: true } : {}),
      ...(p.showNarrations === false ? { showNarrations: false } : {}),
      layout:
        p.layout === 'illustrated' || p.layout === 'split'
          ? p.layout
          : data.config.reading_layout || 'split',
    },
    marks: Array.isArray(r.marks)
      ? r.marks
          .filter((m: any) => m && typeof m.id === 'string' && typeof m.text === 'string')
          .slice(0, 300)
          .map((m: Mark) => {
            const position = validPosition(data, m.position)
            // Old ordinary bookmarks could store a clipped surrogate. Regenerate only
            // their derived labels from a resolvable source, never rewrite an excerpt.
            const recoverLabel =
              !m.ranges &&
              !m.position?.plate &&
              typeof m.position?.byte === 'number' &&
              data.blocks.some(
                (b) => b.byte_start <= m.position.byte && m.position.byte < b.byte_end,
              ) &&
              /[\uD800-\uDFFF]/u.test(m.text)
            return {
              ...m,
              position,
              text: recoverLabel
                ? quoteAt(data, position.byte)
                : m.text.slice(0, utf16Boundary(m.text, 3000)),
            }
          })
      : [],
    completed: r.completed === true,
    updated: Number(r.updated) || 0,
  }
}
// Untrusted or stale optional apparatus must not prevent the original from opening.
function validEchoFold(fold: ReaderEchoFold | null | undefined, blocks: ReaderBlock[]) {
  if (!fold || Object.keys(fold).sort().join('|') !== 'earlier|later') return null
  for (const a of [fold.earlier, fold.later]) {
    if (
      !a ||
      Object.keys(a).sort().join('|') !== 'paragraph|quote' ||
      !Number.isInteger(a.paragraph) ||
      a.paragraph < 1 ||
      a.paragraph > blocks.length ||
      typeof a.quote !== 'string' ||
      !/[^\s\u0085]/u.test(a.quote) ||
      /[\uD800-\uDFFF]/u.test(a.quote) ||
      [...a.quote].length > 160
    )
      return null
    const text = blocks[a.paragraph - 1].text
    const at = text.indexOf(a.quote)
    if (at < 0 || text.indexOf(a.quote, at + 1) >= 0) return null
  }
  if (
    fold.later.paragraph - fold.earlier.paragraph < 2 ||
    blocks.slice(fold.earlier.paragraph, fold.later.paragraph).some((b) => b.heading)
  )
    return null
  return fold
}
export function normalizeContent(d: ReaderContent): ReaderContent {
  if (![1, 2, 3, 4, 5, 6].includes(d.schema_version) || !d.blocks?.length)
    throw Error('此阅读内容的版本暂不受支持。')
  // Optional media must fail silent, not prevent reading a sound original paragraph.
  const cueCounts = new Map<string, number>()
  for (const b of d.blocks) {
    for (const cue of [b?.narration, b?.soundscape])
      if (typeof cue?.id === 'string') cueCounts.set(cue.id, (cueCounts.get(cue.id) || 0) + 1)
  }
  const blocks = d.blocks.map(({ narration, soundscape, ...b }) => {
    const ambient = soundscape && d.media?.[soundscape.id]
    const soundOk =
      d.schema_version >= 5 &&
      soundscape &&
      typeof soundscape.id === 'string' &&
      cueCounts.get(soundscape.id) === 1 &&
      ambient?.id === soundscape.id &&
      ambient.type === 'audio' &&
      ambient.origin === 'paragraph_soundscape' &&
      soundscape.duration === 12 &&
      ambient.duration === 12
    const desc = [
      '细雨',
      '一辆车驶过',
      '细雨中一辆车驶过',
      '风声',
      '风中一辆车驶过',
      '铅笔在纸上划过，随后静默',
    ].includes(soundscape?.description || '')
      ? soundscape!.description
      : '环境声'

    const asset = narration && d.media?.[narration.id]
    const usable =
      d.schema_version >= 4 &&
      narration &&
      typeof narration.id === 'string' &&
      cueCounts.get(narration.id) === 1 &&
      asset?.id === narration.id &&
      asset.type === 'audio' &&
      asset.origin === 'paragraph_narration' &&
      Number.isFinite(narration.duration) &&
      narration.duration > 0 &&
      narration.duration <= 120 &&
      narration.duration === asset.duration

    let at = b.byte_start
    return {
      ...b,
      ...(soundOk
        ? {
            soundscape: {
              id: soundscape.id,
              duration: soundscape.duration,
              label: '段落声景',
              description: desc,
            },
          }
        : {}),
      ...(usable
        ? { narration: { id: narration.id, duration: narration.duration, label: '段落朗读' } }
        : {}),
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
  const { echo_fold, ...config } = d.config
  const echo = d.schema_version >= 6 && validEchoFold(echo_fold, blocks)
  return {
    ...d,
    config: echo ? { ...config, echo_fold: echo } : config,
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
  const inBlock = b.byte_start <= byte && byte < b.byte_end
  return sourceQuote(b.text, inBlock ? byte - b.byte_start : 0, 12, 65)
}
// Search offsets are UTF-16 boundaries into the untouched source, never folded text.
export type TextMatch = { start: number; end: number }
export type TextMatcher = (text: string, query: string) => TextMatch[]
export const literalMatches: TextMatcher = (text, query) => {
  if (!query) return []
  const matches: TextMatch[] = []
  let at = 0
  while (at < text.length) {
    const start = text.indexOf(query, at)
    if (start < 0) break
    const end = start + query.length
    if (utf16Boundary(text, start) === start && utf16Boundary(text, end) === end) {
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
      results.push({
        byte: block.byte_start + byteLength(block.text.slice(0, start)),
        text: sourceSlice(block.text, start - 12, end + 35),
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
