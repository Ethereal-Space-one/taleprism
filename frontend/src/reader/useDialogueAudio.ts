import { useCallback, useEffect, useMemo, useRef, useState, type SetStateAction } from 'react'
import type { ReaderContent } from '../reader-types'
import { automaticClip, nextDialogue } from './readingSession'
export type AudioPoint = { id: string; time: number } | null
export function useDialogueAudio(data: ReaderContent) {
  const element = useRef<HTMLAudioElement>(null)
  const [automatic, updateAutomatic] = useState(false)
  const [current, setCurrent] = useState<string | null>(null)
  const [status, updateStatus] = useState<'idle' | 'playing' | 'paused' | 'failed'>('idle')
  const [notice, setNotice] = useState('')
  // Only normalizeContent's approved, paragraph-owned, finite soundscapes participate.
  // Dialogue and narration keep their separate, intentional listening controls.
  const [cueBlocked, setCueBlocked] = useState(false)
  const cueOwners = useMemo(
    () =>
      new Map(
        data.blocks.flatMap((b) =>
          b.soundscape ? [[b.byte_start, b.soundscape.id] as const] : [],
        ),
      ),
    [data.blocks],
  )
  const cueSeen = useRef(new Set<string>()),
    target = useRef<string | null>(null), // latest eligible paragraph, never a travel history
    waiting = useRef<string | null>(null), // current cue deferred behind reader-chosen audio
    blocked = useRef<string | null>(null), // NotAllowedError, not a media/decoding failure
    creative = useRef(false),
    muted = useRef(false)
  const clearTarget = useCallback(() => {
    target.current = null
    waiting.current = null
    blocked.current = null
    setCueBlocked(false)
  }, [])
  const generation = useRef(0),
    seen = useRef(new Set<string>()),
    queue = useRef<'manual' | 'automatic' | null>(null),
    pending = useRef<string | null>(null),
    visible = useRef<Set<string> | null>(null),
    automaticRef = useRef(false),
    statusRef = useRef(status)
  const clips = useRef(data.blocks.flatMap((b) => b.audio))
  const passages = useRef(
    new Set(
      data.blocks.flatMap((b) => [b.narration, b.soundscape].flatMap((c) => (c ? [c.id] : []))),
    ),
  )
  const pointer = useRef<AudioPoint>(null)
  const setStatus = useCallback((next: typeof status) => {
    statusRef.current = next
    updateStatus(next)
  }, [])
  const setAutomatic = useCallback((next: SetStateAction<boolean>) => {
    automaticRef.current = typeof next === 'function' ? next(automaticRef.current) : next
    if (!automaticRef.current) pending.current = null
    updateAutomatic(automaticRef.current)
  }, [])
  const playbackPoint = useCallback(
    (): AudioPoint =>
      pointer.current
        ? { id: pointer.current.id, time: element.current?.currentTime ?? pointer.current.time }
        : null,
    [],
  )
  // History contains only a sound the reader chose. Returning to a panel or
  // reloading must not turn an automatically started accent into a queued take.
  const point = useCallback(() => (creative.current ? null : playbackPoint()), [playbackPoint])
  const suspend = useCallback(() => {
    generation.current++
    clearTarget()
    queue.current = null
    pending.current = null
    element.current?.pause()
    if (pointer.current) {
      pointer.current = playbackPoint()
      setStatus('paused')
    }
  }, [clearTarget, playbackPoint, setStatus])
  const stop = useCallback(() => {
    suspend()
    creative.current = false
    pointer.current = null
    setCurrent(null)
    setStatus('idle')
    element.current?.removeAttribute('src')
    element.current?.load()
  }, [suspend, setStatus])
  const interruptCue = useCallback(() => {
    // Unlike suspend()/stop(), a reading discontinuity has no claim on an
    // explicit narration/dialogue. Never add an interrupted cue back to the queue.
    if (creative.current && statusRef.current === 'playing') stop()
    else clearTarget()
  }, [clearTarget, stop])
  const begin = useCallback(
    (id: string, time: number, mode: 'manual' | 'automatic' | 'creative' | null) => {
      const a = element.current,
        clip = clips.current.find((c) => c.take_id === id)
      const passage = passages.current.has(id)
      if (!a || (!clip && !passage) || (passage && mode === 'automatic') || !data.media[id]) return
      if (document.hidden) return
      if (muted.current) {
        if (mode === 'manual') setNotice('已静音。取消静音后即可播放。')
        return
      }
      if (mode !== 'creative') clearTarget()
      creative.current = mode === 'creative'
      if (passage) cueSeen.current.add(id)
      const token = ++generation.current
      a.pause()
      a.loop = false
      a.src = data.media[id].url
      a.currentTime = Number.isFinite(time) ? Math.max(0, time) : 0
      pointer.current = { id, time: a.currentTime }
      // A passage reading or soundscape is one listening gesture; neither queues anything.
      queue.current = passage || mode === 'creative' ? null : mode
      if (mode === 'manual') visible.current = null
      pending.current = null
      seen.current.add(id)
      setCurrent(id)
      setStatus('playing')
      setNotice('')
      // Invoke play() on the shared real element in this call stack. A cover
      // gesture can play an actual opening cue; a silent/unrelated asset never
      // stands in for permission. The browser remains the permission authority.
      a.play().catch((error: unknown) => {
        if (generation.current === token) {
          queue.current = null
          pending.current = null
          if (
            mode === 'creative' &&
            typeof error === 'object' &&
            error !== null &&
            'name' in error &&
            error.name === 'NotAllowedError'
          ) {
            creative.current = false
            pointer.current = null
            setCurrent(null)
            setStatus('idle')
            if (target.current === id) {
              blocked.current = id
              setCueBlocked(true)
            }
          } else {
            setStatus('failed')
            setNotice('声音暂未播放，可重试；正文可以继续阅读。')
          }
        }
      })
    },
    [clearTarget, data.media, setStatus],
  )
  const play = useCallback(
    (id: string, time = 0, mode: 'manual' | 'automatic' | null = 'manual') => begin(id, time, mode),
    [begin],
  )
  const cueAt = useCallback(
    (ownerByte: number) => {
      if (muted.current || document.hidden) return
      const id = cueOwners.get(ownerByte) || null
      if (id !== target.current) {
        clearTarget()
        target.current = id
      }
      if (!id || cueSeen.current.has(id)) return
      // A playing manual reading/line always wins. Only the still-current
      // paragraph may follow its natural end; a pause/stop/jump drops it.
      if (pointer.current && !creative.current && statusRef.current !== 'failed') {
        if (statusRef.current === 'playing') waiting.current = id
        return
      }
      begin(id, 0, 'creative')
    },
    [begin, clearTarget, cueOwners],
  )
  const enableCueSound = useCallback(
    (stillVisible?: ReadonlySet<string>) => {
      const id = blocked.current
      if (!id || id !== target.current || muted.current || document.hidden) return
      // A layout change or scroll can precede its scheduled scroll handler.
      // Recheck the actual viewport before playing from the permission action.
      if (stillVisible && !stillVisible.has(id)) {
        clearTarget()
        return
      }
      blocked.current = null
      setCueBlocked(false)
      begin(id, 0, 'creative')
    },
    [begin, clearTarget],
  )
  const resetCueVisit = useCallback(() => {
    clearTarget()
    cueSeen.current.clear()
  }, [clearTarget])
  const setCueMuted = useCallback(
    (next: boolean) => {
      const changed = next !== muted.current
      muted.current = next
      if (element.current) element.current.muted = next
      if (changed && next) suspend()
    },
    [suspend],
  )
  const restore = useCallback(
    (p: AudioPoint) => {
      stop()
      const a = element.current
      if (
        !p ||
        !a ||
        !data.media[p.id] ||
        (!passages.current.has(p.id) && !clips.current.some((c) => c.take_id === p.id))
      )
        return
      a.src = data.media[p.id].url
      a.currentTime = Number.isFinite(p.time) ? Math.max(0, p.time) : 0
      pointer.current = { id: p.id, time: a.currentTime }
      seen.current.add(p.id)
      setCurrent(p.id)
      setStatus('paused')
    },
    [data.media, stop, setStatus],
  )
  const resume = useCallback(() => {
    const p = playbackPoint()
    if (p) play(p.id, p.time)
  }, [play, playbackPoint])
  const autoAt = useCallback(
    (previous: number, byte: number, visibleIds: Set<string>, token: number) => {
      if (!automaticRef.current || generation.current !== token || byte <= previous) return
      if (pointer.current && passages.current.has(pointer.current.id)) return
      visible.current = visibleIds
      const clip = automaticClip(clips.current, seen.current, visibleIds, previous, byte)
      if (!clip) return
      // Natural reading never interrupts the current line. Remember a visible
      // crossed line for its end, without queueing skipped or already heard lines.
      if (statusRef.current === 'playing') {
        if (queue.current === 'automatic') pending.current = clip.take_id
      } else play(clip.take_id, 0, 'automatic')
    },
    [play],
  )
  const leave = useCallback(
    (visibleIds: Set<string>, skip = false) => {
      visible.current = visibleIds
      if (target.current && (skip || !visibleIds.has(target.current))) clearTarget()
      if (pending.current && !visibleIds.has(pending.current)) pending.current = null
      // The source paragraph's top is not the viewport: a line can still be on
      // screen after the reading anchor advances into the following paragraph.
      if (pointer.current && (skip || !visibleIds.has(pointer.current.id))) stop()
    },
    [clearTarget, stop],
  )
  const ended = useCallback(() => {
    const id = pointer.current?.id,
      mode = queue.current
    // Ignore an old source's queued ended event after a jump or a new play.
    if (!id || statusRef.current !== 'playing' || !element.current?.ended) return
    const block = data.blocks.find((b) => b.audio.some((c) => c.take_id === id))
    const next =
      mode && block && (mode !== 'automatic' || automaticRef.current)
        ? nextDialogue(
            block.audio,
            id,
            visible.current,
            mode === 'automatic' ? seen.current : undefined,
          )
        : null
    const follow =
      mode === 'automatic' &&
      automaticRef.current &&
      pending.current &&
      visible.current?.has(pending.current) &&
      !seen.current.has(pending.current)
        ? pending.current
        : null
    if (next || follow) {
      // A reader-chosen same-paragraph sequence is not interrupted between
      // lines. Preserve at most one current accent through its continuation.
      const deferred = waiting.current
      if (next) play(next.take_id, 0, mode)
      else if (follow) play(follow, 0, 'automatic')
      if (deferred) target.current = waiting.current = deferred
    } else {
      const deferred = waiting.current
      waiting.current = null
      creative.current = false
      pointer.current = null
      queue.current = null
      pending.current = null
      setCurrent(null)
      setStatus('idle')
      if (deferred && target.current === deferred && !cueSeen.current.has(deferred))
        begin(deferred, 0, 'creative')
    }
  }, [begin, data.blocks, play, setStatus])
  useEffect(() => {
    const hide = () => {
      if (document.hidden) suspend()
    }
    document.addEventListener('visibilitychange', hide)
    if (typeof window !== 'undefined') window.addEventListener('pagehide', suspend)
    return () => {
      document.removeEventListener('visibilitychange', hide)
      if (typeof window !== 'undefined') window.removeEventListener('pagehide', suspend)
      generation.current++
      element.current?.pause()
    }
  }, [suspend])
  return {
    element,
    automatic,
    setAutomatic,
    cueAt,
    cueBlocked,
    interruptCue,
    enableCueSound,
    setCueMuted,
    resetCueVisit,
    current,
    status,
    notice,
    setNotice,
    play,
    stop,
    suspend,
    restore,
    point,
    resume,
    autoAt,
    leave,
    revision: () => generation.current,
    ended,
    failed: () => {
      if (pointer.current && element.current?.error) {
        generation.current++
        queue.current = null
        pending.current = null
        setStatus('failed')
        setNotice('声音不可用，可重试或继续阅读。')
      }
    },
  }
}
