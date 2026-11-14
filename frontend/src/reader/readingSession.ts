import type { ReaderClip } from '../reader-types'

export type ScrollJourney = { from: number; to: number; distance: number; forward: boolean }

// Keep the whole gesture, not just its last animation frame. A fast multi-frame
// skip or a reversal must never look like a slow forward reading step.
export function followScroll(
  journey: ScrollJourney | null,
  from: number,
  to: number,
  delta: number,
): ScrollJourney {
  return {
    from: journey?.from ?? from,
    to,
    distance: (journey?.distance ?? 0) + Math.abs(delta),
    forward: (journey?.forward ?? true) && delta >= 0 && to >= from,
  }
}
export function isReadingStep(journey: ScrollJourney, viewportHeight: number) {
  return journey.forward && journey.to > journey.from && journey.distance < viewportHeight * 0.7
}
export function automaticClip(
  clips: ReaderClip[],
  seen: ReadonlySet<string>,
  visible: ReadonlySet<string>,
  from: number,
  to: number,
) {
  return clips.find(
    (c) =>
      c.byte_start <= to && c.byte_end > from && visible.has(c.take_id) && !seen.has(c.take_id),
  )
}
export function nextDialogue(
  clips: ReaderClip[],
  id: string,
  visible: ReadonlySet<string> | null,
  seen?: ReadonlySet<string>,
) {
  const index = clips.findIndex((c) => c.take_id === id)
  const next = index >= 0 ? clips[index + 1] : null
  return next && (!visible || visible.has(next.take_id)) && !seen?.has(next.take_id) ? next : null
}
