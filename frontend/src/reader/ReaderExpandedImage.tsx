import { useEffect, useRef, useState, type RefObject } from 'react'
import type { EnvironmentMotionRecipe } from './motion/recipes'
import { startEnvironmentMotion, supportsEnvironmentMotion } from './motion/runtime'

/** Only this viewer can opt into local motion. Inline plates and gallery stay static. */
export function ReaderExpandedImage({
  viewportRef,
  src,
  alt,
  describedBy,
  zoomed,
  pending,
  recipe,
  onLoad,
  onError,
}: {
  viewportRef: RefObject<HTMLDivElement | null>
  src: string
  alt: string
  describedBy?: string
  zoomed: boolean
  pending: boolean
  recipe: EnvironmentMotionRecipe | null
  onLoad: () => void
  onError: () => void
}) {
  const image = useRef<HTMLImageElement>(null),
    canvas = useRef<HTMLCanvasElement>(null)
  // Opt-in belongs to this expanded image visit, never the reading record.
  const [enabled, setEnabled] = useState(false)
  const [supported, setSupported] = useState(false),
    [reduced, setReduced] = useState(true)
  useEffect(() => {
    if (!supportsEnvironmentMotion()) return
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (
      typeof media.addEventListener !== 'function' ||
      typeof media.removeEventListener !== 'function'
    )
      return
    setSupported(true)
    const update = () => {
      setReduced(media.matches)
      // Returning from reduced motion never silently re-enables animation.
      if (media.matches) setEnabled(false)
    }
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  useEffect(() => {
    if (
      !recipe ||
      !enabled ||
      reduced ||
      zoomed ||
      pending ||
      !image.current ||
      !canvas.current ||
      !viewportRef.current
    )
      return
    return startEnvironmentMotion(image.current, canvas.current, viewportRef.current, recipe)
  }, [recipe, enabled, reduced, zoomed, pending, src, viewportRef])
  return (
    <>
      <div
        ref={viewportRef}
        className={`reader-image-viewport ${zoomed ? 'is-zoomed' : ''}`}
        tabIndex={0}
        aria-label={zoomed ? '插图细节，可横向和纵向移动' : '完整插图'}
        aria-describedby={describedBy}
      >
        <img
          ref={image}
          className="reader-expanded-image"
          src={src}
          alt={alt}
          onLoad={onLoad}
          onError={onError}
        />
        {recipe && (
          <canvas ref={canvas} className="reader-image-motion" hidden aria-hidden="true" />
        )}
      </div>
      {recipe && (
        <div className="reader-motion-controls">
          <button
            type="button"
            aria-pressed={enabled && !reduced}
            disabled={!supported || reduced || zoomed || pending}
            onClick={() => setEnabled((value) => !value)}
          >
            {enabled && !reduced ? '关闭动效' : '开启动效'}
          </button>
          <span>
            {!supported
              ? '当前浏览器显示原图'
              : reduced
                ? '已按系统偏好保持静止'
                : zoomed
                  ? '放大时保持静止'
                  : '仅此幅展开画面 · 环境动效'}
          </span>
        </div>
      )}
    </>
  )
}
