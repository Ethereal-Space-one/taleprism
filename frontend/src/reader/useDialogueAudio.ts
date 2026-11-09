import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReaderContent } from '../reader-types'
export type AudioPoint = { id: string; time: number } | null
export function useDialogueAudio(data: ReaderContent) {
  const element = useRef<HTMLAudioElement>(null)
  const [automatic, setAutomatic] = useState(false)
  const [current, setCurrent] = useState<string | null>(null)
  const [status, setStatus] = useState<'idle' | 'playing' | 'paused' | 'failed'>('idle')
  const [notice, setNotice] = useState('')
  const generation = useRef(0),
    seen = useRef(new Set<string>()),
    nextAllowed = useRef(true)
  const clips = useRef(data.blocks.flatMap((b) => b.audio))
  const pointer = useRef<AudioPoint>(null)
  const point = useCallback(
    (): AudioPoint =>
      pointer.current
        ? { id: pointer.current.id, time: element.current?.currentTime || pointer.current.time }
        : null,
    [],
  )
  const suspend = useCallback(() => {
    generation.current++
    element.current?.pause()
    if (pointer.current) {
      pointer.current = point()
      setStatus('paused')
    }
    nextAllowed.current = false
  }, [point])
  const stop = useCallback(() => {
    suspend()
    pointer.current = null
    setCurrent(null)
    setStatus('idle')
    element.current?.removeAttribute('src')
    element.current?.load()
  }, [suspend])
  const play = useCallback(
    (id: string, time = 0, allowQueue = true) => {
      const a = element.current,
        clip = clips.current.find((c) => c.take_id === id)
      if (!a || !clip || !data.media[id]) return
      const token = ++generation.current
      a.pause()
      a.src = data.media[id].url
      a.currentTime = time
      pointer.current = { id, time }
      nextAllowed.current = allowQueue
      seen.current.add(id)
      setCurrent(id)
      setStatus('playing')
      setNotice('')
      a.play().catch(() => {
        if (generation.current === token) {
          setStatus('failed')
          setNotice('声音暂未播放，可重试；正文可以继续阅读。')
        }
      })
    },
    [data.media],
  )
  const restore = useCallback(
    (p: AudioPoint) => {
      suspend()
      const a = element.current
      if (!p || !a || !data.media[p.id]) {
        pointer.current = null
        setCurrent(null)
        setStatus('idle')
        return
      }
      a.src = data.media[p.id].url
      a.currentTime = p.time
      pointer.current = p
      setCurrent(p.id)
      setStatus('paused')
    },
    [data.media, suspend],
  )
  const resume = useCallback(() => {
    const p = point()
    if (p) play(p.id, p.time)
  }, [play, point])
  const autoAt = useCallback(
    (previous: number, byte: number) => {
      if (!automatic || status === 'playing' || byte <= previous) return
      const clip = clips.current.find(
        (c) => c.byte_start > previous && c.byte_start <= byte && !seen.current.has(c.take_id),
      )
      if (clip) play(clip.take_id)
    },
    [automatic, status, play],
  )
  const leave = useCallback(
    (byte: number) => {
      if (!pointer.current) return
      const block = data.blocks.find((b) => b.audio.some((c) => c.take_id === pointer.current?.id))
      if (block && !(block.byte_start <= byte && byte < block.byte_end)) stop()
    },
    [data.blocks, stop],
  )
  const ended = useCallback(() => {
    const id = pointer.current?.id
    const b = data.blocks.find((b) => b.audio.some((c) => c.take_id === id)),
      index = b?.audio.findIndex((c) => c.take_id === id) ?? -1
    if (nextAllowed.current && b && b.audio[index + 1]) play(b.audio[index + 1].take_id)
    else {
      pointer.current = null
      setCurrent(null)
      setStatus('idle')
    }
  }, [data.blocks, play])
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
    ended,
    failed: () => {
      if (pointer.current) {
        setStatus('failed')
        setNotice('声音不可用，可重试或继续阅读。')
      }
    },
  }
}
