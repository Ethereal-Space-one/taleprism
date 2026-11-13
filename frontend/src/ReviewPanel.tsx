import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  type Asset,
  type Character,
  type Dialogue,
  type Evidence,
  type Job,
  type ModelStatus,
  type ReviewState,
} from './api'

type Change = { path: string; body: Record<string, unknown> | FormData; method?: string }
const statusNames = {
  candidate: '待确认',
  confirmed: '已确认',
  rejected: '已排除',
  merged: '已合并',
}

function EvidenceList({ items }: { items: Evidence[] }) {
  return (
    <details className="evidence">
      <summary>原文依据（{items.length} 处）</summary>
      {items.length === 0 ? (
        <p>人工补充的身份，尚未绑定原文证据。</p>
      ) : (
        items.map((e, i) => (
          <blockquote key={i}>
            <p>{e.quote}</p>
            <small>
              原文字节 {e.byte_start}–{e.byte_end}
            </small>
          </blockquote>
        ))
      )}
    </details>
  )
}

function CharacterEditor({
  character,
  onSave,
  pending,
}: {
  character?: Character
  onSave: (body: Record<string, unknown>) => void
  pending: boolean
}) {
  return (
    <form
      className="identity-form"
      onSubmit={(e) => {
        e.preventDefault()
        const data = new FormData(e.currentTarget)
        onSave({
          display_name: String(data.get('display_name')).trim(),
          aliases: String(data.get('aliases') || '')
            .split(/[,，、\n]/)
            .map((s) => s.trim())
            .filter(Boolean),
          description: String(data.get('description') || ''),
          status: 'confirmed',
        })
      }}
    >
      <label>
        角色名称
        <input
          name="display_name"
          required
          maxLength={40}
          defaultValue={character?.display_name || ''}
        />
      </label>
      <label>
        别名与称呼
        <input
          name="aliases"
          defaultValue={character?.aliases.join('、') || ''}
          placeholder="用顿号或逗号分开"
        />
      </label>
      <label>
        身份说明
        <textarea
          name="description"
          maxLength={2000}
          rows={3}
          defaultValue={character?.description || ''}
          placeholder="记录你已核实的身份与形象要求"
        />
      </label>
      <button type="submit" className="primary" disabled={pending}>
        {pending ? '正在保存…' : character ? '保存并确认身份' : '添加并确认角色'}
      </button>
    </form>
  )
}

