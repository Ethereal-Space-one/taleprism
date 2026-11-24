import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import { downloadScreeningWorksheet, usePlateScreening } from './PlateScreening'
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

function ReviewHandoff({ projectId }: { projectId: string }) {
  const screening = usePlateScreening(projectId)
  const summary = screening.data?.handoff
  const section = useRef<HTMLElement>(null)
  const startedWithFocus = useRef(false)
  const worksheet = useMutation({
    mutationFn: async () => {
      // An edit can arrive from another tab while this disclosure stays open.
      // Never download the old cached worksheet when an on-demand check fails.
      const fresh = await screening.refetch()
      if (fresh.isError || !fresh.data?.handoff)
        throw Error('无法重新核对审图，请重试。没有下载旧审图单。')
      const { motion_transferable, motion_blocked } = fresh.data.handoff
      if (!motion_transferable || motion_blocked)
        throw Error('审图范围已变，请核对下方最新结果。没有下载旧审图单。')
      return fresh.data.worksheet
    },
  })
  useEffect(() => {
    if (!worksheet.isError || !startedWithFocus.current) return
    startedWithFocus.current = false
    // A checked result can remove the old download button. If that was the
    // active control, give keyboard navigation a stable place to resume.
    if (document.activeElement === document.body) section.current?.focus()
  }, [worksheet.isError])
  const checking = screening.isFetching || worksheet.isPending
  return (
    <section
      ref={section}
      tabIndex={-1}
      className="bundle-review-handoff"
      aria-label="逐幅审图交接"
    >
      <h3>逐幅审图交接</h3>
      <p>工程 ZIP 不含动静审图单或出场时机判断。私有审图单只给继续制作的人，不发给读者。</p>
      {summary && checking && <p role="status">正在核对最新审图…</p>}
      {!summary && (screening.isFetching || screening.isPending) ? (
        <p role="status">正在核对已保存的审图…</p>
      ) : screening.isError || !summary ? (
        <>
          <p role="status">暂时无法核对审图。可在「逐幅审图」检查原图后重试；工程备份单独检查。</p>
          <button type="button" onClick={() => void screening.refetch()}>
            重查审图
          </button>
        </>
      ) : !summary.plates ? (
        <p role="status">本章尚无已放置插图，不需要交接审图单。</p>
      ) : (
        <>
          <dl>
            <div>
              <dt>动静判断</dt>
              <dd>
                {summary.motion_transferable} / {summary.plates} 幅符合审图单移入条件
                {summary.motion_unassessed ? `，${summary.motion_unassessed} 幅未审` : ''}
                {summary.motion_blocked ? `，${summary.motion_blocked} 幅需修正` : ''}。
              </dd>
            </div>
            <div>
              <dt>出场时机</dt>
              <dd>
                本版已记录 {summary.timing_recorded} / {summary.plates} 幅，不随备份迁移；恢复后{' '}
                {summary.plates} 幅都要核对。
              </dd>
            </div>
          </dl>
          {summary.motion_blocked > 0 ? (
            <p>
              请在「逐幅审图 → 动静选择」修正后再下载。移入时核对整份审图单，不能跳过有冲突的判断。
            </p>
          ) : summary.motion_transferable > 0 ? (
            <>
              <button
                type="button"
                aria-disabled={checking}
                onClick={(event) => {
                  if (checking) return
                  startedWithFocus.current = document.activeElement === event.currentTarget
                  worksheet.mutate(undefined, { onSuccess: downloadScreeningWorksheet })
                }}
              >
                下载私有动静审图单 JSON ↓
              </button>
              <p>恢复完整工程后，在「逐幅审图 → 动静选择」导入这份私有 JSON。</p>
            </>
          ) : null}
        </>
      )}
      {worksheet.error && (
        <p className="error" role="alert">
          {worksheet.error.message}
        </p>
      )}
    </section>
  )
}

export function BundleBackup({ projectId, disabled }: { projectId: string; disabled: boolean }) {
  const prefix = '/api/projects/' + projectId
  const cache = useQueryClient()
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
      <p className="asset-helper">
        给自己或下一位制作者，不是给读者的成品。工程 ZIP
        保留原文、声景私有依据与各版混音、候选和撤回录音、私人来源说明及已保存的制作意见。给读者请选「导出独立阅读器」。
      </p>
      {open && !disabled && <ReviewHandoff key={projectId} projectId={projectId} />}
      <p className="asset-helper">
        完整工程 ZIP 按解压后大小计算，上限 160
        MB；撤回的录音及声景仍会占用空间。超过上限不会静默删减，请停止工作台后一起复制数据库和媒体所在的数据目录。
      </p>
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
              void cache.invalidateQueries({ queryKey: ['plate-screening', projectId] })
            }}
          >
            重新检查
          </button>
        </div>
      )}
    </details>
  )
}
