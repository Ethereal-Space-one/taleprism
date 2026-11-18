import { useLayoutEffect, useMemo, useRef, type RefObject } from 'react'

export type ReadingCueKind = 'sound' | 'motion' | 'echo'
type Options = {
  root: RefObject<HTMLElement | null>
  edition: string
  running: boolean
  onCue: (kind: ReadingCueKind, key: string) => void
  onDiscontinuity?: () => void
}

const selector = '[data-auto-sound],[data-auto-motion],[data-auto-echo]'
const maxSeen = 2048
type Target = { element: HTMLElement; kind: ReadingCueKind; key: string }

// Only opaque cue identities, never manuscript text, timestamps, a gesture log,
// or a copy of the book. A full ledger fails quiet rather than evicting old cues.
function identity(kind: ReadingCueKind, key: string) {
  let a = 2166136261,
    b = 5381
  for (const c of kind + ':' + key) {
    a = Math.imul(a ^ c.codePointAt(0)!, 16777619)
    b = Math.imul(b, 33) ^ c.codePointAt(0)!
  }
  return [a, b].map((v) => (v >>> 0).toString(16).padStart(8, '0')).join('')
}
function cueLedger(edition: string) {
  const key = edition + ':encounters-v1'
  const seen = new Set<string>()
  let entered = false
  try {
    const raw = window.sessionStorage.getItem(key)
    if (raw && raw.length <= 40000) {
      const v = JSON.parse(raw)
      if (v && v.entered === true && Array.isArray(v.seen) && v.seen.length <= maxSeen) {
        entered = true
        for (const id of v.seen)
          if (typeof id === 'string' && /^[\da-f]{16}$/.test(id)) seen.add(id)
      }
    }
  } catch {
    /* blocked or damaged storage never prevents reading */
  }
  function save() {
    try {
      window.sessionStorage.setItem(key, JSON.stringify({ entered, seen: [...seen] }))
    } catch {
      /* retain once-only behavior in this mounted edition */
    }
  }
  function has(kind: ReadingCueKind, value: string) {
    return seen.size >= maxSeen || seen.has(identity(kind, value))
  }
  return {
    begin(fresh: boolean) {
      const first = fresh || !entered
      if (fresh) seen.clear()
      entered = true
      save()
      return first
    },
    has,
    consume(kind: ReadingCueKind, value: string) {
      if (!value || value.length > 512 || has(kind, value)) return false
      seen.add(identity(kind, value))
      entered = true
      save()
      return true
    },
  }
}

function reached(root: HTMLElement) {
  const bounds = root.getBoundingClientRect()
  const vp = window.visualViewport
  const top = Math.max(vp?.offsetTop ?? 0, bounds.top),
    bottom = Math.min(vp ? vp.offsetTop + vp.height : window.innerHeight, bounds.bottom)
  const left = Math.max(vp?.offsetLeft ?? 0, bounds.left),
    right = Math.min(vp ? vp.offsetLeft + vp.width : window.innerWidth, bounds.right)
  const targets: Target[] = []
  if (bottom <= top || right <= left) return { tail: false, targets }
  const paragraphs = root.getElementsByClassName('reader-paragraph')
  const last = paragraphs[paragraphs.length - 1]?.getBoundingClientRect()
  // A short poem can all fit even though decorative bottom padding can scroll.
  // On the last screen the reading line cannot be moved over a low final line.
  const tail =
    root.scrollHeight - root.clientHeight - root.scrollTop <= 2 ||
    (!!last && last.bottom <= bottom && last.bottom > top)
  const line = tail ? bottom : top + (bottom - top) * 0.55
  const nodes = root.querySelectorAll<HTMLElement>(selector)
  // The markers are disjoint, ordered siblings in one manuscript column. Skip
  // long prefixes without reading the geometry of every preceding paragraph.
  let lo = 0,
    hi = nodes.length
  while (lo < hi) {
    const mid = (lo + hi) >>> 1
    if (nodes[mid].getBoundingClientRect().bottom <= top) lo = mid + 1
    else hi = mid
  }
  for (let i = lo; i < nodes.length; i++) {
    const element = nodes[i],
      d = element.dataset
    if (element.getBoundingClientRect().top >= line) break
    const kind =
      d.autoSound !== undefined ? 'sound' : d.autoMotion !== undefined ? 'motion' : 'echo'
    const key = d.autoSound ?? d.autoMotion ?? d.autoEcho
    if (!key || key.length > 512) continue
    // A caption or the audio button alone is not its owning illustration/prose.
    const anchor =
      element.querySelector<HTMLElement>(
        kind === 'motion'
          ? '[data-illustration-anchor]'
          : kind === 'sound'
            ? '.reader-paragraph-text'
            : 'summary',
      ) || element
    const r = anchor.getBoundingClientRect()
    const depth = Math.min(bottom, r.bottom) - Math.max(top, r.top)
    const required = Math.min(r.height, kind === 'motion' ? 72 : 24, (bottom - top) / 3)
    if (
      r.width <= 0 ||
      r.height <= 0 ||
      r.right <= left ||
      r.left >= right ||
      r.top >= line ||
      depth < required ||
      (kind === 'echo' && (r.top < top - 1 || r.bottom > bottom + 1))
    )
      continue
    targets.push({ element, kind, key })
  }
  return { tail, targets }
}

