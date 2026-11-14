import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api, type Job } from './api'

type Mode = 'text' | 'review' | 'speech' | 'visual' | 'delivery' | 'reader' | 'production'
type Record = { export_id: string; reviewed_at: string; notes: string; archive_sha256: string }
type Delivery = {
  ready: boolean
  stale: boolean
  checks: { id: string; label: string; target: Mode; passed: boolean; detail: string }[]
  warnings: { target: Mode; detail: string }[]
  latest: Job | null
  records: Record[]
  tasks: Job[]
}
const checks = [
  ['source', '已核对显示正文与原文一致'],
  ['speakers', '已核对角色标签、立绘和未知归属'],
  ['audio', '已试听选中配音；无配音时已确认静音'],
  ['visual', '已核对场景、人物出入场、图页／地图及正文恢复；无视觉素材时已确认'],
  ['end', '已从头完整读到结尾，未遇到缺字、缺资源或卡住'],
] as const
const names = {
  export: 'WebGAL 导出',
  reader_export: '阅读器导出',
  speech: '对白配音',
  analysis: '角色抽取',
}

export function DeliveryPanel({
  projectId,
  onLocate,
  onExport,
  busy,
}: {
  projectId: string
  onLocate: (mode: Mode) => void
  onExport: () => void
  busy: boolean
}) {
  const [approval, setApproval] = useState<{ exportId: string | null; keys: string[] }>({
    exportId: null,
    keys: [],
  })
  const state = useQuery({
    queryKey: ['delivery', projectId],
    queryFn: () => api<Delivery>(`/api/projects/${projectId}/delivery`),
    refetchInterval: (q) => (q.state.data?.tasks.some((t) => t.state === 'running') ? 1000 : false),
  })
  const data = state.data
  const job = data?.latest
  const result = job?.result
  const selected = approval.exportId === job?.id ? approval.keys : []
  const record = data?.records.find((r) => r.export_id === job?.id)
  const save = useMutation({
    mutationFn: (notes: string) =>
      api(`/api/projects/${projectId}/exports/${job!.id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ checks: Object.fromEntries(selected.map((k) => [k, true])), notes }),
      }),
    onSuccess: () => {
      setApproval({ exportId: null, keys: [] })
      state.refetch()
    },
  })
  return (
    <section className="delivery-panel" aria-label="交付检查">
      <div className="panel-head">
        <h2>交付检查</h2>
        <button disabled={state.isFetching} onClick={() => state.refetch()}>
          {state.isFetching ? '正在检查…' : '重新检查'}
        </button>
      </div>
      <p className="asset-helper">
        推荐交付独立阅读器，保留完整图文与编排。自动检查与人工复核分别记录，导出后仍需从头试读。
      </p>
      {(state.error || save.error) && (
        <p className="error" role="alert">
          {(state.error || save.error)?.message}
        </p>
      )}
      {state.isPending && <p role="status">正在检查原文与已启用素材…</p>}
      {data && (
        <>
          <p className={data.ready ? 'saved-note' : 'error'} role="status">
            {data.ready ? '✓ 自动检查通过。' : '请先修复以下问题，再导出当前版本。'}
          </p>
          <p className="asset-helper">
            以下检查针对{job?.kind === 'export' ? '最近的 WebGAL 兼容交付' : '独立阅读器交付'}。
          </p>
          <div className="delivery-checks">
            {data.checks.map((c) => (
              <article key={c.id} className={c.passed ? '' : 'blocked'}>
                <div>
                  <strong>
                    {c.passed ? '✓ ' : '待修复 · '}
                    {c.label}
                  </strong>
                  <p>{c.detail}</p>
                </div>
                {!c.passed && c.target !== 'delivery' && (
                  <button onClick={() => onLocate(c.target)}>前往处理</button>
                )}
              </article>
            ))}
          </div>
          {data.warnings.length > 0 && (
            <aside className="delivery-warnings">
              <h3>制作提醒</h3>
              <p>以下事项不会阻止导出，请在最终审查时核实。</p>
              {data.warnings.map((w, i) => (
                <p key={i}>
                  {w.detail}{' '}
                  <button className="text-button" onClick={() => onLocate(w.target)}>
                    查看 →
                  </button>
                </p>
              ))}
            </aside>
          )}
          <button className="primary" onClick={() => onLocate('reader')}>
            前往独立阅读器与导出 →
          </button>
          <details className="webgal-compatibility">
            <summary>其他格式 · WebGAL 兼容导出</summary>
            <p>
              仅在需要 WebGAL
              引擎时使用。章节插图、阅读器场景和地图等专属内容不会自动转换，导出前会逐项列明。
            </p>
            <button disabled={busy} onClick={onExport}>
              {busy ? '正在打包 WebGAL…' : '检查 WebGAL 兼容性'}
            </button>
          </details>
          {result && (
            <div className="delivery-output">
              <h3>
                {data.stale ? '之前的成品 · 制作状态已变化' : '当前成品'} ·{' '}
                {job?.kind === 'export' ? 'WebGAL 兼容版' : '独立阅读器'}
              </h3>
              <p>
                {result.file_count ? `${result.file_count} 个文件 · ` : ''}
                {new Date(job!.created_at).toLocaleString('zh-CN')}
              </p>
              <div className="visual-actions">
                <a href={result.play_url} target="_blank" rel="noreferrer">
                  打开完整播放 ↗
                </a>
                <a href={result.download_url}>下载独立工程 ↓</a>
              </div>
              <p className="asset-helper">
                下载解压后，按包内 README 启动；随包提供文件完整性检查器和素材来源说明。
              </p>
              {result.archive_sha256 && (
                <details className="integrity">
                  <summary>压缩包完整性指纹</summary>
                  <code>{result.archive_sha256}</code>
                  <p>用于核对下载内容，不能代替事实或权利审核。</p>
                </details>
              )}
              {record && (
                <p className="saved-note">
                  ✓ 此导出版本已有人工复核记录 ·{' '}
                  {new Date(record.reviewed_at).toLocaleString('zh-CN')}
                  {record.notes && ` · ${record.notes}`}
                </p>
              )}
              <form
                className="delivery-review"
                key={job!.id}
                onSubmit={(e) => {
                  e.preventDefault()
                  save.mutate(String(new FormData(e.currentTarget).get('notes') || ''))
                }}
              >
                <h3>记录本版本人工复核</h3>
                <p className="asset-helper">
                  完成实际播放后再勾选。记录绑定本次成品，修改后需重新导出并复核。
                </p>
                {checks.map(([key, label]) => (
                  <label className="inline-check" key={key}>
                    <input
                      type="checkbox"
                      checked={selected.includes(key)}
                      onChange={(e) =>
                        setApproval({
                          exportId: job!.id,
                          keys: e.target.checked
                            ? [...selected, key]
                            : selected.filter((k) => k !== key),
                        })
                      }
                    />
                    {label}
                  </label>
                ))}
                <label>
                  审查备注
                  <textarea
                    name="notes"
                    maxLength={2000}
                    rows={3}
                    placeholder="可记录仍需调整的读音、素材或说明"
                  />
                </label>
                <button
                  disabled={
                    selected.length !== checks.length || data.stale || save.isPending || busy
                  }
                >
                  {save.isPending ? '正在记录…' : '保存人工复核记录'}
                </button>
                {data.stale && <p className="error">制作状态已变，请先导出当前版本。</p>}
              </form>
            </div>
          )}
          <details className="delivery-history">
            <summary>最近任务与失败原因</summary>
            {data.tasks.map((t) => (
              <article key={t.id}>
                <strong>
                  {names[t.kind]} ·{' '}
                  {t.state === 'completed' ? '已完成' : t.state === 'running' ? '进行中' : '未完成'}
                </strong>
                <small>{new Date(t.created_at).toLocaleString('zh-CN')}</small>
                {t.error && <p className="error">{t.error}</p>}
                {t.state === 'failed' && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      t.kind === 'export'
                        ? onExport()
                        : onLocate(
                            t.kind === 'reader_export'
                              ? 'reader'
                              : t.kind === 'speech'
                                ? 'speech'
                                : 'review',
                          )
                    }
                  >
                    {t.kind === 'export' ? '重新导出当前版本' : '前往重试'}
                  </button>
                )}
              </article>
            ))}
          </details>
        </>
      )}
    </section>
  )
}
