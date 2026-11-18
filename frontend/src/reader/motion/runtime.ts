import { validMotionRecipe, type EnvironmentMotionRecipe } from './recipes'
import { createMotionRenderer } from './render'

/** The actual pixels inside a centered object-fit: contain image element. */
export function containedImageBounds(
  width: number,
  height: number,
  naturalWidth: number,
  naturalHeight: number,
) {
  if (![width, height, naturalWidth, naturalHeight].every((n) => Number.isFinite(n) && n > 0))
    return null
  const scale = Math.min(width / naturalWidth, height / naturalHeight)
  const w = naturalWidth * scale,
    h = naturalHeight * scale
  return { left: (width - w) / 2, top: (height - h) / 2, width: w, height: h }
}

export function supportsEnvironmentMotion() {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    typeof ResizeObserver !== 'undefined' &&
    typeof IntersectionObserver !== 'undefined' &&
    typeof requestAnimationFrame === 'function' &&
    typeof cancelAnimationFrame === 'function'
  )
}

/**
 * Owns all resources for one plate. The expanded viewer explicitly opts in;
 * the inline reader is armed only by the reading conductor at a bound cue.
 * Missing platform capabilities fail static rather than assuming visibility.
 */
export function startEnvironmentMotion(
  image: HTMLImageElement,
  canvas: HTMLCanvasElement,
  viewport: HTMLElement,
  recipe: EnvironmentMotionRecipe,
  onFirstFrame?: () => void,
  onReviewCycle?: () => void,
  onReviewSecond?: (seconds: number) => void,
  playback: 'expanded' | 'inline-once' = 'expanded',
): () => void {
  canvas.hidden = true
  if (!supportsEnvironmentMotion() || !validMotionRecipe(recipe)) return () => {}
  let ctx: CanvasRenderingContext2D | null
  try {
    ctx = canvas.getContext('2d')
  } catch {
    return () => {}
  }
  if (!ctx) return () => {}
  const context = ctx
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
  // Older media-query APIs deliberately keep the static reader.
  if (
    typeof reduced.addEventListener !== 'function' ||
    typeof reduced.removeEventListener !== 'function'
  )
    return () => {}
  const inline = playback === 'inline-once'
  if (inline && (document.hidden || reduced.matches)) return () => {}
  const render = createMotionRenderer(context, recipe)
  let disposed = false,
    failed = false,
    visible = false,
    frame = 0
  let reported = false
  let cycleReported = false,
    reportedSecond = -1
  let width = 0,
    height = 0,
    seconds = 0,
    last: number | null = null,
    began: number | null = null
  const imageReady = () =>
    image.complete && image.naturalWidth === recipe.width && image.naturalHeight === recipe.height
  const eligible = () =>
    !disposed &&
    !failed &&
    visible &&
    !document.hidden &&
    !reduced.matches &&
    image.isConnected &&
    viewport.isConnected &&
    imageReady() &&
    width > 0 &&
    height > 0
  const stop = () => {
    if (frame) cancelAnimationFrame(frame)
    frame = 0
    last = null
    canvas.hidden = true
    context.clearRect(0, 0, canvas.width, canvas.height)
  }
  const draw = (now: number) => {
    frame = 0
    if (!eligible()) {
      if (inline && reported) dispose()
      else stop()
      return
    }
    if (inline) {
      began ??= now
      // One quiet eight-second encounter, measured in wall time even on a slow
      // device. Fade the overlay, never the still, and never restart it on return.
      seconds = (now - began) / 1000
      if (seconds >= 8) {
        dispose()
        return
      }
      canvas.style.opacity = String(Math.min(1, (seconds + 0.02) / 0.3, (8 - seconds) / 0.7))
    } else if (last !== null) seconds += Math.min(0.05, Math.max(0, (now - last) / 1000))
    last = now
    try {
      render(seconds, width, height)
      if (!reported) {
        reported = true
        onFirstFrame?.()
      }
      const wholeSecond = Math.min(8, Math.floor(seconds))
      if (onReviewSecond && wholeSecond !== reportedSecond) {
        reportedSecond = wholeSecond
        onReviewSecond(wholeSecond)
      }
      if (!cycleReported && seconds >= 8) {
        cycleReported = true
        onReviewCycle?.()
      }
    } catch {
      failed = true
      if (inline) dispose()
      else stop()
      return
    }
    if (!disposed) frame = requestAnimationFrame(draw)
  }
  const sync = () => {
    if (disposed) return
    if (!eligible()) {
      if (inline && (reported || reduced.matches || document.hidden)) dispose()
      else stop()
      return
    }
    canvas.hidden = false
    if (!frame) frame = requestAnimationFrame(draw)
  }
  const resize = () => {
    if (disposed) return
    width = height = 0
    if (imageReady()) {
      const rect = image.getBoundingClientRect(),
        parent = viewport.getBoundingClientRect()
      const bounds = containedImageBounds(
        rect.width,
        rect.height,
        image.naturalWidth,
        image.naturalHeight,
      )
      if (bounds) {
        // Image and viewport boxes are not the same in a letterboxed layout.
        canvas.style.left = `${rect.left - parent.left + viewport.scrollLeft - viewport.clientLeft + bounds.left}px`
        canvas.style.top = `${rect.top - parent.top + viewport.scrollTop - viewport.clientTop + bounds.top}px`
        canvas.style.width = `${bounds.width}px`
        canvas.style.height = `${bounds.height}px`
        const density = Math.min(
          window.devicePixelRatio || 1,
          1.5,
          1920 / bounds.width,
          1080 / bounds.height,
        )
        width = Math.max(1, Math.round(bounds.width * density))
        height = Math.max(1, Math.round(bounds.height * density))
        if (canvas.width !== width) canvas.width = width
        if (canvas.height !== height) canvas.height = height
      }
    }
    sync()
  }
  const loaded = () => {
    failed = false
    resize()
  }
  const errored = () => {
    failed = true
    if (inline) dispose()
    else stop()
  }
  const resizeObserver = new ResizeObserver(resize)
  // The reader can render a partial image; creator review needs most of it in view.
  const reviewThreshold = onReviewCycle ? 0.65 : 0
  const intersectionObserver = new IntersectionObserver(
    (entries) => {
      if (disposed) return
      const before = visible
      visible = entries.some(
        (entry) =>
          entry.target === viewport &&
          entry.isIntersecting &&
          entry.intersectionRatio > 0 &&
          entry.intersectionRatio >= reviewThreshold,
      )
      // A slow-loading inline image may not have drawn yet. Leaving its first
      // encounter still expires it: finally decoding on scroll-back is not a cue.
      if (inline && before && !visible) dispose()
      else sync()
    },
    { threshold: reviewThreshold },
  )
  image.addEventListener('load', loaded)
  image.addEventListener('error', errored)
  document.addEventListener('visibilitychange', sync)
  window.addEventListener('resize', resize)
  reduced.addEventListener('change', sync)
  resizeObserver.observe(viewport)
  resizeObserver.observe(image)
  intersectionObserver.observe(viewport)
  resize()
  return dispose
  function dispose() {
    if (disposed) return
    disposed = true
    stop()
    image.removeEventListener('load', loaded)
    image.removeEventListener('error', errored)
    document.removeEventListener('visibilitychange', sync)
    window.removeEventListener('resize', resize)
    reduced.removeEventListener('change', sync)
    resizeObserver.disconnect()
    intersectionObserver.disconnect()
  }
}
