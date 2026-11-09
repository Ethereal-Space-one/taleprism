import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Span, type PresentationUnit } from './api'

type Node = { id: string; label: string; evidence_span_ids: number[] }
type Edge = { from_id: string; to_id: string; label: string; evidence_span_ids: number[]; directed: boolean }
type Graph = { nodes: Node[]; edges: Edge[] }
type Item = { id: string; kind: 'illustration' | 'diagram'; title: string; anchor_byte: number; evidence_span_ids: number[]; graph: Graph | null; status: string; enabled: boolean; stale: boolean; prompt: string; evidence: { span_id: number; quote: string }[]; asset: { id: string; url: string; license: string; origin: string } | null }
export type VisualState = { revision: number; style: string; budget: number; items: Item[]; styles: Record<string, { name: string }> }

function EvidencePicker({ spans, value, onChange }: { spans: Span[]; value: number[]; onChange: (ids: number[]) => void }) {
  const [query, setQuery] = useState('')
  const options = spans.filter(s => s.kind !== 'whitespace' && (s.text.includes(query) || String(s.id) === query)).slice(0, 24)
  return <details className="evidence-picker"><summary>选择原文引句（{value.length} 条）</summary>
    <input type="search" aria-label="搜索原文引句" value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索原文或编号" />
    <div className="evidence-options">{options.map(s => <label key={s.id}><input type="checkbox" checked={value.includes(s.id)} onChange={e => onChange(e.target.checked ? [...value, s.id] : value.filter(id => id !== s.id))} /><span>#{s.id} {s.text}</span></label>)}</div>
    <div className="selected-evidence">{value.map(id => <p key={id}><button type="button" aria-label={`移除引句 ${id}`} onClick={() => onChange(value.filter(i => i !== id))}>×</button><span>#{id} {spans.find(s => s.id === id)?.text}</span></p>)}</div>
  </details>
}

function ItemEditor({ item, kind, spans, units, pending, onSave }: { item?: Item; kind: Item['kind']; spans: Span[]; units: PresentationUnit[]; pending: boolean; onSave: (value: object) => void }) {
  const [refs, setRefs] = useState<number[]>(item?.evidence_span_ids || [])
  const [graph, setGraph] = useState<Graph>(item?.graph || { nodes: [{ id: 'n1', label: '', evidence_span_ids: [] }, { id: 'n2', label: '', evidence_span_ids: [] }], edges: [] })
  return <form className="visual-editor" onSubmit={e => { e.preventDefault(); const form = new FormData(e.currentTarget); onSave({ kind, title: String(form.get('title')), anchor_byte: Number(form.get('anchor')), evidence_span_ids: refs, graph: kind === 'diagram' ? graph : null }) }}>
    <label>项目名称<input name="title" maxLength={80} required defaultValue={item?.title || ''} /></label>
    <label>插入位置（在该显示框之后）<select name="anchor" defaultValue={item?.anchor_byte || units.at(-1)?.byte_end} required>{units.map(u => <option key={u.id} value={u.byte_end}>第 {u.id + 1} 框 · {u.text.slice(0, 30)}</option>)}</select></label>
    <p className="asset-helper">插入位置必须晚于所有引用证据。正文分页变化时，导出会把锚点移到不早于该位置的显示框结束处。</p>
    <EvidencePicker spans={spans} value={refs} onChange={setRefs} />
    {kind === 'diagram' && <div className="graph-editor"><h3>节点（最多 4 个）</h3>{graph.nodes.map((node, index) => <section className="graph-element" key={node.id}>
      <div className="graph-element-head"><strong>节点 {index + 1}</strong><button type="button" onClick={() => setGraph(g => ({ nodes: g.nodes.filter(n => n.id !== node.id), edges: g.edges.filter(e => e.from_id !== node.id && e.to_id !== node.id) }))}>移除节点</button></div>
      <label>原文名称<input value={node.label} maxLength={20} required onChange={e => setGraph(g => ({ ...g, nodes: g.nodes.map(n => n.id === node.id ? { ...n, label: e.target.value } : n) }))} /></label>
      <EvidencePicker spans={spans} value={node.evidence_span_ids} onChange={ids => setGraph(g => ({ ...g, nodes: g.nodes.map(n => n.id === node.id ? { ...n, evidence_span_ids: ids } : n) }))} />
    </section>)}
      <button type="button" disabled={graph.nodes.length >= 4} onClick={() => setGraph(g => ({ ...g, nodes: [...g.nodes, { id: `n${Date.now()}`, label: '', evidence_span_ids: [] }] }))}>＋ 添加节点</button>
      <h3>连线（最多 6 条）</h3>{graph.edges.map((edge, i) => <section className="graph-element" key={i}>
        <div className="edge-endpoints"><label>起点<select required value={edge.from_id} onChange={e => setGraph(g => ({ ...g, edges: g.edges.map((x, j) => i === j ? { ...x, from_id: e.target.value } : x) }))}>{graph.nodes.map(n => <option key={n.id} value={n.id}>{n.label || n.id}</option>)}</select></label><label>终点<select required value={edge.to_id} onChange={e => setGraph(g => ({ ...g, edges: g.edges.map((x, j) => i === j ? { ...x, to_id: e.target.value } : x) }))}>{graph.nodes.map(n => <option key={n.id} value={n.id}>{n.label || n.id}</option>)}</select></label></div>
        <label>连线原文用词<input maxLength={20} required value={edge.label} onChange={e => setGraph(g => ({ ...g, edges: g.edges.map((x, j) => i === j ? { ...x, label: e.target.value } : x) }))} /></label>
        <label className="inline-check"><input type="checkbox" checked={edge.directed} onChange={e => setGraph(g => ({ ...g, edges: g.edges.map((x, j) => i === j ? { ...x, directed: e.target.checked } : x) }))} />使用方向箭头（需原文支持方向）</label>
        <EvidencePicker spans={spans} value={edge.evidence_span_ids} onChange={ids => setGraph(g => ({ ...g, edges: g.edges.map((x, j) => i === j ? { ...x, evidence_span_ids: ids } : x) }))} />
        <button type="button" onClick={() => setGraph(g => ({ ...g, edges: g.edges.filter((_, j) => j !== i) }))}>移除连线</button>
      </section>)}
      <button type="button" disabled={graph.edges.length >= 6 || graph.nodes.length < 2} onClick={() => setGraph(g => ({ ...g, edges: [...g.edges, { from_id: g.nodes[0].id, to_id: g.nodes[1].id, label: '', evidence_span_ids: [], directed: false }] }))}>＋ 添加连线</button>
    </div>}
    <button className="primary" disabled={pending || !refs.length || (kind === 'diagram' && !graph.nodes.length)}>保存计划与证据</button>
  </form>
}

export function VisualPanel({ projectId, spans, units }: { projectId: string; spans: Span[]; units: PresentationUnit[] }) {
  const cache = useQueryClient()
  const state = useQuery({ queryKey: ['visual', projectId], queryFn: () => api<VisualState>(`/api/projects/${projectId}/visual`) })
  const [id, setId] = useState<string | null>(null)
  const [adding, setAdding] = useState<Item['kind'] | null>(null)
  const [verified, setVerified] = useState(false)
  const data = state.data
  const item = data?.items.find(i => i.id === id) || data?.items[0]
  const change = useMutation({ mutationFn: ({ path, body = {}, method = 'POST' }: { path: string; body?: object | FormData; method?: string }) => api<any>(`/api/projects/${projectId}/visual${path}`, { method, ...(body instanceof FormData ? { body } : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision: data?.revision, ...body }) }) }),
    onSuccess: async result => { if (result?.kind && result?.id) { setId(result.id); setAdding(null) }; await cache.invalidateQueries({ queryKey: ['visual', projectId] }); setVerified(false) },
    onError: () => cache.invalidateQueries({ queryKey: ['visual', projectId] }) })
  const error = state.error || change.error
  return <section className="visual-workbench" aria-label="视觉与图解制作">
    <div className="panel-head"><h2>视觉与图解</h2><span>先核对证据，再接受图像</span></div>
    <p className="asset-helper">情节插图由 Codex 会话生成后导入；图解由程序绘制事实标签。这里只整理有原文依据的关系与路线，不推测地理坐标。</p>
    {error && <p className="error" role="alert">{error.message}</p>}
    {change.isPending && <p role="status">正在保存或绘制…</p>}
    {change.isSuccess && !change.isPending && <p className="saved-note">✓ 视觉计划已更新。</p>}
    {data && <>
      <form className="visual-settings" key={data.revision} onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); change.mutate({ path: '/settings', method: 'PATCH', body: { style: f.get('style'), budget: Number(f.get('budget')) } }) }}>
        <label>统一风格<select name="style" defaultValue={data.style}>{Object.entries(data.styles).map(([key, value]) => <option key={key} value={key}>{value.name}</option>)}</select></label>
        <label>本章插图预算<input type="number" name="budget" min={0} max={6} defaultValue={data.budget} required /></label><button disabled={change.isPending}>保存风格与预算</button>
      </form><p className="asset-helper">改变风格会撤销旧图确认并停用；已启用插图不能超过预算，图解不占插图预算。</p>
      <div className="visual-actions"><button disabled={change.isPending} onClick={() => change.mutate({ path: '/propose' })}>整理插图候选</button><button onClick={() => { setAdding('illustration'); setVerified(false) }}>新建插图</button><button onClick={() => { setAdding('diagram'); setVerified(false) }}>新建图解</button><button disabled={change.isPending} onClick={() => change.mutate({ path: '/sample-diagram' })}>导入赤壁证据图解</button></div>
      <div className="visual-layout"><aside className="visual-list">{data.items.map(i => <button key={i.id} className={!adding && item?.id === i.id ? 'selected' : ''} onClick={() => { setId(i.id); setAdding(null); setVerified(false); change.reset() }}><strong>{i.kind === 'diagram' ? '图解' : '插图'} · {i.title}</strong><small>{i.status === 'accepted' ? '已接受' : i.status === 'rejected' ? '已拒绝' : '待确认'}{i.enabled ? ' · 已启用' : ' · 未启用'}{i.stale ? ' · 已过期' : ''}</small></button>)}</aside>
      <div className="visual-detail">{adding || item ? <>
        <h3>{adding ? `新建${adding === 'diagram' ? '图解' : '插图'}` : item?.title}</h3>
        <details className="visual-edit-details" open={!!adding}><summary>{adding ? '填写新计划、位置与证据' : '编辑位置、节点、连线与证据'}</summary><ItemEditor key={adding || `${item?.id}:${data.revision}`} item={adding ? undefined : item} kind={adding || item!.kind} spans={spans} units={units} pending={change.isPending} onSave={body => change.mutate({ path: adding ? '/items' : `/items/${item!.id}`, method: adding ? 'POST' : 'PUT', body })} /></details>
        {!adding && item && <>
          <details className="evidence"><summary>本项目全部原文依据（{item.evidence.length} 条）</summary>{item.evidence.map(e => <blockquote key={e.span_id}>#{e.span_id} {e.quote}</blockquote>)}</details>
          {item.kind === 'diagram' ? <button disabled={change.isPending} onClick={() => change.mutate({ path: `/items/${item.id}/render` })}>生成图解预览</button> : <>
            <details className="visual-prompt"><summary>给 Codex 的生图提示词</summary><p>{item.prompt}</p><p>在会话生成新图后保存到本机，再在下方上传。</p></details>
            <button disabled={change.isPending || data.style !== 'ink'} onClick={() => change.mutate({ path: `/items/${item.id}/codex-sample` })}>导入 Codex 赤壁火船候选图</button><p className="asset-helper">该候选仅适合火船场景及水墨淡彩风格，须人工对照本项目引句。</p>
            <form className="visual-upload" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); f.set('revision', String(data.revision)); change.mutate({ path: `/items/${item.id}/upload`, body: f }) }}><label>插图文件<input name="file" type="file" accept="image/png,image/jpeg,image/webp" required /></label><label>来源与许可<input name="license_text" maxLength={1000} required /></label><button disabled={change.isPending}>上传为待确认插图</button></form>
          </>}
          {item.asset && <figure className="visual-preview"><img src={item.asset.url} alt={item.kind === 'diagram' ? '根据原文生成的示意图预览' : '待审核情节插图'} /><figcaption>{item.asset.license}{item.stale ? ' · 配置已变，请重新生成。' : ''}</figcaption>{item.kind === 'diagram' && <a href={item.asset.url.replace('.png', '.svg')} target="_blank" rel="noreferrer">查看 SVG 源图 ↗</a>}</figure>}
          {item.kind === 'diagram' && <label className="inline-check"><input type="checkbox" checked={verified} onChange={e => setVerified(e.target.checked)} />我已逐项核对节点、连线和方向的原文依据</label>}
          <div className="visual-actions"><button disabled={change.isPending || !item.asset || item.stale || (item.kind === 'diagram' && !verified)} onClick={() => change.mutate({ path: `/items/${item.id}/review`, method: 'PATCH', body: { status: 'accepted', enabled: true, evidence_confirmed: verified } })}>接受并启用</button><button disabled={change.isPending} onClick={() => change.mutate({ path: `/items/${item.id}/review`, method: 'PATCH', body: { status: item.status === 'accepted' ? 'accepted' : 'draft', enabled: false, evidence_confirmed: item.kind === 'diagram' ? verified : false } })}>停用</button><button disabled={change.isPending} onClick={() => change.mutate({ path: `/items/${item.id}/review`, method: 'PATCH', body: { status: 'rejected', enabled: false } })}>拒绝</button></div>
        </>}
      </> : <p className="review-empty">还没有视觉计划。整理候选或新建一张图解开始。</p>}</div></div>
    </>}
  </section>
}
