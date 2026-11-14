import { byteLength, type Position } from './model'

function rangeAt(element: HTMLElement, byte: number) {
  const text = element.firstChild
  if (!text || text.nodeType !== Node.TEXT_NODE) return null
  const start = Number(element.dataset.sourceStart)
  let offset = 0,
    at = start
  for (const c of text.textContent || '') {
    if (at >= byte) break
    at += byteLength(c)
    offset += c.length
  }
  offset = Math.min(offset, Math.max(0, (text.textContent || '').length - 1))
  const range = document.createRange()
  range.setStart(text, offset)
  range.setEnd(
    text,
    Math.min(
      offset + (text.textContent!.codePointAt(offset)! > 0xffff ? 2 : 1),
      text.textContent!.length,
    ),
  )
  return range
}
export function restorePosition(root: HTMLElement, p: Position, focus = false) {
  const plate =
    p.plate &&
    Array.from(root.querySelectorAll<HTMLElement>('[data-illustration-id]')).find(
      (e) => e.dataset.illustrationId === p.plate,
    )
  if (plate) {
    const art = plate.querySelector<HTMLElement>('[data-illustration-anchor]') || plate
    const rect = art.getBoundingClientRect()
    root.scrollTop +=
      rect.top + rect.height * (p.imageOffset || 0) - root.getBoundingClientRect().top - 24
    if (focus) root.focus({ preventScroll: true })
    return
  }
  const spans = Array.from(root.querySelectorAll<HTMLElement>('[data-source-start]'))
  const span =
    spans.find(
      (e) => Number(e.dataset.sourceStart) <= p.byte && Number(e.dataset.sourceEnd) > p.byte,
    ) || spans[0]
  if (!span) return
  const rect = rangeAt(span, p.byte)?.getBoundingClientRect() || span.getBoundingClientRect()
  const leading = parseFloat(getComputedStyle(span.parentElement!).lineHeight) || 40
  root.scrollTop += rect.top - root.getBoundingClientRect().top - 24 - p.offset * leading
  if (focus) root.focus({ preventScroll: true })
}
export function capturePosition(root: HTMLElement): Position {
  const top = root.getBoundingClientRect().top + 24
  const plate = Array.from(root.querySelectorAll<HTMLElement>('[data-illustration-id]')).find(
    (e) => {
      const r = e.getBoundingClientRect()
      return r.top <= top && r.bottom > top
    },
  )
  if (plate) {
    const art = plate.querySelector<HTMLElement>('[data-illustration-anchor]') || plate
    const rect = art.getBoundingClientRect()
    return {
      byte: Number(plate.dataset.sourceByte),
      offset: 0,
      plate: plate.dataset.illustrationId,
      imageAsset: plate.dataset.imageAsset,
      imageOffset: Math.max(0, Math.min(1, (top - rect.top) / rect.height)),
    }
  }
  const spans = Array.from(root.querySelectorAll<HTMLElement>('[data-source-start]'))
  const span = spans.find((e) => e.getBoundingClientRect().bottom > top) || spans.at(-1)!
  if (!span) return { byte: 0, offset: 0 }
  const text = span.textContent || ''
  const offsets = [0]
  let units = 0
  for (const c of text) {
    units += c.length
    offsets.push(units)
  }
  const node = span.firstChild!
  let lo = 0,
    hi = Math.max(0, offsets.length - 2)
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2),
      range = document.createRange()
    range.setStart(node, offsets[mid])
    range.setEnd(node, offsets[mid + 1])
    if (range.getBoundingClientRect().bottom <= top) lo = mid + 1
    else hi = mid
  }
  const byte = Number(span.dataset.sourceStart) + byteLength(text.slice(0, offsets[lo]))
  const rect = rangeAt(span, byte)?.getBoundingClientRect()
  const leading = parseFloat(getComputedStyle(span.parentElement!).lineHeight) || 40
  return { byte, offset: rect ? Math.max(-2, Math.min(2, (rect.top - top) / leading)) : 0 }
}
export function selectedExcerpt(root: HTMLElement) {
  const selection = window.getSelection()
  if (!selection?.rangeCount || selection.isCollapsed) return null
  const chosen = selection.getRangeAt(0)
  const ranges: { start: number; end: number }[] = [],
    texts: string[] = []
  for (const span of root.querySelectorAll<HTMLElement>('[data-source-start]')) {
    const node = span.firstChild
    if (!node || !chosen.intersectsNode(node)) continue
    const text = node.textContent || ''
    const start = chosen.startContainer === node ? chosen.startOffset : 0
    const end = chosen.endContainer === node ? chosen.endOffset : text.length
    if (end <= start) continue
    ranges.push({
      start: Number(span.dataset.sourceStart) + byteLength(text.slice(0, start)),
      end: Number(span.dataset.sourceStart) + byteLength(text.slice(0, end)),
    })
    texts.push(text.slice(start, end))
  }
  return ranges.length
    ? {
        ranges,
        text: texts.join('').slice(0, 3000),
        position: { byte: ranges[0].start, offset: 0 },
      }
    : null
}

export function visibleAudioIds(root: HTMLElement) {
  const viewport = root.getBoundingClientRect()
  return new Set(
    Array.from(root.querySelectorAll<HTMLElement>('[data-take]'))
      .filter((span) => {
        const rect = span.getBoundingClientRect()
        return rect.bottom > viewport.top && rect.top < viewport.bottom
      })
      .map((span) => span.dataset.take!),
  )
}
