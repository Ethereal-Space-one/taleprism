import { useEffect, useRef } from 'react'
import type { ReaderContent } from '../reader-types'

// A small moving window. No audio requests, API calls, or whole-chapter eager loading.
export function useStagePreload(data: ReaderContent, id: string | undefined, enabled: boolean) {
  const cache = useRef(new Map<string, HTMLImageElement>())
  useEffect(() => {
    if (!enabled) {
      cache.current.clear()
      return
    }
    const index = data.presentations.findIndex((p) => p.id === id)
    if (index < 0) return
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection
    const cues = data.presentations.slice(index, index + (connection?.saveData ? 1 : 3))
    const urls = new Set(
      cues
        .flatMap((p) => [p.image_asset_id, ...p.cast.map((c) => c.figure_asset_id)])
        .map((asset) => data.media[asset]?.url)
        .filter((url): url is string => !!url),
    )
    const timer = window.setTimeout(() => {
      for (const key of cache.current.keys()) if (!urls.has(key)) cache.current.delete(key)
      for (const url of urls) {
        if (cache.current.has(url)) continue
        const image = new Image()
        image.decoding = 'async'
        image.fetchPriority = 'low'
        cache.current.set(url, image)
        image.src = url
        image.decode().catch(() => cache.current.delete(url))
      }
    }, 120)
    return () => window.clearTimeout(timer)
  }, [data, id, enabled])
}
