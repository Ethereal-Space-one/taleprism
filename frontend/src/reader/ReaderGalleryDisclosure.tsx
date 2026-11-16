import { useState, type ReactNode } from 'react'

/** Whole-gallery permission is local to this panel, never reading progress. */
export function ReaderGalleryDisclosure({
  protectFuture,
  onCancel,
  children,
}: {
  protectFuture: boolean
  onCancel: () => void
  children: () => ReactNode
}) {
  const [revealed, setRevealed] = useState(false)
  if (!protectFuture || revealed) return children()
  return (
    <section className="reader-image-disclosure" aria-labelledby="reader-gallery-disclosure-title">
      <h3 id="reader-gallery-disclosure-title">全章画卷含后文画面与标题</h3>
      <p>查看会提前看到尚未读到的场景。仅本次浏览有效，不会改变阅读或续读位置。</p>
      <div>
        <button className="reader-primary" onClick={onCancel}>
          取消
        </button>
        <button onClick={() => setRevealed(true)}>查看全章画卷（含后文）</button>
      </div>
    </section>
  )
}
