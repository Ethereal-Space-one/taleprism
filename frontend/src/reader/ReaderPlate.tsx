import { useId, useRef } from 'react'
import type { ReaderContent, ReaderIllustration } from '../reader-types'
import type { ImageRequest } from './imageRecovery'
import { ReaderImageRetry } from './ReaderImageRetry'
import { ReaderPlateMotion } from './ReaderPlateMotion'
import type { EnvironmentMotionRecipe } from './motion/recipes'

export function ReaderPlate({
  plate,
  asset,
  sourceByte,
  displayAfterByte,
  visualDescription,
  request,
  motionRecipe,
  motionArmed = false,
  motionSeen,
  onLoad,
  onRetry,
  onError,
  onOpen,
}: {
  plate: ReaderIllustration
  asset?: ReaderContent['media'][string]
  sourceByte: number
  displayAfterByte?: number
  visualDescription?: string | null
  request?: ImageRequest
  motionRecipe?: EnvironmentMotionRecipe | null
  motionArmed?: boolean
  motionSeen?: Set<string>
  onLoad: () => void
  onRetry: () => void
  onError: () => void
  onOpen: () => void
}) {
  const descriptionId = useId()
  const art = useRef<HTMLButtonElement>(null),
    image = useRef<HTMLImageElement>(null)
  const description = visualDescription || plate.description || plate.title
  const failed = request?.status === 'failed'
  return (
    <figure
      className="reader-plate"
      data-illustration-id={plate.id}
      data-source-byte={sourceByte}
      data-display-after-byte={displayAfterByte ?? plate.after_byte}
      data-image-asset={plate.image_asset_id}
    >
      <button
        ref={art}
        className="reader-plate-art"
        data-illustration-anchor="true"
        data-auto-motion={motionRecipe && asset && !failed ? plate.id : undefined}
        aria-label={`放大插图：${plate.title}`}
        aria-describedby={descriptionId}
        onClick={onOpen}
        disabled={!asset || failed}
        style={{ aspectRatio: `${asset?.width || 16} / ${asset?.height || 9}` }}
      >
        {asset && !failed ? (
          <img
            ref={image}
            key={`${asset.id}:${request?.attempt || 0}`}
            src={asset.url}
            alt={description}
            width={asset.width}
            height={asset.height}
            loading={request?.attempt ? 'eager' : 'lazy'}
            decoding="async"
            onLoad={onLoad}
            onError={onError}
          />
        ) : (
          <span>这幅插图暂不可用，正文仍可阅读。</span>
        )}
        {asset && !failed && motionArmed && motionSeen && motionRecipe && (
          <ReaderPlateMotion
            key={`motion:${asset.id}:${request?.attempt || 0}`}
            recipe={motionRecipe}
            seen={motionSeen}
            art={art}
            image={image}
          />
        )}
      </button>
      <span id={descriptionId} hidden>
        {description}
      </span>
      <figcaption>
        <span>{plate.title}</span>
        <span className="reader-plate-actions">
          <ReaderImageRetry request={request} label={`插图：${plate.title}`} onRetry={onRetry} />
          <button onClick={onOpen} disabled={!asset || failed} aria-describedby={descriptionId}>
            展开画面 ↗
          </button>
        </span>
      </figcaption>
    </figure>
  )
}
