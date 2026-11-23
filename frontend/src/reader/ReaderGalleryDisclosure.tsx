import { useState, type ReactNode } from 'react'

function focusWholeGallery(heading: HTMLHeadingElement | null) {
  heading?.focus()
  heading?.closest('.reader-dialog-body')?.scrollTo(0, 0)
}

/** Whole-gallery permission is local to this panel, never reading progress. */
export function ReaderGalleryDisclosure({
  totalCount,
  reachedCount,
  onCancel,
  children,
}: {
  totalCount: number
  reachedCount: number
  onCancel: () => void
  children: (whole: boolean) => ReactNode
}) {
  const [revealed, setRevealed] = useState(false)
  // All placed illustrations have a source boundary, even without a story graph.
  // When nothing is ahead there is no consent to ask for or carry to the lightbox.
  if (reachedCount === totalCount) return children(false)
  if (revealed)
    return (
      <section className="reader-gallery-full" aria-labelledby="reader-gallery-full-title">
        <h3 id="reader-gallery-full-title" tabIndex={-1} ref={focusWholeGallery}>
          全章插图
        </h3>
        {children(true)}
      </section>
    )
  return (
    <div className="reader-gallery-bounded">
      <section aria-labelledby="reader-gallery-reached-title">
        <h3 id="reader-gallery-reached-title">读到这里的画面 · {reachedCount} 幅</h3>
        <p>仅展示当前正文位置及之前的插图，不改变续读位置。</p>
        {reachedCount === 0 && <p>当前位置还没有可回看的插图。继续阅读，画面会随正文展开。</p>}
      </section>
      {reachedCount > 0 && children(false)}
      <section
        className="reader-image-disclosure"
        aria-labelledby="reader-gallery-disclosure-title"
      >
        <h3 id="reader-gallery-disclosure-title">全章画卷含后文画面与标题</h3>
        <p>查看会提前看到尚未读到的场景。仅本次浏览有效，不会改变阅读或续读位置。</p>
        <div>
          <button className="reader-primary" onClick={onCancel}>
            返回
          </button>
          <button onClick={() => setRevealed(true)}>查看全章画卷（含后文）</button>
        </div>
      </section>
    </div>
  )
}
