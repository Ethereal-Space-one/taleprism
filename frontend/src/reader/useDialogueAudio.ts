import { useCallback, useEffect, useRef, useState, type SetStateAction } from 'react'
import type { ReaderContent } from '../reader-types'
import { automaticClip, nextDialogue } from './readingSession'
export type AudioPoint = { id: string; time: number } | null
export function useDialogueAudio(data: ReaderContent) {
  const element = useRef<HTMLAudioElement>(null)
  const [automatic, updateAutomatic] = useState(false)
  const [current, setCurrent] = useState<string | null>(null)
  const [status, updateStatus] = useState<'idle' | 'playing' | 'paused' | 'failed'>('idle')
  const [notice, setNotice] = useState('')
  const generation = useRef(0),
    seen = useRef(new Set<string>()),
    queue = useRef<'manual' | 'automatic' | null>(null),
    pending = useRef<string | null>(null),
    visible = useRef<Set<string> | null>(null),
    automaticRef = useRef(false),
    statusRef = useRef(status)
  const clips = useRef(data.blocks.flatMap((b) => b.audio))
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
  const point = useCallback(
    (): AudioPoint =>
      pointer.current
        ? { id: pointer.current.id, time: element.current?.currentTime ?? pointer.current.time }
        : null,
    [],
  )
  const suspend = useCallback(() => {
    generation.current++
    queue.current = null
    pending.current = null
    element.current?.pause()
    if (pointer.current) {
      pointer.current = point()
      setStatus('paused')
    }
  }, [point, setStatus])
  const stop = useCallback(() => {
    suspend()
    pointer.current = null
    setCurrent(null)
    setStatus('idle')
    element.current?.removeAttribute('src')
    element.current?.load()
  }, [suspend, setStatus])
  const play = useCallback(
    (id: string, time = 0, mode: 'manual' | 'automatic' | null = 'manual') => {
      const a = element.current,
        clip = clips.current.find((c) => c.take_id === id)
      if (!a || !clip || !data.media[id]) return
      const token = ++generation.current
      a.pause()
      a.src = data.media[id].url
      a.currentTime = Number.isFinite(time) ? Math.max(0, time) : 0
      pointer.current = { id, time: a.currentTime }
      queue.current = mode
      if (mode === 'manual') visible.current = null
      pending.current = null
      seen.current.add(id)
      setCurrent(id)
      setStatus('playing')
      setNotice('')
      a.play().catch(() => {
        if (generation.current === token) {
          queue.current = null
          pending.current = null
          setStatus('failed')
          setNotice('声音暂未播放，可重试；正文可以继续阅读。')
        }
      })
    },
    [data.media, setStatus],
  )
  const restore = useCallback(
    (p: AudioPoint) => {
      stop()
      const a = element.current
      if (!p || !a || !data.media[p.id] || !clips.current.some((c) => c.take_id === p.id)) return
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
    const p = point()
    if (p) play(p.id, p.time)
  }, [play, point])
  const autoAt = useCallback(
    (previous: number, byte: number, visibleIds: Set<string>, token: number) => {
      if (!automaticRef.current || generation.current !== token || byte <= previous) return
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
      if (pending.current && !visibleIds.has(pending.current)) pending.current = null
      // The source paragraph's top is not the viewport: a line can still be on
      // screen after the reading anchor advances into the following paragraph.
      if (pointer.current && (skip || !visibleIds.has(pointer.current.id))) stop()
    },
    [stop],
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
    if (next) play(next.take_id, 0, mode)
    else if (follow) play(follow, 0, 'automatic')
    else {
      pointer.current = null
      queue.current = null
      pending.current = null
      setCurrent(null)
      setStatus('idle')
    }
  }, [data.blocks, play, setStatus])
  useEffect(() => {
    const hide = () => {
      if (document.hidden) suspend()
    }
    document.addEventListener('visibilitychange', hide)
    return () => {
      document.removeEventListener('visibilitychange', hide)
      generation.current++
      element.current?.pause()
    }
  }, [suspend])
  return {
    element,
    automatic,
    setAutomatic,
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
