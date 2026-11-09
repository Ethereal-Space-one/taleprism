import type { ReaderContent, ReaderIllustration } from '../reader-types'

export function ReaderPlate({
  plate,
  asset,
  sourceByte,
  failed,
  onError,
  onOpen,
}: {
  plate: ReaderIllustration
  asset?: ReaderContent['media'][string]
  sourceByte: number
  failed: boolean
  onError: () => void
  onOpen: () => void
}) {
  return (
    <figure className="reader-plate" data-illustration-id={plate.id} data-source-byte={sourceByte}>
      <button
        className="reader-plate-art"
        aria-label={`放大插图：${plate.title}`}
        onClick={onOpen}
        disabled={!asset || failed}
        style={{ aspectRatio: `${asset?.width || 16} / ${asset?.height || 9}` }}
      >
        {asset && !failed ? (
          <img
            src={asset.url}
            alt={plate.description || plate.title}
            width={asset.width}
            height={asset.height}
            loading="lazy"
            decoding="async"
            onError={onError}
          />
        ) : (
          <span>这幅插图暂不可用，正文仍可阅读。</span>
        )}
      </button>
      <figcaption>
        <span>{plate.title}</span>
        <button onClick={onOpen} disabled={!asset || failed}>
          展开画面 ↗
        </button>
      </figcaption>
    </figure>
  )
}
