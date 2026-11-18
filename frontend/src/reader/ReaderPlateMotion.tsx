import { useEffect, useRef, type RefObject } from 'react'
import type { EnvironmentMotionRecipe } from './motion/recipes'
import { startEnvironmentMotion } from './motion/runtime'

/** Decorative transparent pixels only. The original image owns layout, focus,
 * click-to-expand, alternative text and reading/bookmark position throughout. */
export function ReaderPlateMotion({
  recipe,
  seen,
  art,
  image,
}: {
  recipe: EnvironmentMotionRecipe
  seen: Set<string>
  art: RefObject<HTMLButtonElement | null>
  image: RefObject<HTMLImageElement | null>
}) {
  const canvas = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const key = 'inline:' + recipe.plateId
    if (seen.has(key) || !art.current || !image.current || !canvas.current) return
    return startEnvironmentMotion(
      image.current,
      canvas.current,
      art.current,
      recipe,
      () => seen.add(key),
      undefined,
      undefined,
      'inline-once',
    )
  }, [recipe, seen, art, image])
  return (
    <canvas
      ref={canvas}
      className="reader-image-motion reader-inline-motion"
      data-motion-effect={recipe.effect}
      hidden
      aria-hidden="true"
    />
  )
}
