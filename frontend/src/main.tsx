import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Job, type Project, type TextData, type ReviewState } from './api'
import { ReviewPanel } from './ReviewPanel'
import { SpeechPanel } from './SpeechPanel'
import { VisualPanel } from './VisualPanel'
import { DeliveryPanel } from './DeliveryPanel'
import { ReaderApp } from './ReaderApp'
import { ReaderPanel } from './ReaderPanel'
import { ProductionPanel } from './ProductionPanel'
import { ProjectExchange } from './ProjectExchange'
import { GuidedSampleIntro, GuidedSampleSteps, type GuidedProject } from './GuidedSample'
import './style.css'

const rights: Record<string, string> = { owned: '自有作品', authorized: '已获授权', public_domain: '公有领域', local_test: '仅本地测试' }
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function App() {
  const cache = useQueryClient()
  const [selected, setSelected] = useState<string | null>(localStorage.getItem('storygal-project'))
  const [guidedProject, setGuidedProject] = useState<GuidedProject | null>(() => {
    try {
      const value = JSON.parse(localStorage.getItem('taleprism-guided-last-light') || 'null')
      return value && typeof value.projectId === 'string' && typeof value.shotId === 'string'
        ? { ...value, restoreIssues: Array.isArray(value.restoreIssues) && value.restoreIssues.every((item: unknown) => typeof item === 'string') ? value.restoreIssues : [] }
        : null
    } catch {
      return null
    }
  })
  const guidedOpening = useRef(false)
  const navigationVersion = useRef(0)
  const [guidedReady, setGuidedReady] = useState<GuidedProject | null>(null)
  const [focusShot, setFocusShot] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const [marks, setMarks] = useState(true)
  const [check, setCheck] = useState(false)
  const [mode, setMode] = useState<'text' | 'review' | 'speech' | 'visual' | 'delivery' | 'reader' | 'production'>('text')
  const dialog = useRef<HTMLDialogElement>(null)
  const [webgalOpen, setWebgalOpen] = useState(false)
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => api<Project[]>('/api/projects') })
  const project = projects.data?.find(p => p.id === selected)
  const data = useQuery({ queryKey: ['text', selected], queryFn: () => api<TextData>(`/api/projects/${selected}/text`), enabled: !!project })
  const review = useQuery({ queryKey: ['review', selected], queryFn: () => api<ReviewState>(`/api/projects/${selected}/review`), enabled: !!project })
  const jobs = useQuery({ queryKey: ['jobs', selected], queryFn: () => api<Job[]>(`/api/projects/${selected}/jobs`), enabled: !!project,
    refetchInterval: query => query.state.data?.some(j => j.state === 'running') ? 900 : false })
  const latest = jobs.data?.find(j => j.kind === 'export')
  const unit = data.data?.units[page]

  function keepCurrentWork() { navigationVersion.current += 1 }
  function navigateMode(next: typeof mode) { keepCurrentWork(); setMode(next) }
  function openImportDialog() { keepCurrentWork(); upload.reset(); dialog.current?.showModal() }
  function choose(id: string) {
    navigationVersion.current += 1
    setSelected(id); localStorage.setItem('storygal-project', id); setPage(0); setCheck(false); setWebgalOpen(false); setFocusShot(null); setMode('text')
  }
  function created(p: Project) {
    cache.invalidateQueries({ queryKey: ['projects'] }); choose(p.id); dialog.current?.close()
  }
  const guided = useMutation({
    mutationFn: (_request: { navigation: number }) =>
      api<Project & { guided_shot_id: string; restore_issues?: string[] }>('/api/samples/last-light/guided', {
        method: 'POST',
      }),
    onSuccess: (p, request) => {
      const guide = { projectId: p.id, shotId: p.guided_shot_id, restoreIssues: p.restore_issues }
      cache.invalidateQueries({ queryKey: ['projects'] })
      if (request.navigation === navigationVersion.current) {
        setGuidedProject(guide)
        localStorage.setItem('taleprism-guided-last-light', JSON.stringify(guide))
        created(p)
        setGuidedReady(null)
        setMode('production')
        setFocusShot(guide.shotId)
      } else setGuidedReady(guide)
      cache.invalidateQueries({ queryKey: ['guided-last-light'] })
    },
    onSettled: () => {
      guidedOpening.current = false
    },
  })
  const guidedStart = {
    pending: guided.isPending,
    error: guided.error,
    start: () => {
      if (guidedOpening.current) return
      guidedOpening.current = true
      guided.mutate({ navigation: navigationVersion.current })
    },
  }
  function editGuidedShot(id: string) {
    navigateMode('production')
    setFocusShot(id)
  }
  useEffect(() => {
    if (mode !== 'production' || !focusShot) return
    const reveal = () => {
      const element = document.getElementById(`shot-${focusShot}`)
      if (!element) return false
      if (element instanceof HTMLDetailsElement) element.open = true
      element.scrollIntoView({ behavior: 'smooth', block: 'start' })
      setFocusShot(null)
      return true
    }
    if (reveal()) return
    const observer = new MutationObserver(() => {
      if (reveal()) observer.disconnect()
    })
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [mode, focusShot])
  const sample = useMutation({ mutationFn: () => api<Project>('/api/samples/last-light', { method: 'POST' }), onSuccess: created })
  const upload = useMutation({ mutationFn: (form: FormData) => api<Project>('/api/projects', { method: 'POST', body: form }), onSuccess: created })
  const verify = useMutation({ mutationFn: () => api(`/api/projects/${selected}/verify`, { method: 'POST' }), onSuccess: () => setCheck(true) })
  const busy = latest?.state === 'running'
  const error = projects.error || data.error || jobs.error || sample.error || verify.error

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (mode !== 'text' || dialog.current?.open || /INPUT|SELECT|TEXTAREA/.test((e.target as HTMLElement).tagName)) return
      if (e.key === 'ArrowRight') setPage(p => Math.min(p + 1, (data.data?.units.length || 1) - 1))
      if (e.key === 'ArrowLeft') setPage(p => Math.max(0, p - 1))
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [data.data, mode])

  return <div className="app creator-workbench">
    <header className="masthead">
      <a className="brand" href="/" aria-label="Taleprism 首页"><b>Taleprism<span className="brand-dot">.</span></b><span>VISUAL STORIES</span></a>
      <span className="local-note"><span className="status-dot" />本地制作台 <small>本地版</small></span>
    </header>
    <div className="workspace">
      <aside className="sidebar" aria-label="项目导航">
        <div className="sidebar-head"><h2>我的文本</h2><button className="plus" onClick={openImportDialog} aria-label="导入新文本">＋</button></div>
        <div className="project-list">
          {projects.isPending && <p role="status">正在读取项目…</p>}
          {projects.data?.map(p => <button key={p.id} className={`project ${p.id === selected ? 'selected' : ''}`} onClick={() => choose(p.id)} title={p.filename}>
            <span className="project-icon">文</span><span className="project-name">{p.filename.replace(/\.txt$/i, '')}<small>{p.character_count.toLocaleString()} 字</small></span>
          </button>)}
          {projects.data?.length === 0 && <p className="sidebar-empty">还没有项目。<br />导入一章，开始制作。</p>}
        </div>
        <ProjectExchange onCreated={(p) => { created(p); setMode('production') }} guidedStart={guidedStart} onNavigate={keepCurrentWork} rawSample={{ pending: sample.isPending, start: () => { keepCurrentWork(); sample.mutate() } }} />
        <div className="sidebar-foot"><span>文本 → 标注 → 试读</span><p>项目与产物保存在这台电脑。</p></div>
      </aside>
      <main onInputCapture={() => { if (guidedOpening.current) keepCurrentWork() }}>
        {error && <p className="error" role="alert">{error.message}</p>}
        {guidedReady && <div className="notice" role="status"><p>完整样例已另存为新项目。你切换后的当前项目未改动。</p><button onClick={() => { choose(guidedReady.projectId); setGuidedProject(guidedReady); localStorage.setItem('taleprism-guided-last-light', JSON.stringify(guidedReady)); setGuidedReady(null); setMode('production'); setFocusShot(guidedReady.shotId) }}>打开刚准备的《末班灯》副本 →</button></div>}
        {!project ? <>
          <GuidedSampleIntro start={guidedStart} />
          <div className="guided-manual-intro"><button onClick={openImportDialog}>导入自己的 TXT ↗</button><p>已有原文？从空白项目开始。完整示例与工程 ZIP 导入在左侧「手动导入与原文练习」。</p></div>
        </> : <>
          <div className="project-heading"><div><p className="eyebrow">文本工作台 <span>／</span> {rights[project.rights_status]}</p><h1>{project.filename.replace(/\.txt$/i, '')}</h1><p className="project-meta">{project.character_count.toLocaleString()} 字 <span>·</span> {data.data?.units.length || project.unit_count} 个显示框 <span>·</span> {project.encoding.toUpperCase()}</p></div>
          <div className="heading-actions"><button disabled={verify.isPending} onClick={() => { keepCurrentWork(); verify.mutate() }}>{verify.isPending ? '正在校验…' : check ? '✓ 原文校验通过' : '校验原文'}</button><a href={`/read/${project.id}`} onClick={keepCurrentWork} target="_blank" rel="noreferrer">阅读预览 ↗</a><button className="primary" onClick={() => navigateMode('reader')}>独立阅读器与导出 <span>→</span></button></div></div>
          {guidedProject?.projectId === project.id && <GuidedSampleSteps guide={guidedProject} mode={mode} onEdit={editGuidedShot} onPreview={() => navigateMode('reader')} onNavigate={keepCurrentWork} onLeave={() => { keepCurrentWork(); setGuidedProject(null); localStorage.removeItem('taleprism-guided-last-light') }} />}
          {latest?.state === 'failed' && <p className="error" role="alert">导出未完成：{latest.error} 可重新导出。</p>}
          {busy && <p className="notice" role="status">正在打包 WebGAL 兼容版本，完成后请到交付检查查看。</p>}

          <nav className="workspace-tabs" aria-label="工作台视图"><button aria-pressed={mode === 'production'} onClick={() => navigateMode('production')}>章节制作方案</button><button aria-pressed={mode === 'text'} onClick={() => navigateMode('text')}>原文与预览</button><button aria-pressed={mode === 'review'} onClick={() => navigateMode('review')}>人物与审校{review.data ? ` · ${review.data.pending_count} 待审` : ''}</button><button aria-pressed={mode === 'speech'} onClick={() => navigateMode('speech')}>对白配音</button><button aria-pressed={mode === 'visual'} onClick={() => navigateMode('visual')}>视觉与图解</button><button aria-pressed={mode === 'reader'} onClick={() => navigateMode('reader')}>独立阅读器</button><button aria-pressed={mode === 'delivery'} onClick={() => navigateMode('delivery')}>交付检查</button></nav>
          {mode === 'production' && <ProductionPanel key={project.id} projectId={project.id} />}
          {mode === 'reader' && <ReaderPanel key={project.id} projectId={project.id} review={review.data} />}
          {mode === 'delivery' && <DeliveryPanel key={project.id} projectId={project.id} onLocate={navigateMode} onExport={() => { keepCurrentWork(); setWebgalOpen(true) }} busy={busy} />}
          {mode === 'visual' && data.data && <VisualPanel key={project.id} projectId={project.id} spans={data.data.spans} units={data.data.units} />}
          {mode === 'speech' && <SpeechPanel key={project.id} projectId={project.id} />}
          {mode === 'review' && <ReviewPanel key={project.id} projectId={project.id} onLocate={(start, end) => {
            const found = data.data?.units.findIndex(u => start < u.byte_end && end > u.byte_start) ?? -1
            if (found >= 0) setPage(found)
            navigateMode('text')
          }} />}
          {data.isPending && <p role="status">正在读取原文与切分…</p>}
          {data.data && mode === 'text' && <div className="review-grid">
            <section className="source-panel" aria-label="原文预览"><div className="panel-head"><h2>原文</h2><label className="mark-switch"><input type="checkbox" checked={marks} onChange={e => setMarks(e.target.checked)} />显示标注</label></div>
              <div className="source-legend"><span>只读</span><span className="dialogue-legend">引号内文本</span><span>{review.data?.pending_count || 0} 句待审校</span></div>
              <article className={`source-text ${marks ? 'marked' : ''}`}>
                {data.data.spans.map(s => <span key={s.id} className={`span-${s.kind} ${unit && s.byte_start < unit.byte_end && s.byte_end > unit.byte_start ? 'current-range' : ''}`} title={`字节 ${s.byte_start}–${s.byte_end}`} onClick={() => {
                  const found = data.data.units.findIndex(u => s.byte_start < u.byte_end && s.byte_end > u.byte_start)
                  if (found >= 0) setPage(found)
                }}>{s.text}</span>)}
              </article>
              <footer className="source-foot">完整保留 {project.byte_length.toLocaleString()} 字节原文件 <a href={`/api/projects/${project.id}/source`}>下载原文 ↓</a></footer>
            </section>
            <aside className="preview-panel" aria-label="显示分段预览"><div className="panel-head"><h2>显示分段</h2><span>整段同框</span></div>
              <p className="preview-note">预览每次点击显示的内容。<br />长段按句子边界分页，文字顺序不变。</p>
              <div className="reading-frame"><span className="page-label">第 {page + 1} 框{unit?.speaker_name ? ` · ${unit.speaker_name}` : ''}</span>{unit?.figure_asset_id && <img className="preview-figure" src={review.data?.assets.find(a => a.id === unit.figure_asset_id)?.url} alt={`${unit.speaker_name}立绘`} />}<p data-testid="unit-text">{unit?.text}</p><span className="reading-next">◇</span></div>
              <div className="pagination"><button aria-label="上一框" disabled={page === 0} onClick={() => setPage(p => p - 1)}>←</button><span>{page + 1} <span>/ {data.data.units.length}</span></span><button aria-label="下一框" disabled={page >= data.data.units.length - 1} onClick={() => setPage(p => p + 1)}>→</button></div>
              <label className="jump-label">跳到显示框<input type="number" min={1} max={data.data.units.length} value={page + 1} onChange={e => setPage(Math.min(data.data.units.length - 1, Math.max(0, Number(e.target.value) - 1)))} /></label>
              <p className="keyboard-hint">也可使用键盘 ← → 翻页</p>
              <details className="integrity"><summary>保真记录</summary><p>原文哈希</p><code>{project.sha256}</code><p>显示仅隐藏换行、初始 BOM 与每行首尾空白；导出时检查所有原文字节和显示顺序。</p><p>实际播放复核需单独执行，导出成功不表示已完成逐框播放检查。</p></details>
            </aside>
          </div>}
        </>}
        <footer className="colophon"><span>Taleprism · 忠于原文的制作工具</span><span>v0.3.1 / 公开试用版</span></footer>
      </main>
    </div>
    {webgalOpen && project && <WebgalExportDialog key={project.id} projectId={project.id} busy={busy} onClose={() => setWebgalOpen(false)} onReader={() => { setWebgalOpen(false); navigateMode('reader') }} />}
    <dialog ref={dialog} className="import-dialog"><form onSubmit={e => { e.preventDefault(); upload.mutate(new FormData(e.currentTarget)) }}>
      <div className="dialog-head"><h2>导入一章文本</h2><button type="button" aria-label="关闭导入" onClick={() => dialog.current?.close()}>×</button></div>
      <p>建议 5,000–15,000 字，最多 30,000 字。</p>
      <label>TXT 文件<input name="file" type="file" accept=".txt,text/plain" required /></label>
      <label>文本权利状态<select name="rights_status" required defaultValue=""><option value="" disabled>请选择</option>{Object.entries(rights).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>文件编码<select name="encoding" defaultValue="auto"><option value="auto">自动识别（优先 UTF-8）</option><option value="utf-8">UTF-8</option><option value="gb18030">GB18030 / GBK</option></select></label>
      {upload.error && <p className="error" role="alert">{upload.error.message}</p>}
      <p className="privacy-note">原文与工程保存在本机；导入后可下载原文件。</p>
      <button className="primary" type="submit" disabled={upload.isPending}>{upload.isPending ? '正在导入…' : '导入并预览'}<span>→</span></button>
    </form></dialog>
  </div>
}