/** One clock for forward encounters. It can reveal an attached cue, never navigate. */
export function readingCueConductor(edition: string, options: () => Options) {
  const ledger = cueLedger(edition)
  let timer: ReturnType<typeof setTimeout> | undefined,
    revision = 0
  let armed = false,
    entrance = false,
    y = 0,
    distance = 0,
    broken = false
  let pageStep = false,
    openingInput = false
  let frontier: HTMLElement | null = null
  function cancel() {
    revision++
    clearTimeout(timer)
    timer = undefined
  }
  function invalidate() {
    cancel()
    entrance = armed = broken = pageStep = false
    distance = 0
    options().onDiscontinuity?.()
  }
  function later(ms: number, fn: () => void) {
    cancel()
    const token = revision
    timer = setTimeout(() => {
      if (token === revision) fn()
    }, ms)
  }
  function live() {
    const { root, running } = options()
    return running && !document.hidden && root.current?.isConnected ? root.current : null
  }
  function eligible(t: Target) {
    // Never work backwards through older candidates when the nearest one is spent.
    return (
      (!frontier?.isConnected ||
        frontier === t.element ||
        !!(frontier.compareDocumentPosition(t.element) & Node.DOCUMENT_POSITION_FOLLOWING)) &&
      !ledger.has(t.kind, t.key)
    )
  }
  function probe(opening: boolean) {
    const root = live()
    if (!root || !armed) return
    const { tail, targets } = reached(root)
    const ordered = opening || tail
    // A small phone may show the owning prose and its immediately following
    // image together. Prefer the nearest in each lane (even when already spent,
    // so we don't work backwards from it), preserving actual manuscript order.
    // A regular gesture can NEVER queue multiple sounds or multiple plates.
    const nearestSound = targets.filter((v) => v.kind === 'sound').at(-1)
    const nearestVisual = targets.filter((v) => v.kind !== 'sound').at(-1)
    const group = ordered
      ? targets.filter(eligible).slice(0, 1)
      : targets.filter((v) => (v === nearestSound || v === nearestVisual) && eligible(v))
    function visit(index: number) {
      const t = group[index]
      if (!t) return
      const deliver = () => {
        // Re-check the ACTUAL target, geometry and all gates after the dwell.
        if (
          live() !== root ||
          !armed ||
          !eligible(t) ||
          !reached(root!).targets.some(
            (v) => v.element === t.element && v.kind === t.kind && v.key === t.key,
          )
        )
          return
        if (!ledger.consume(t.kind, t.key)) return
        frontier = t.element
        const token = revision
        options().onCue(t.kind, t.key)
        if (revision !== token) return
        if (ordered) later(1600, () => probe(opening))
        else visit(index + 1)
      }
      if (t.kind === 'echo') later(opening ? 3200 : 800, deliver)
      else deliver()
    }
    visit(0)
  }
  function begin(fresh: boolean, opening: boolean, firstSound?: string) {
    cancel()
    const first = ledger.begin(fresh)
    if (fresh) frontier = null
    distance = 0
    broken = pageStep = openingInput = false
    armed = entrance = first && opening && !document.hidden
    if (!entrance) return
    // The caller can certify ONLY the opening paragraph on the cover's actual
    // activation. The audio play attempt must remain in this gesture's stack.
    if (firstSound && ledger.consume('sound', firstSound)) options().onCue('sound', firstSound)
    later(700, () => {
      entrance = false
      probe(true)
    })
  }
  function attach(root: HTMLElement) {
    y = root.scrollTop
    const initialY = y
    function discontinuity() {
      entrance = false
      if (!broken) options().onDiscontinuity?.()
      broken = true
    }
    function intent() {
      // A forward wheel on a fully fitted poem has no scroll event. Preserve
      // its opening dwell unless the manuscript actually moves.
      if (entrance) openingInput = true
      armed = true
    }
    function wheel(e: WheelEvent) {
      if (e.ctrlKey || !e.deltaY) return
      intent()
      pageStep = false
      if (e.deltaY < 0) {
        cancel()
        discontinuity()
        later(220, settle)
      }
    }
    function keydown(e: KeyboardEvent) {
      if (e.key === 'Home' || e.key === 'End') {
        invalidate()
        return
      }
      if (['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp', ' '].includes(e.key)) {
        intent()
        // One deliberate keyboard page is a reading step. Repeated keys or a
        // longer jump still must not drain the intervening cues.
        pageStep = !e.repeat && !e.shiftKey && (e.key === 'PageDown' || e.key === ' ')
        if (e.key === 'ArrowUp' || e.key === 'PageUp' || (e.key === ' ' && e.shiftKey)) {
          discontinuity()
          later(220, settle)
        }
      }
    }
    function pointer(e: PointerEvent) {
      // Clicking prose, the fold or a source button is not reading movement.
      if (e.target === root || e.button === 1) intent()
    }
    function settle() {
      const ok = armed && !broken && distance > 0
      broken = pageStep = false
      distance = 0
      if (ok) probe(false)
    }
    function scroll() {
      const delta = root.scrollTop - y
      y = root.scrollTop
      if (!delta || !armed) return
      if (entrance && !openingInput) {
        // Aligning the first source line at startup can shift by its padding.
        // A real relocation during that quiet frame is not an opening.
        if (Math.abs(y - initialY) > Math.min(112, root.clientHeight * 0.35)) invalidate()
        return
      }
      entrance = false
      distance += Math.abs(delta)
      if (delta < 0 || distance >= Math.max(1, root.clientHeight) * (pageStep ? 1.05 : 0.78))
        discontinuity()
      later(220, settle)
    }
    function hide() {
      if (document.hidden) invalidate()
    }
    root.addEventListener('wheel', wheel, { passive: true })
    root.addEventListener('keydown', keydown)
    root.addEventListener('touchmove', intent, { passive: true })
    root.addEventListener('pointerdown', pointer, { passive: true })
    root.addEventListener('scroll', scroll, { passive: true })
    document.addEventListener('visibilitychange', hide)
    return () => {
      cancel()
      armed = entrance = broken = pageStep = false
      distance = 0
      root.removeEventListener('wheel', wheel)
      root.removeEventListener('keydown', keydown)
      root.removeEventListener('touchmove', intent)
      root.removeEventListener('pointerdown', pointer)
      root.removeEventListener('scroll', scroll)
      document.removeEventListener('visibilitychange', hide)
    }
  }
  return { begin, invalidate, consume: ledger.consume, attach }
}

export function useReadingCues(options: Options) {
  const latest = useRef(options)
  latest.current = options
  const cues = useMemo(
    () => readingCueConductor(options.edition, () => latest.current),
    [options.edition],
  )
  useLayoutEffect(() => {
    if (options.running && options.root.current) return cues.attach(options.root.current)
  }, [cues, options.running, options.root])
  return cues
}
