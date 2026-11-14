import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from './api'
import './bundle-backup.css'

type Preflight = {
  can_export: boolean
  uncompressed_bytes: number
  limits: { uncompressed_bytes: number }
  media_files: number
  largest_media: { path: string; bytes: number }[]
  missing_files: string[]
  errors: string[]
}

function megabytes(bytes: number) {
  if (bytes === 0) return '0 MB'
  if (bytes < 100_000) return '< 0.1 MB'
  return (bytes / 1_000_000).toLocaleString('zh-CN', { maximumFractionDigits: 1 }) + ' MB'
}

export function BundleBackup({ prefix, disabled }: { prefix: string; disabled: boolean }) {
  const [open, setOpen] = useState(false)
  const status = useQuery({
    queryKey: ['bundle-preflight', prefix],
    queryFn: () => api<Preflight>(prefix + '/bundle/preflight'),
    enabled: open && !disabled,
    staleTime: 0,
    gcTime: 0,
  })
  const download = useMutation({
    mutationFn: async () => {
      const response = await fetch(prefix + '/bundle')
      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw Error(
          typeof payload?.detail === 'string' ? payload.detail : '备份未能完成，请稍后重新检查。',
        )
      }
      return response.blob()
    },
    onSuccess: (file) => {
      const url = URL.createObjectURL(file)
      const link = document.createElement('a')
      link.href = url
      link.download = 'taleprism-project.zip'
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 30_000)
    },
  })
  const result = status.data
  return (
    <details className="bundle-backup" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>备份可编辑工程</summary>
      {disabled ? (
        <p className="asset-helper">先保存修改或等当前操作结束，再检查备份。</p>
      ) : status.isFetching || status.isPending ? (
        <p role="status">正在检查工程大小与素材…</p>
      ) : status.error ? (
        <p className="error" role="alert">
          {status.error.message}
        </p>
      ) : (
        result && (
          <div className="bundle-backup-content">
            <p className="bundle-backup-size">
              <strong>{megabytes(result.uncompressed_bytes)}</strong>
              <span>
                {' '}
                / {megabytes(result.limits.uncompressed_bytes)} · {result.media_files} 个素材文件
              </span>
            </p>
            {result.can_export ? (
              <p>大小与素材路径检查通过。下载时还会校验内容和可恢复性。</p>
            ) : (
              <>
                <p className="error" role="alert">
                  目前不能导出可编辑工程。原工程未改动。
                </p>
                <ul>
                  {result.errors.map((error) => (
                    <li key={error}>{error}</li>
                  ))}
                </ul>
                {result.missing_files.length > 0 && (
                  <details>
                    <summary>缺失素材（{result.missing_files.length}）</summary>
                    <ul>
                      {result.missing_files.map((path) => (
                        <li key={path}>
                          <code>{path}</code>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                {result.largest_media.length > 0 && (
                  <details>
                    <summary>占空间最多的素材</summary>
                    <ul>
                      {result.largest_media.map((entry) => (
                        <li key={entry.path}>
                          <code>{entry.path}</code> · {megabytes(entry.bytes)}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                <p>要备份整个工作台，请在确认停止写入后一起复制数据库和媒体所在的数据目录。</p>
              </>
            )}
          </div>
        )
      )}
      {download.isPending && <p role="status">正在打包并试恢复，原工程不会改动…</p>}
      {download.error && (
        <p className="error" role="alert">
          {download.error.message}
        </p>
      )}
      {!disabled && !status.isFetching && (
        <div className="bundle-backup-actions">
          {result?.can_export && !status.error && (
            <button type="button" disabled={download.isPending} onClick={() => download.mutate()}>
              下载工程 ZIP ↓
            </button>
          )}
          <button
            type="button"
            className="text-button"
            disabled={download.isPending}
            onClick={() => {
              download.reset()
              void status.refetch()
            }}
          >
            重新检查
          </button>
        </div>
      )}
    </details>
  )
}
