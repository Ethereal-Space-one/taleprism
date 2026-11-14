import { useState } from 'react'
import type { ReaderContent } from '../reader-types'
import { directoryEntries } from './disclosure'

export function ReaderContents({
  data,
  at,
  protectFuture,
  sceneId,
  onVisit,
  onVoices,
}: {
  data: ReaderContent
  at: number
  protectFuture: boolean
  sceneId?: string
  onVisit: (byte: number) => void
  onVoices: () => void
}) {
  const [full, setFull] = useState(false)
  const entries = directoryEntries(data, at, protectFuture, full)
  return (
    <div className="reader-contents">
      {protectFuture && (
        <div className="reader-disclosure-controls">
          <p className="reader-muted">
            {full
              ? '完整目录含后文标题。查看目录不会改变阅读位置。'
              : '按当前阅读位置展开标题。后文章节与场景仍可点选跳读。'}
          </p>
          <button aria-pressed={full} onClick={() => setFull((value) => !value)}>
            {full ? '按当前阅读位置显示' : '查看完整目录（含后文标题）'}
          </button>
        </div>
      )}
      {entries.chapters.map((chapter) => (
        <button key={chapter.id} onClick={() => onVisit(chapter.byte)}>
          {chapter.title}
        </button>
      ))}
      <h3>场景</h3>
      {entries.scenes.map((scene) => (
        <button
          key={scene.id}
          onClick={() => onVisit(scene.byte)}
          aria-current={scene.id === sceneId ? 'location' : undefined}
        >
          {scene.title}
          <span>→</span>
        </button>
      ))}
      <button onClick={onVoices}>本章对白</button>
    </div>
  )
}