export function ReviewPanel({
  projectId,
  onLocate,
}: {
  projectId: string
  onLocate: (start: number, end: number) => void
}) {
  const cache = useQueryClient()
  const [section, setSection] = useState<'dialogues' | 'characters'>('dialogues')
  const [filter, setFilter] = useState<'pending' | 'all' | 'unknown'>('pending')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [characterId, setCharacterId] = useState<string | null>(null)
  const [addCharacter, setAddCharacter] = useState(false)
  const [checked, setChecked] = useState<string[]>([])
  const [showAudit, setShowAudit] = useState(false)
  const [notice, setNotice] = useState('')
  const data = useQuery({
    queryKey: ['review', projectId],
    queryFn: () => api<ReviewState>(`/api/projects/${projectId}/review`),
  })
  const model = useQuery({
    queryKey: ['model'],
    queryFn: () => api<ModelStatus & { error?: string }>('/api/llm/status'),
  })
  const jobs = useQuery({
    queryKey: ['jobs', projectId],
    queryFn: () => api<Job[]>(`/api/projects/${projectId}/jobs`),
    refetchInterval: (q) => (q.state.data?.some((j) => j.state === 'running') ? 1000 : false),
  })
  const audit = useQuery({
    queryKey: ['audit', projectId],
    queryFn: () =>
      api<{ id: number; action: string; actor: string; created_at: string }[]>(
        `/api/projects/${projectId}/audit`,
      ),
    enabled: showAudit,
  })
  const state = data.data
  const characters = state?.characters.filter((c) => c.status !== 'merged') || []
  const confirmed = characters.filter((c) => c.status === 'confirmed')
  const character = characters.find((c) => c.id === characterId) || characters[0]
  const candidates = useQuery({
    queryKey: ['character-samples', projectId, character?.id],
    queryFn: () =>
      api<{ key: string; label: string; state: string; kind: string }[]>(
        `/api/projects/${projectId}/characters/${character!.id}/codex-samples`,
      ),
    enabled: !!character,
  })
  const visible = (
    state?.dialogues.filter(
      (d) =>
        filter === 'all' ||
        (filter === 'pending' ? d.status === 'pending' : !d.speaker_id && !d.suggested_speaker_id),
    ) || []
  ).sort((a, b) =>
    filter === 'pending'
      ? a.confidence - b.confidence || a.byte_start - b.byte_start
      : a.byte_start - b.byte_start,
  )
  const ambiguous = [
    ...new Set(
      characters
        .filter((c) => c.status !== 'rejected')
        .flatMap((c) => [c.display_name, ...c.aliases]),
    ),
  ].filter(
    (label) =>
      characters.filter(
        (c) => c.status !== 'rejected' && [c.display_name, ...c.aliases].includes(label),
      ).length > 1,
  )
  const selected = visible.find((d) => d.id === selectedId) || visible[0]
  const analysisJob = jobs.data?.find((j) => j.kind === 'analysis')
  const lastJob = useRef('')
  async function refresh() {
    await Promise.all(
      ['review', 'text', 'audit'].map((key) =>
        cache.invalidateQueries({ queryKey: [key, projectId] }),
      ),
    )
  }
  useEffect(() => {
    if (analysisJob?.state === 'completed' && lastJob.current !== analysisJob.id) {
      lastJob.current = analysisJob.id
      refresh()
    }
  }, [analysisJob?.state, analysisJob?.id])
  const change = useMutation({
    mutationFn: ({ path, body, method = 'PATCH' }: Change) =>
      api(`/api/projects/${projectId}${path}`, {
        method,
        ...(body instanceof FormData
          ? { body }
          : {
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ revision: state?.revision, ...body }),
            }),
      }),
    onSuccess: async () => {
      setNotice('修改已保存。')
      setChecked([])
      await refresh()
    },
    onError: () => cache.invalidateQueries({ queryKey: ['review', projectId] }),
  })
  const analyze = useMutation({
    mutationFn: () =>
      api(`/api/projects/${projectId}/analysis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ allow_remote: true }),
      }),
    onSuccess: () => cache.invalidateQueries({ queryKey: ['jobs', projectId] }),
  })
  const analyzing = analyze.isPending || analysisJob?.state === 'running'
  const busy = change.isPending
  const error =
    candidates.error || data.error || model.error || jobs.error || change.error || analyze.error

  function assign(speakerId: string | null, ids?: string[]) {
    const target = ids || (checked.length ? checked : selected ? [selected.id] : [])
    if (target.length)
      change.mutate({ path: '/dialogues', body: { dialogue_ids: target, speaker_id: speakerId } })
  }
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const element = e.target as HTMLElement
      if (
        /INPUT|TEXTAREA|SELECT|BUTTON/.test(element.tagName) ||
        section !== 'dialogues' ||
        busy ||
        !selected
      )
        return
      if (/^[1-9]$/.test(e.key)) {
        const candidate = confirmed[Number(e.key) - 1]
        if (candidate) {
          e.preventDefault()
          assign(candidate.id, [selected.id])
        }
      }
      if (e.key === '0') {
        e.preventDefault()
        assign(null, [selected.id])
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const index = visible.findIndex((d) => d.id === selected.id)
        setSelectedId(
          visible[
            Math.max(0, Math.min(visible.length - 1, index + (e.key === 'ArrowDown' ? 1 : -1)))
          ]?.id || null,
        )
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [selected?.id, visible, confirmed, busy, section])

  function saveCharacter(body: Record<string, unknown>) {
    change.mutate(
      {
        path: addCharacter || !character ? '/characters' : `/characters/${character.id}`,
        method: addCharacter || !character ? 'POST' : 'PATCH',
        body,
      },
      { onSuccess: () => setAddCharacter(false) },
    )
  }
  function reviewAsset(asset: Asset, status: Asset['status'], active = false) {
    change.mutate({ path: `/assets/${asset.id}`, body: { status, active } })
  }

  return (
    <section className="review-workbench" aria-label="角色与对白审校">
      <div className="review-toolbar">
        <div className="sub-tabs" role="tablist" aria-label="审校内容">
          <button
            role="tab"
            aria-selected={section === 'dialogues'}
            onClick={() => setSection('dialogues')}
          >
            对白审校 <small>{state?.pending_count || 0} 待审</small>
          </button>
          <button
            role="tab"
            aria-selected={section === 'characters'}
            onClick={() => setSection('characters')}
          >
            角色资产 <small>{confirmed.length} 已确认</small>
          </button>
        </div>
        <button
          disabled={analyzing || !model.data?.configured}
          onClick={() => {
            setNotice('')
            analyze.mutate()
          }}
        >
          {analyzing ? 'AI 正在抽取…' : 'AI 抽取候选'}
        </button>
      </div>
      <p className="remote-note">
        点击抽取会将本章文本发送至 {model.data?.provider || '配置的模型服务'}（
        {model.data ? model.data.model || '未设置模型' : '正在读取配置'}
        ）；结果需人工确认，已确认内容会保留。
        {model.data?.base_url && <> 接口：{model.data.base_url}。</>}
        {model.data &&
          !model.data.configured &&
          !model.data.error &&
          ' 尚未检测到本机密钥，请配置 STORYGAL_LLM_API_KEY。'}
      </p>
      {(model.error || model.data?.error) && (
        <p className="error" role="alert">
          {model.data?.error || '无法读取模型配置，请检查本机服务后重试。'}
        </p>
      )}
      {state?.last_analysis && (
        <p className="analysis-note">
          上次抽取：{state.last_analysis.model} · 新请求 {state.last_analysis.requests} 次 ·
          缓存复用 {state.last_analysis.cache_hits} 次
        </p>
      )}
      {analyzing && (
        <p className="notice" role="status">
          正在整理角色与对白候选，可以继续人工审校。
        </p>
      )}
      {analysisJob?.state === 'failed' && (
        <p className="error" role="alert">
          {analysisJob.error}
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error.message}
        </p>
      )}
      {notice && !error && (
        <p className="saved-note" role="status">
          ✓ {notice}
        </p>
      )}
      {ambiguous.length > 0 && (
        <p className="notice">
          这些称呼对应多个角色：{ambiguous.join('、')}
          。请核实身份、合并或修正别名，系统不会自动消歧。
        </p>
      )}
      {data.isPending && <p role="status">正在读取角色和对白…</p>}
      {state && section === 'dialogues' && (
        <>
          <div className="dialogue-filters">
            <label>
              显示范围
              <select
                aria-label="对白筛选"
                value={filter}
                onChange={(e) => {
                  setFilter(e.target.value as typeof filter)
                  setChecked([])
                  setSelectedId(null)
                }}
              >
                <option value="pending">待审核</option>
                <option value="all">全部对白</option>
                <option value="unknown">无候选说话人</option>
              </select>
            </label>
            <span>
              候选 {characters.filter((c) => c.status === 'candidate').length} 人 · 已审核{' '}
              {state.dialogues.length - state.pending_count}/{state.dialogues.length} 句
              {filter === 'pending' ? ' · 低置信度优先' : ''}
            </span>
            <button
              onClick={() => {
                setSection('characters')
                setAddCharacter(true)
              }}
            >
              添加角色
            </button>
          </div>
          <div className="dialogue-review-grid">
            <div className="dialogue-list" aria-label="对白列表">
              {visible.length === 0 && (
                <p className="review-empty">
                  {state.dialogues.length
                    ? '当前筛选下没有待处理对白。'
                    : '没有识别到成对引号对白。可先整理角色身份。'}
                </p>
              )}
              {visible.map((d, index) => {
                const speaker = state.characters.find(
                  (c) => c.id === (d.status === 'reviewed' ? d.speaker_id : d.suggested_speaker_id),
                )
                return (
                  <div
                    key={d.id}
                    className={`dialogue-row ${d.id === selected?.id ? 'selected' : ''}`}
                  >
                    <input
                      type="checkbox"
                      aria-label={`选择对白 ${index + 1}`}
                      checked={checked.includes(d.id)}
                      onChange={(e) =>
                        setChecked((ids) =>
                          e.target.checked ? [...ids, d.id] : ids.filter((id) => id !== d.id),
                        )
                      }
                    />
                    <button
                      onClick={() => setSelectedId(d.id)}
                      aria-label={`审校对白 ${index + 1}`}
                    >
                      <span>{d.text}</span>
                      <small>
                        {d.status === 'reviewed' ? '✓ 已审' : '待审'} ·{' '}
                        {speaker?.display_name || '未知说话人'}
                        {d.status === 'pending' && d.suggested_speaker_id
                          ? ` · ${Math.round(d.confidence * 100)}%`
                          : ''}
                      </small>
                    </button>
                  </div>
                )
              })}
            </div>
            <div className="dialogue-detail">
              {selected ? (
                <>
                  <h2>确认这句的说话人</h2>
                  <p className="context-before">{selected.context_before}</p>
                  <blockquote className="dialogue-quote" data-testid="review-dialogue">
                    {selected.text}
                  </blockquote>
                  <p className="context-after">{selected.context_after}</p>
                  <p className="review-instruction">
                    {checked.length
                      ? `将同时修改勾选的 ${checked.length} 句。`
                      : '选择已确认角色，或保留未知。'}{' '}
                    只有人工确认的归属进入导出。
                  </p>
                  <div className="speaker-buttons">
                    {confirmed.map((c, i) => (
                      <button
                        key={c.id}
                        disabled={busy}
                        className={selected.speaker_id === c.id ? 'speaker-current' : ''}
                        onClick={() => assign(c.id)}
                      >
                        {i < 9 && <kbd>{i + 1}</kbd>}
                        {c.display_name}
                      </button>
                    ))}
                    <button disabled={busy} onClick={() => assign(null)}>
                      <kbd>0</kbd>保留未知
                    </button>
                  </div>
                  {!confirmed.length && (
                    <p className="notice">先在「角色资产」里确认人物身份，再指定说话人。</p>
                  )}
                  <button
                    className="text-button"
                    onClick={() => onLocate(selected.outer_start, selected.outer_end)}
                  >
                    定位原文 →
                  </button>
                  <EvidenceList items={selected.evidence} />
                  <p className="keyboard-hint">数字键选择角色，0 保留未知，↑ ↓ 切换对白</p>
                </>
              ) : (
                <p className="review-empty">选择一条对白查看上下文。</p>
              )}
            </div>
          </div>
        </>
      )}
      {state && section === 'characters' && (
        <div className="character-workspace">
          <aside className="character-list" aria-label="角色列表">
            <button onClick={() => setAddCharacter(true)}>＋ 新建角色</button>
            {characters.map((c) => (
              <button
                key={c.id}
                aria-label={`编辑角色 ${c.display_name}`}
                className={!addCharacter && character?.id === c.id ? 'selected' : ''}
                onClick={() => {
                  setCharacterId(c.id)
                  setAddCharacter(false)
                  change.reset()
                  setNotice('')
                }}
              >
                <strong>{c.display_name}</strong>
                <small>
                  {statusNames[c.status]}
                  {c.aliases.length ? ` · ${c.aliases.join('、')}` : ''}
                </small>
              </button>
            ))}
          </aside>
          <div className="character-editor">
            <div className="panel-head">
              <h2>{addCharacter || !character ? '新建角色身份' : character.display_name}</h2>
              <span>{!addCharacter && character ? statusNames[character.status] : '人工补充'}</span>
            </div>
            <CharacterEditor
              key={addCharacter ? 'new' : character?.id}
              character={addCharacter ? undefined : character}
              onSave={saveCharacter}
              pending={busy}
            />
            {character && !addCharacter && (
              <>
                <EvidenceList items={character.evidence} />
                <div className="identity-actions">
                  <button
                    disabled={busy}
                    onClick={() =>
                      change.mutate({
                        path: `/characters/${character.id}`,
                        body: {
                          display_name: character.display_name,
                          aliases: character.aliases,
                          description: character.description,
                          status: 'rejected',
                        },
                      })
                    }
                  >
                    排除该候选
                  </button>
                  <form
                    key={`merge-${character.id}`}
                    onSubmit={(e) => {
                      e.preventDefault()
                      const target = new FormData(e.currentTarget).get('target')
                      if (target)
                        change.mutate({
                          path: `/characters/${character.id}/merge`,
                          method: 'POST',
                          body: { target_id: target },
                        })
                    }}
                  >
                    <select name="target" aria-label="合并目标" required defaultValue="">
                      <option value="" disabled>
                        同一人物？合并到…
                      </option>
                      {characters
                        .filter((c) => c.id !== character.id && c.status !== 'rejected')
                        .map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.display_name}
                          </option>
                        ))}
                    </select>
                    <button disabled={busy}>合并角色</button>
                  </form>
                </div>
                <section className="character-assets">
                  <div className="panel-head">
                    <h2>参考图与立绘</h2>
                    <span>只复用已接受资产</span>
                  </div>
                  <p className="asset-helper">
                    上传自有或获授权图像，或导入本次 Codex
                    生成的候选图。接受后可设为当前立绘；同角色多处复用同一文件。
                  </p>
                  <form
                    key={`codex-${character.id}`}
                    className="codex-import"
                    onSubmit={(e) => {
                      e.preventDefault()
                      change.mutate({
                        path: `/characters/${character.id}/codex-sample`,
                        method: 'POST',
                        body: { sample_key: new FormData(e.currentTarget).get('sample_key') },
                      })
                    }}
                  >
                    <label>
                      Codex 候选图
                      <select
                        name="sample_key"
                        aria-label="Codex 候选图"
                        required
                        key={character.id + ':' + (candidates.data?.length || 0)}
                        defaultValue={candidates.data?.[0]?.key || ''}
                      >
                        {candidates.data?.length ? (
                          candidates.data.map((c) => (
                            <option key={c.key} value={c.key}>
                              {c.label}
                              {c.state === 'base' ? ' · 基础' : ' · 状态'}
                            </option>
                          ))
                        ) : (
                          <option value="">此角色暂无内置候选，可上传已有图像</option>
                        )}
                      </select>
                    </label>
                    <button disabled={busy || !candidates.data?.length}>导入 Codex 候选图</button>
                  </form>
                  <form
                    key={`upload-${character.id}`}
                    className="asset-upload"
                    onSubmit={(e) => {
                      e.preventDefault()
                      const form = new FormData(e.currentTarget)
                      form.set('revision', String(state.revision))
                      change.mutate({
                        path: `/characters/${character.id}/assets`,
                        method: 'POST',
                        body: form,
                      })
                    }}
                  >
                    <label>
                      图像文件
                      <input
                        type="file"
                        name="file"
                        accept="image/png,image/jpeg,image/webp"
                        required
                      />
                    </label>
                    <label>
                      用途
                      <select name="kind" defaultValue="reference_and_figure">
                        <option value="reference_and_figure">参考图，同时用作立绘</option>
                        <option value="reference">仅作为参考图</option>
                        <option value="figure">立绘／表情差分</option>
                      </select>
                    </label>
                    <label>
                      来源与许可
                      <input
                        name="license_text"
                        maxLength={1000}
                        required
                        placeholder="如：本人绘制，仅用于本项目"
                      />
                    </label>
                    <button disabled={busy}>上传为待确认图</button>
                  </form>
                  <div className="assets-grid">
                    {state.assets
                      .filter((a) => a.character_id === character.id)
                      .map((asset) => (
                        <article className="asset-item" key={asset.id}>
                          <img
                            src={asset.url}
                            alt={`${character.display_name}的${asset.kind === 'reference' ? '参考图' : '候选立绘'}`}
                          />
                          <p>
                            {asset.label && <strong>{asset.label} · </strong>}
                            {asset.status === 'accepted'
                              ? '✓ 已接受'
                              : asset.status === 'rejected'
                                ? '已拒绝'
                                : '待确认'}
                            {character.active_figure_id === asset.id ? ' · 当前立绘' : ''}
                          </p>
                          <small>
                            {asset.width} × {asset.height} ·{' '}
                            {asset.origin === 'codex_imagegen' ? 'Codex 生图' : '本机上传'}
                          </small>
                          <p className="asset-license">{asset.license}</p>
                          <div className="asset-actions">
                            <button
                              disabled={
                                busy ||
                                (character.active_figure_id === asset.id &&
                                  asset.status === 'accepted')
                              }
                              onClick={() =>
                                reviewAsset(asset, 'accepted', asset.kind !== 'reference')
                              }
                            >
                              {asset.kind === 'reference' ? '接受参考图' : '接受并设为立绘'}
                            </button>
                            <button disabled={busy} onClick={() => reviewAsset(asset, 'rejected')}>
                              拒绝
                            </button>
                          </div>
                        </article>
                      ))}
                  </div>
                </section>
              </>
            )}
          </div>
        </div>
      )}
      <details className="review-audit" onToggle={(e) => setShowAudit(e.currentTarget.open)}>
        <summary>操作记录</summary>
        {audit.error && <p role="alert">读取记录失败，请重新展开。</p>}
        {audit.data?.map((a) => (
          <p key={a.id}>
            <time>
              {new Date(a.created_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}
            </time>{' '}
            · {a.actor} ·{' '}
            {(
              {
                'character.update': '保存角色身份',
                'character.merge': '合并角色',
                'dialogue.assign': '修正对白归属',
                'asset.upload': '导入候选图',
                'asset.review': '审核图像',
                'analysis.apply': '应用 AI 候选',
              } as Record<string, string>
            )[a.action] || a.action}
          </p>
        ))}
      </details>
    </section>
  )
}
