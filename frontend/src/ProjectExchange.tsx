import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Project } from './api'
import { GuidedSampleIntro, type GuidedStart } from './GuidedSample'
type Pack = {
  id: string
  title: string
  description: string
  file: string
  available: boolean
  download_url?: string
  sha256?: string
}
type RestoredProject = Project & { restore_issues?: string[] }
export function ProjectExchange({
  onCreated,
  guidedStart,
  rawSample,
  onNavigate,
}: {
  onCreated: (p: Project) => void
  guidedStart: GuidedStart
  onNavigate: () => void
  rawSample: { pending: boolean; start: () => void }
}) {
  const [pack, setPack] = useState('')
  const [restored, setRestored] = useState<RestoredProject | null>(null)
  const created = (project: RestoredProject) => {
    setRestored(project)
    onCreated(project)
  }
  const list = useQuery({
    queryKey: ['content-packs'],
    queryFn: () => api<Pack[]>('/api/content-packs'),
  })
  const install = useMutation({
    mutationFn: () => api<RestoredProject>('/api/content-packs/' + pack, { method: 'POST' }),
    onSuccess: created,
  })
  const restore = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api<RestoredProject>('/api/project-bundles', { method: 'POST', body: form })
    },
    onSuccess: created,
  })
  const busy = install.isPending || restore.isPending
  const selected = list.data?.find((p) => p.id === pack)
  return (
    <div className="project-exchange">
      <GuidedSampleIntro start={guidedStart} compact />
      {guidedStart.error && (
        <p className="error" role="alert">
          {guidedStart.error.message}
        </p>
      )}
      <details className="exchange-manual" open={guidedStart.error ? true : undefined}>
        <summary>手动导入与原文练习</summary>
        <div className="exchange-manual-content">
          <h3>示例与工程</h3>
          <label>
            示例内容包
            <select aria-label="本地内容包" value={pack} onChange={(e) => setPack(e.target.value)}>
              <option value="">选择完整示例</option>
              {list.data?.map((p) => (
                <option value={p.id} key={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
          {selected && <p>{selected.description}</p>}
          {selected && !selected.available && (
            <p>
              本机尚未安装。
              {selected.download_url && (
                <a href={selected.download_url} target="_blank" rel="noreferrer">
                  下载示例工程 ↗
                </a>
              )}
              下载后选择下方“导入可编辑工程”。
            </p>
          )}
          <button
            disabled={!selected?.available || busy}
            onClick={() => {
              onNavigate()
              install.mutate()
            }}
          >
            {busy
              ? '正在准备…'
              : selected && !selected.available
                ? '下载后导入工程'
                : '作为新项目打开'}
          </button>
          <label className="file-button">
            导入可编辑工程
            <input
              aria-label="导入可编辑工程"
              disabled={busy}
              type="file"
              accept=".zip"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) {
                  onNavigate()
                  restore.mutate(file)
                }
                e.target.value = ''
              }}
            />
          </label>
          <small>每次导入新建项目；原工程保留。工程 ZIP 与只读阅读成品不同。</small>
          <div className="raw-sample">
            <button
              disabled={rawSample.pending || busy || guidedStart.pending}
              onClick={rawSample.start}
            >
              {rawSample.pending ? '正在准备原文…' : '仅从《末班灯》原文开始'}
            </button>
            <small>空白制作练习，只导入 TXT，不含完整方案与图片。</small>
          </div>
        </div>
      </details>
      {restored && (
        <div role="status" aria-live="polite">
          <p>已恢复“{restored.filename}”。</p>
          {!!restored.restore_issues?.length && (
            <>
              <p>工程仍有待修复内容，原方案与审核状态已保留。请修复并复核后再正式导出。</p>
              <ul>
                {restored.restore_issues.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
      {(install.error || restore.error || list.error) && (
        <p className="error" role="alert">
          {(install.error || restore.error || list.error)?.message}
        </p>
      )}
    </div>
  )
}
