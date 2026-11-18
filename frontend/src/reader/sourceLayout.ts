import type { ReaderBlock, ReaderContent } from '../reader-types'
import { byteLength } from './model'

// Whitespace between visible paragraphs stays separate from their stable story anchors.
// Legacy exports have no gaps; do not invent an exact original layout for those editions.
export function originalSpacing(blocks: ReaderBlock[]) {
  let previous = 0
  const parts: { gap: string; indent: string; blanks: number }[] = []
  for (const [i, b] of blocks.entries()) {
    const gap = b.source_gap_before
    if (
      typeof gap !== 'string' ||
      !/^[\uFEFF\x20\t\u3000\r\n]*$/.test(gap) ||
      byteLength(gap) !== b.byte_start - previous
    )
      return null
    const breaks = (gap.match(/\r\n|\r|\n/g) || []).length
    parts.push({
      gap,
      indent: gap
        .split(/\r\n|\r|\n/)
        .at(-1)!
        .replace(/^\uFEFF/, ''),
      blanks: Math.max(0, breaks - (i ? 1 : 0)),
    })
    previous = b.byte_end
  }
  return parts
}
// Honor literal author separators, never guess word boundaries or add verse breaks.
// Equal short Han phrases ending in punctuation can stay together at line wraps.
export function spacedVerse(text: string) {
  if (text.length > 240) return false
  const phrases = text.split(/[ \t\u3000]+/)
  if (phrases.length < 3 || phrases.length > 12) return false
  const n = [...phrases[0]].length
  return (
    n >= 4 &&
    n <= 10 &&
    phrases.every((p) => [...p].length === n && /^\p{Script=Han}+[，。；！？、：]$/u.test(p))
  )
}
export function preferOriginalLines(data: ReaderContent) {
  return (
    (data.blocks.length > 1 || spacedVerse(data.blocks[0].text)) &&
    data.blocks.length <= 60 &&
    !data.config.scenes.length &&
    !data.presentations.length &&
    data.blocks.every((b) => !b.heading && [...b.text].length <= 65)
  )
}