type WebgalCompatibility = {
  reader_revision: number
  compatible: boolean
  losses: { field: string; label: string; detail: string }[]
}

function WebgalExportDialog({
  projectId,
  busy,
  onClose,
  onReader,
}: {
  projectId: string
  busy: boolean
  onClose: () => void
  onReader: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const cache = useQueryClient()
  const [approvedRevision, setApprovedRevision] = useState<number | null>(null)
  const report = useQuery({
    queryKey: ['webgal-compatibility', projectId],
    queryFn: () => api<WebgalCompatibility>(`/api/projects/${projectId}/exports/compatibility`),
    staleTime: 0,
  })
  const submit = useMutation({
    mutationFn: (snapshot: WebgalCompatibility) =>
      api(
        `/api/projects/${projectId}/exports?reader_revision=${snapshot.reader_revision}${snapshot.losses.length ? '&simplified=true' : ''}`,
        { method: 'POST' },
      ),
    onSuccess: async () => {
      await Promise.all([
        cache.invalidateQueries({ queryKey: ['jobs', projectId] }),
        cache.invalidateQueries({ queryKey: ['delivery', projectId] }),
      ])
      onClose()
    },
    onError: async () => {
      setApprovedRevision(null)
      await report.refetch()
    },
  })
  useEffect(() => {
    const element = dialog.current
    if (element && !element.open) element.showModal()
  }, [])
  const data = report.data
  const lossy = !!data?.losses.length
  return (
    <dialog
      ref={dialog}
      className="export-dialog"
      aria-labelledby="webgal-title"
      aria-describedby="webgal-description"
      onCancel={(e) => {
        if (submit.isPending) e.preventDefault()
        else onClose()
      }}
      onClose={() => { if (!submit.isPending) onClose() }}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (
            data &&
            !report.isFetching &&
            !submit.isPending &&
            !busy &&
            (!lossy || approvedRevision === data.reader_revision)
          )
            submit.mutate(data)
        }}
      >
        <div className="dialog-head">
          <h2 id="webgal-title">WebGAL 兼容导出</h2>
          <button type="button" aria-label="关闭 WebGAL 导出" disabled={submit.isPending} onClick={onClose}>
            ×
          </button>
        </div>
        <p id="webgal-description">
          用于需要 WebGAL
          引擎的逐框播放。保留原文、审校后的对白、已选配音与“视觉与图解”中启用的图页，不等同于独立阅读器。
        </p>
        {report.isFetching && <p role="status">正在核对当前阅读器配置…</p>}
        {submit.isPending && <p role="status">请求提交中，请稍候。提交成功后会在后台打包，此时不能取消已提交的请求。</p>}
        {(report.error || submit.error) && (
          <p className="error" role="alert">
            {(submit.error || report.error)?.message}
          </p>
        )}
        {report.error && (
          <button type="button" onClick={() => report.refetch()} disabled={report.isFetching}>
            重新检查
          </button>
        )}
        {data && !report.error && (
          <>
            {lossy ? (
              <section aria-labelledby="webgal-loss-heading">
                <h3 id="webgal-loss-heading">此版本将省略的内容</h3>
                <ul className="export-losses">
                  {data.losses.map((loss) => (
                    <li key={loss.field}>
                      <strong>{loss.label}</strong>
                      <p>{loss.detail}</p>
                    </li>
                  ))}
                </ul>
                <label className="inline-check">
                  <input
                    type="checkbox"
                    checked={approvedRevision === data.reader_revision}
                    onChange={(e) =>
                      setApprovedRevision(e.target.checked ? data.reader_revision : null)
                    }
                    disabled={report.isFetching || submit.isPending}
                  />
                  我已了解上述省略内容，仍要导出简化版。
                </label>
              </section>
            ) : (
              <p className="saved-note">
                当前没有配置会被省略的阅读器专属内容，仍将使用 WebGAL 逐框播放。
              </p>
            )}
            <p className="asset-helper">
              原项目不会改动。完整保留章节插图、编排和地图，请选择独立阅读器。
            </p>
          </>
        )}
        <div className="export-dialog-actions">
          <button type="button" className="primary" disabled={submit.isPending} onClick={onReader}>
            改用独立阅读器 →
          </button>
          <button
            type="submit"
            disabled={
              !data ||
              !!report.error ||
              report.isFetching ||
              submit.isPending ||
              busy ||
              (lossy && approvedRevision !== data.reader_revision)
            }
          >
            {submit.isPending ? '正在提交…' : lossy ? '导出 WebGAL 简化版' : '导出 WebGAL 兼容版'}
          </button>
          <button type="button" className="text-button" disabled={submit.isPending} onClick={onClose}>
            取消
          </button>
        </div>
      </form>
    </dialog>
  )
}

const readerProject = /^\/read\/([0-9a-f-]{36})\/?$/.exec(location.pathname)?.[1]
const readerExport = document.querySelector<HTMLMetaElement>('meta[name="storygal-reader-export"]')?.content
createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={client}>{readerProject || readerExport ? <ReaderApp projectId={readerProject} exportUrl={readerExport} /> : <App />}</QueryClientProvider></React.StrictMode>)
