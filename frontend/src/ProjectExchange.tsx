import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Project } from './api'
type Pack = {
  id: string
  title: string
  description: string
  file: string
  available: boolean
  download_url?: string
  sha256?: string
}
export function ProjectExchange({ onCreated }: { onCreated: (p: Project) => void }) {
  const [pack, setPack] = useState('')
  const list = useQuery({
    queryKey: ['content-packs'],
    queryFn: () => api<Pack[]>('/api/content-packs'),
  })
  const install = useMutation({
    mutationFn: () => api<Project>('/api/content-packs/' + pack, { method: 'POST' }),
    onSuccess: onCreated,
  })
  const restore = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api<Project>('/api/project-bundles', { method: 'POST', body: form })
    },
    onSuccess: onCreated,
  })
  const busy = install.isPending || restore.isPending
  const selected = list.data?.find((p) => p.id === pack)
  return (
    <div className="project-exchange">
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
      <button disabled={!selected?.available || busy} onClick={() => install.mutate()}>
        {busy ? '正在准备…' : selected && !selected.available ? '下载后导入工程' : '作为新项目打开'}
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
            if (file) restore.mutate(file)
            e.target.value = ''
          }}
        />
      </label>
      <small>每次导入新建项目；原工程保留。工程 ZIP 与只读阅读成品不同。</small>
      {(install.error || restore.error || list.error) && (
        <p className="error" role="alert">
          {(install.error || restore.error || list.error)?.message}
        </p>
      )}
    </div>
  )
}
