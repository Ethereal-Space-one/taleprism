import { MAX_IMAGE_RETRIES, type ImageRequest } from './imageRecovery'

export function ReaderImageRetry({
  request,
  onRetry,
  label,
}: {
  request?: ImageRequest
  onRetry: () => void
  label: string
}) {
  if (
    !request ||
    request.status === 'ready' ||
    (request.attempt === 0 && request.status === 'loading')
  )
    return null
  if (request.status === 'loading')
    return (
      <span className="reader-image-recovery" role="status">
        正在重新载入画面…
      </span>
    )
  return (
    <span className="reader-image-recovery">
      {request.attempt < MAX_IMAGE_RETRIES ? (
        <button onClick={onRetry} aria-label={`重试${label}`}>
          重试画面{request.attempt ? ` · ${request.attempt}/${MAX_IMAGE_RETRIES}` : ''}
        </button>
      ) : (
        <span role="status">已重试 {MAX_IMAGE_RETRIES} 次，可稍后重新打开本卷。</span>
      )}
    </span>
  )
}
