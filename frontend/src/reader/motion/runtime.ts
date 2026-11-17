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
 * Owns every listener, observer and RAF for ONE expanded image. Its caller only
 * mounts this when opted in, unzoomed and not awaiting spoiler disclosure.
 * Missing platform capabilities fail static rather than assuming visibility.
 */
export function startEnvironmentMotion(
  image: HTMLImageElement,
  canvas: HTMLCanvasElement,
  viewport: HTMLDivElement,
  recipe: EnvironmentMotionRecipe,
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
  const render = createMotionRenderer(context, recipe)
  let disposed = false,
    failed = false,
    visible = false,
    frame = 0
  let width = 0,
    height = 0,
    seconds = 0,
    last: number | null = null
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
      stop()
      return
    }
    if (last !== null) seconds += Math.min(0.05, Math.max(0, (now - last) / 1000))
    last = now
    try {
      render(seconds, width, height)
    } catch {
      failed = true
      stop()
      return
    }
    frame = requestAnimationFrame(draw)
  }
  const sync = () => {
    if (!eligible()) {
      stop()
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
    stop()
  }
  const resizeObserver = new ResizeObserver(resize)
  const intersectionObserver = new IntersectionObserver((entries) => {
    if (disposed) return
    visible = entries.some(
      (entry) => entry.target === viewport && entry.isIntersecting && entry.intersectionRatio > 0,
    )
    sync()
  })
  image.addEventListener('load', loaded)
  image.addEventListener('error', errored)
  document.addEventListener('visibilitychange', sync)
  window.addEventListener('resize', resize)
  reduced.addEventListener('change', sync)
  resizeObserver.observe(viewport)
  resizeObserver.observe(image)
  intersectionObserver.observe(viewport)
  resize()
  return () => {
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
