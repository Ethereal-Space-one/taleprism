export const MAX_IMAGE_RETRIES = 3
export type ImageRequest = { attempt: number; status: 'loading' | 'ready' | 'failed' }
export type ImageRequests = Record<string, ImageRequest>
export type ImageAction =
  | { type: 'retry'; id: string }
  | { type: 'loaded' | 'failed'; id: string; attempt: number }

// No timers or automatic retries. Stale load/error events cannot finish a newer request.
export function imageRecoveryReducer(state: ImageRequests, action: ImageAction): ImageRequests {
  const before = state[action.id] || { attempt: 0, status: 'loading' as const }
  if (action.type === 'retry') {
    if (before.status !== 'failed' || before.attempt >= MAX_IMAGE_RETRIES) return state
    return { ...state, [action.id]: { attempt: before.attempt + 1, status: 'loading' } }
  }
  if (action.attempt !== before.attempt || before.status === 'failed') return state
  const status = action.type === 'loaded' ? 'ready' : 'failed'
  if (before.status === status) return state
  return { ...state, [action.id]: { ...before, status } }
}
export function imageRetryUrl(url: string, attempt: number) {
  if (!attempt) return url
  // Only our ordinary local media URLs get a cache-buster. Do not alter remote
  // signed URLs, data URLs, or send reading positions to another service.
  if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(url)) return url
  const [path, hash] = url.split('#', 2)
  return `${path}${path.includes('?') ? '&' : '?'}taleprism_retry=${attempt}${hash ? `#${hash}` : ''}`
}
