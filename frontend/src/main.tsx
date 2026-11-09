import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Job, type Project, type TextData, type ReviewState } from './api'
import { ReviewPanel } from './ReviewPanel'
import { SpeechPanel, type SpeechState } from './SpeechPanel'
import { VisualPanel, type VisualState } from './VisualPanel'
import { DeliveryPanel } from './DeliveryPanel'
import { ReaderApp } from './ReaderApp'
import { ReaderPanel } from './ReaderPanel'
import { ProductionPanel } from './ProductionPanel'
import { ProjectExchange } from './ProjectExchange'
import './style.css'

const rights: Record<string, string> = { owned: '自有作品', authorized: '已获授权', public_domain: '公有领域', local_test: '仅本地测试' }
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function App() {
  const cache = useQueryClient()
  const [selected, setSelected] = useState<string | null>(localStorage.getItem('storygal-project'))
  const [page, setPage] = useState(0)
  const [marks, setMarks] = useState(true)
  const [check, setCheck] = useState(false)
  const [mode, setMode] = useState<'text' | 'review' | 'speech' | 'visual' | 'delivery' | 'reader' | 'production'>('text')
  const dialog = useRef<HTMLDialogElement>(null)
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => api<Project[]>('/api/projects') })
  const project = projects.data?.find(p => p.id === selected)
  const data = useQuery({ queryKey: ['text', selected], queryFn: () => api<TextData>(`/api/projects/${selected}/text`), enabled: !!project })
  const review = useQuery({ queryKey: ['review', selected], queryFn: () => api<ReviewState>(`/api/projects/${selected}/review`), enabled: !!project })
  const jobs = useQuery({ queryKey: ['jobs', selected], queryFn: () => api<Job[]>(`/api/projects/${selected}/jobs`), enabled: !!project,
    refetchInterval: query => query.state.data?.some(j => j.state === 'running') ? 900 : false })
  const speech = useQuery({ queryKey: ['speech', selected], queryFn: () => api<SpeechState>(`/api/projects/${selected}/speech`), enabled: !!project })
  const visual = useQuery({ queryKey: ['visual', selected], queryFn: () => api<VisualState>(`/api/projects/${selected}/visual`), enabled: !!project })
  const latest = jobs.data?.find(j => j.kind === 'export')
  const exported = jobs.data?.find(j => j.kind === 'export' && j.state === 'completed')?.result
  const stale = !!exported && ((review.data?.revision || 0) > (exported.review_revision || 0) || (speech.data?.revision || 0) > (exported.speech_revision || 0) || (visual.data?.revision || 0) > (exported.visual_revision || 0))
  const unit = data.data?.units[page]

  function choose(id: string) {
    setSelected(id); localStorage.setItem('storygal-project', id); setPage(0); setCheck(false); setMode('text')
  }
  function created(p: Project) {
    cache.invalidateQueries({ queryKey: ['projects'] }); choose(p.id); dialog.current?.close()
  }
  const sample = useMutation({ mutationFn: () => api<Project>('/api/samples/last-light', { method: 'POST' }), onSuccess: created })
  const upload = useMutation({ mutationFn: (form: FormData) => api<Project>('/api/projects', { method: 'POST', body: form }), onSuccess: created })
  const verify = useMutation({ mutationFn: () => api(`/api/projects/${selected}/verify`, { method: 'POST' }), onSuccess: () => setCheck(true) })
  const exportJob = useMutation({ mutationFn: async () => {
    const r = await api<{config: {presentations?: unknown[]; map_entries?: unknown[]}}>(`/api/projects/${selected}/reader`)
    const p6 = !!(r.config.presentations?.length || r.config.map_entries?.length)
    if (p6 && !window.confirm('WebGAL 会简化段内人物编排、事件呈现和地图入口。完整体验请在“阅读器与场景”导出独立阅读器。仍要导出简化版吗？')) throw Error('已取消简化导出，可前往阅读器与场景。')
    return api(`/api/projects/${selected}/exports${p6 ? '?simplified=true' : ''}`, { method: 'POST' })
  },
    onSuccess: async () => { await cache.invalidateQueries({ queryKey: ['jobs', selected] }); await cache.invalidateQueries({ queryKey: ['delivery', selected] }) } })
  const busy = exportJob.isPending || latest?.state === 'running'
  const error = projects.error || data.error || jobs.error || sample.error || verify.error || exportJob.error

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (mode !== 'text' || dialog.current?.open || /INPUT|SELECT|TEXTAREA/.test((e.target as HTMLElement).tagName)) return
      if (e.key === 'ArrowRight') setPage(p => Math.min(p + 1, (data.data?.units.length || 1) - 1))
      if (e.key === 'ArrowLeft') setPage(p => Math.max(0, p - 1))
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [data.data, mode])

  return <div className="app">
    <header className="masthead">
      <a className="brand" href="/" aria-label="Taleprism 首页"><b>Taleprism<span className="brand-dot">.</span></b><span>VISUAL STORIES</span></a>
      <span className="local-note"><span className="status-dot" />本地制作台 <small>本地版</small></span>
    </header>
    <div className="workspace">
      <aside className="sidebar" aria-label="项目导航">
        <div className="sidebar-head"><h2>我的文本</h2><button className="plus" onClick={() => { upload.reset(); dialog.current?.showModal() }} aria-label="导入新文本">＋</button></div>
        <div className="project-list">
          {projects.isPending && <p role="status">正在读取项目…</p>}
          {projects.data?.map(p => <button key={p.id} className={`project ${p.id === selected ? 'selected' : ''}`} onClick={() => choose(p.id)} title={p.filename}>
            <span className="project-icon">文</span><span className="project-name">{p.filename.replace(/\.txt$/i, '')}<small>{p.character_count.toLocaleString()} 字</small></span>
          </button>)}
          {projects.data?.length === 0 && <p className="sidebar-empty">还没有项目。<br />导入一章，开始制作。</p>}
        </div>
        <ProjectExchange onCreated={(p) => { created(p); setMode('production') }} />
        <div className="sidebar-foot"><span>文本 → 标注 → 试读</span><p>项目与产物保存在这台电脑。</p></div>
      </aside>
      <main>
        {error && <p className="error" role="alert">{error.message}</p>}
        {!project ? <div className="empty-state">
          <span className="folio">原文在这里，故事向前。</span>
          <h1>从一章原文开始。</h1>
          <p>导入文本，查看切分，再把这一章<br className="desktop-break" />变成可以连续阅读的视觉作品。</p>
          <div className="empty-actions"><button className="primary" onClick={() => { upload.reset(); dialog.current?.showModal() }}>导入 TXT <span>↗</span></button>
          <button className="text-button" disabled={sample.isPending} onClick={() => sample.mutate()}>{sample.isPending ? '正在准备样例…' : '从《末班灯》原文练习 →'}</button></div>
          <div className="empty-detail"><span>01 / 文本底座</span><p>支持 UTF-8、GB18030 · 单篇最多 30,000 字<br />原文完整留存，显示内容可以逐框核对。</p></div>
        </div> : <>
          <div className="project-heading"><div><p className="eyebrow">文本工作台 <span>／</span> {rights[project.rights_status]}</p><h1>{project.filename.replace(/\.txt$/i, '')}</h1><p className="project-meta">{project.character_count.toLocaleString()} 字 <span>·</span> {data.data?.units.length || project.unit_count} 个显示框 <span>·</span> {project.encoding.toUpperCase()}</p></div>
          <div className="heading-actions"><button disabled={verify.isPending} onClick={() => verify.mutate()}>{verify.isPending ? '正在校验…' : check ? '✓ 原文校验通过' : '校验原文'}</button><a className="primary" href={`/read/${project.id}`} target="_blank" rel="noreferrer">阅读预览 ↗</a><button disabled={busy || data.isPending || !!data.error} onClick={() => exportJob.mutate()}>{busy ? '正在导出…' : '导出 WebGAL'}<span>↗</span></button></div></div>
          {latest?.state === 'failed' && <p className="error" role="alert">导出未完成：{latest.error} 可重新导出。</p>}
          {busy && <p className="notice" role="status">正在检查原文并打包工程，完成后可以播放和下载。</p>}
          {exported && <div className="export-result" role="status"><span>{stale ? '审校已更新，下方是旧版本，请重新导出。' : '✓ 工程已导出，原文与解析检查通过。'}</span><div><a href={exported.play_url} target="_blank" rel="noreferrer">打开播放 ↗</a><a href={exported.download_url}>下载工程 ↓</a></div></div>}
          <nav className="workspace-tabs" aria-label="工作台视图"><button aria-pressed={mode === 'production'} onClick={() => setMode('production')}>章节制作方案</button><button aria-pressed={mode === 'text'} onClick={() => setMode('text')}>原文与预览</button><button aria-pressed={mode === 'review'} onClick={() => setMode('review')}>人物与审校{review.data ? ` · ${review.data.pending_count} 待审` : ''}</button><button aria-pressed={mode === 'speech'} onClick={() => setMode('speech')}>对白配音</button><button aria-pressed={mode === 'visual'} onClick={() => setMode('visual')}>视觉与图解</button><button aria-pressed={mode === 'reader'} onClick={() => setMode('reader')}>阅读器与场景</button><button aria-pressed={mode === 'delivery'} onClick={() => setMode('delivery')}>交付检查</button></nav>
          {mode === 'production' && <ProductionPanel key={project.id} projectId={project.id} />}
          {mode === 'reader' && <ReaderPanel key={project.id} projectId={project.id} review={review.data} />}
          {mode === 'delivery' && <DeliveryPanel key={project.id} projectId={project.id} onLocate={setMode} onExport={() => exportJob.mutate()} busy={busy} />}
          {mode === 'visual' && data.data && <VisualPanel key={project.id} projectId={project.id} spans={data.data.spans} units={data.data.units} />}
          {mode === 'speech' && <SpeechPanel key={project.id} projectId={project.id} />}
          {mode === 'review' && <ReviewPanel key={project.id} projectId={project.id} onLocate={(start, end) => {
            const found = data.data?.units.findIndex(u => start < u.byte_end && end > u.byte_start) ?? -1
            if (found >= 0) setPage(found)
            setMode('text')
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
        <footer className="colophon"><span>Taleprism · 忠于原文的制作工具</span><span>v0.1.0 / 公开试用版</span></footer>
      </main>
    </div>
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

const readerProject = /^\/read\/([0-9a-f-]{36})\/?$/.exec(location.pathname)?.[1]
const readerExport = document.querySelector<HTMLMetaElement>('meta[name="storygal-reader-export"]')?.content
createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={client}>{readerProject || readerExport ? <ReaderApp projectId={readerProject} exportUrl={readerExport} /> : <App />}</QueryClientProvider></React.StrictMode>)
