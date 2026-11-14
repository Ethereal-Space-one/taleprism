import type { ReaderContent, ReaderIllustration } from '../reader-types'
import type { ImageRequest } from './imageRecovery'
import { ReaderImageRetry } from './ReaderImageRetry'

export function ReaderPlate({
  plate,
  asset,
  sourceByte,
  request,
  onLoad,
  onRetry,
  onError,
  onOpen,
}: {
  plate: ReaderIllustration
  asset?: ReaderContent['media'][string]
  sourceByte: number
  request?: ImageRequest
  onLoad: () => void
  onRetry: () => void
  onError: () => void
  onOpen: () => void
}) {
  const failed = request?.status === 'failed'
  return (
    <figure
      className="reader-plate"
      data-illustration-id={plate.id}
      data-source-byte={sourceByte}
      data-image-asset={plate.image_asset_id}
    >
      <button
        className="reader-plate-art"
        data-illustration-anchor="true"
        aria-label={`放大插图：${plate.title}`}
        onClick={onOpen}
        disabled={!asset || failed}
        style={{ aspectRatio: `${asset?.width || 16} / ${asset?.height || 9}` }}
      >
        {asset && !failed ? (
          <img
            key={`${asset.id}:${request?.attempt || 0}`}
            src={asset.url}
            alt={plate.description || plate.title}
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
      </button>
      <figcaption>
        <span>{plate.title}</span>
        <span className="reader-plate-actions">
          <ReaderImageRetry request={request} label={`插图：${plate.title}`} onRetry={onRetry} />
          <button onClick={onOpen} disabled={!asset || failed}>
            展开画面 ↗
          </button>
        </span>
      </figcaption>
    </figure>
  )
}
