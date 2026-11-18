import { useEffect, useId, useRef, useState, type RefObject } from 'react'
import type { ReaderNarration } from '../reader-types'

export function voiceTime(seconds: number) {
  const n = Math.max(0, Math.floor(seconds))
  return Math.floor(n / 60) + ':' + String(n % 60).padStart(2, '0')
}

/** A reader can ignore the entire control. No src, preload or new audio element here. */
export function PassageVoice({
  cue,
  paragraph,
  ambience,
  current,
  status,
  element,
  onStart,
  onPause,
  onResume,
  onStop,
}: {
  ambience?: string
  cue: ReaderNarration
  paragraph: number
  current: string | null
  status: 'idle' | 'playing' | 'paused' | 'failed'
  element: RefObject<HTMLAudioElement | null>
  onStart: () => void
  onPause: () => void
  onResume: () => void
  onStop: () => void
}) {
  const active = current === cue.id
  const main = useRef<HTMLButtonElement>(null)
  const durationId = useId()
  const duration = Math.ceil(cue.duration)
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const audio = element.current
    if (!active || !audio) return
    const update = () => setSeconds(Math.floor(audio.currentTime || 0))
    update()
    audio.addEventListener('timeupdate', update)
    return () => audio.removeEventListener('timeupdate', update)
  }, [active, element])
  const playing = active && status === 'playing'
  const paused = active && status === 'paused'
  const failed = active && status === 'failed'
  const kind = ambience ? '声景' : '朗读'
  const action = playing
    ? '暂停' + kind
    : paused
      ? '继续' + kind
      : failed
        ? '重试' + kind
        : ambience
          ? '听此处声景'
          : '听这一段'
  return (
    <div
      className={ambience ? 'reader-passage-voice is-soundscape' : 'reader-passage-voice'}
      aria-label={'第 ' + paragraph + ' 段' + kind}
    >
      <button
        type="button"
        ref={main}
        className="reader-passage-voice-main"
        aria-describedby={durationId}
        aria-label={action + '：第 ' + paragraph + ' 段'}
        onClick={playing ? onPause : paused ? onResume : onStart}
      >
        <span aria-hidden="true">{playing ? 'Ⅱ' : '▷'}</span> {action}
        {ambience && !active && (
          <span className="reader-ambient-caption" aria-hidden="true">
            {' '}
            · {ambience}
          </span>
        )}
        <small aria-hidden="true">
          {active && !failed ? voiceTime(Math.min(cue.duration, seconds)) + ' / ' : ''}
          {voiceTime(duration)}
        </small>
      </button>
      <span id={durationId} hidden>
        {ambience ? ambience + '；合成声景' : '朗读'}时长约 {duration} 秒
        {ambience ? '，播放一次，不会翻页。' : ''}
      </span>
      {active && (
        <button
          type="button"
          onClick={() => {
            onStop()
            main.current?.focus({ preventScroll: true })
          }}
          aria-label={'停止' + kind + '：第 ' + paragraph + ' 段'}
        >
          停止
        </button>
      )}
      {failed && <span role="status">{ambience ? '声景' : '录音'}暂不可用，正文仍可阅读。</span>}
    </div>
  )
}
