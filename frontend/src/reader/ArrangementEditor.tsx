import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type ReviewState } from '../api'
import type {
  ReaderConfig,
  ReaderContent,
  ReaderMapEntry,
  ReaderPresentation,
  ReaderState,
} from '../reader-types'
import { byteLength } from './model'
import { IllustrationEditor } from './IllustrationEditor'

type Issue = {
  id?: string
  anchor: number
  category: 'visual' | 'cast' | 'audio' | 'map' | 'reading'
  note: string
  state: 'open' | 'resolved' | 'deferred'
  reason: string
  versions?: Record<string, number>
}
type Editorial = { revision: number; issues: Issue[] }
export function ArrangementEditor({
  projectId,
  state,
  review,
  content,
}: {
  projectId: string
  state: ReaderState
  review?: ReviewState
  content?: ReaderContent
}) {
  const cache = useQueryClient(),
    prefix = `/api/projects/${projectId}/reader`
  const [draft, setDraft] = useState<ReaderConfig>(() => ({
    ...state.config,
    presentations: state.config.presentations?.length
      ? state.config.presentations
      : content?.presentations || [],
    map_entries: state.config.map_entries || [],
  }))
  const [baseRevision, setBaseRevision] = useState(state.revision),
    [dirty, setDirty] = useState(false)
  const [paragraphIndex, setParagraphIndex] = useState(0),
    [anchor, setAnchor] = useState(state.paragraphs[0].byte_start)
  const [category, setCategory] = useState<Issue['category']>('visual'),
    [note, setNote] = useState(''),
    [mapLabel, setMapLabel] = useState('查看此处战局'),
    [phase, setPhase] = useState('opposition'),
    [place, setPlace] = useState('chibi')
  useEffect(() => {
    if (!dirty && state.revision !== baseRevision) {
      setDraft({
        ...state.config,
        presentations: state.config.presentations?.length
          ? state.config.presentations
          : content?.presentations || [],
        map_entries: state.config.map_entries || [],
      })
      setBaseRevision(state.revision)
    }
  }, [state, content, dirty, baseRevision])
  const [issueReasons, setIssueReasons] = useState<Record<string, string>>({})
  const editorial = useQuery({
    queryKey: ['editorial', projectId],
    queryFn: () => api<Editorial>(prefix + '/editorial'),
  })
  async function refresh() {
    await Promise.all(
      ['reader', 'reader-content', 'delivery', 'editorial'].map((k) =>
        cache.invalidateQueries({ queryKey: [k, projectId] }),
      ),
    )
  }
  const save = useMutation({
    mutationFn: () =>
      api(prefix, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision: baseRevision, ...draft }),
      }),
    onSuccess: async () => {
      await refresh()
      setBaseRevision(baseRevision + 1)
      setDirty(false)
    },
    onError: refresh,
  })
  const issueSave = useMutation({
    mutationFn: (issue: Issue) =>
      api(prefix + '/editorial', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision: editorial.data?.revision || 0, ...issue }),
      }),
    onSuccess: async () => {
      setNote('')
      await refresh()
    },
    onError: refresh,
  })
  const sample = useMutation({
    mutationFn: (expanded: boolean | 'second' | 'narrative' | 'import') =>
      api<ReaderState>(
        prefix +
          (expanded === 'import'
            ? '/narrative/sample'
            : expanded === 'narrative'
              ? '/choreography/narrative-sample'
              : expanded === 'second'
                ? '/choreography/second-sample'
                : expanded
                  ? '/choreography/expanded-sample'
                  : '/choreography/sample'),
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ revision: baseRevision }),
        },
      ),
    onSuccess: async (next) => {
      setDraft(next.config)
      setBaseRevision(next.revision)
      setDirty(false)
      await refresh()
    },
  })
  const paragraph = state.paragraphs[paragraphIndex]
  const chars = review?.characters.filter((c) => c.status === 'confirmed') || []
  function anchorQuote(byte: number) {
    const p = state.paragraphs.find((p) => p.byte_start <= byte && byte < p.byte_end)
    return p
      ? new TextDecoder()
          .decode(new TextEncoder().encode(p.text).slice(byte - p.byte_start))
          .slice(0, 70)
      : '原文边界'
  }
  const source =
    state.paragraphs.find((p) => p.byte_start <= anchor && p.byte_end > anchor)?.text || ''
  function update(next: Partial<ReaderConfig>) {
    setDraft((v) => ({ ...v, ...next }))
    setDirty(true)
  }
  function patch(id: string, change: Partial<ReaderPresentation>) {
    update({
      presentations: draft.presentations!.map((p) => (p.id === id ? { ...p, ...change } : p)),
    })
  }
  function add() {
    const scene = draft.scenes.filter((s) => s.start_byte <= anchor).at(-1)
    if (!scene) return
    const current = draft.presentations?.filter((p) => p.start_byte <= anchor).at(-1)
    const next: ReaderPresentation = {
      id: crypto.randomUUID(),
      start_byte: anchor,
      scene_id: scene.id,
      kind: 'environment',
      image_asset_id: scene.asset_id,
      place_label: scene.title,
      time_label: '',
      cast: [],
      ...current,
      ...(current ? { id: crypto.randomUUID(), start_byte: anchor, scene_id: scene.id } : {}),
    }
    const existing = draft.presentations?.filter((p) => p.start_byte !== anchor) || []
    update({ presentations: [...existing, next].sort((a, b) => a.start_byte - b.start_byte) })
  }
  const error = save.error || issueSave.error || sample.error || editorial.error
  return (
    <section className="reader-arrangement" aria-label="章节编排与意见">
      <h3>章节编排与位置意见</h3>
      <p>先选择原文位置，再编排画面。人物是否在场以这里为准；说到某人不会让他自动登场。</p>
      {error && (
        <p role="alert" className="error">
          {error.message} 草稿仍在。
        </p>
      )}
      {state.revision !== baseRevision && (
        <p role="status">
          制作配置已有更新。当前草稿保留，请先复制需要保留的修改，再载入最新版本。
        </p>
      )}
      <div className="reader-arrangement-tools">
        <button disabled={save.isPending || !dirty} onClick={() => save.mutate()}>
          保存章节编排
        </button>
        <button
          onClick={() => {
            setDraft({
              ...state.config,
              presentations: state.config.presentations?.length
                ? state.config.presentations
                : content?.presentations || [],
            })
            setBaseRevision(state.revision)
            setDirty(false)
          }}
        >
          载入最新配置
        </button>
        <button
          disabled={
            !state.chibi_sample || dirty || sample.isPending || state.revision !== baseRevision
          }
          onClick={() => sample.mutate(false)}
        >
          应用赤壁人物与事件编排
        </button>
        <button
          disabled={
            !state.chibi_sample || dirty || sample.isPending || state.revision !== baseRevision
          }
          onClick={() => sample.mutate(true)}
        >
          应用六角色首批编排
        </button>
        <button
          disabled={
            !state.chibi_sample || dirty || sample.isPending || state.revision !== baseRevision
          }
          onClick={() => sample.mutate('second')}
        >
          应用八角色二期编排
        </button>
        <button
          disabled={
            !state.chibi_sample || dirty || sample.isPending || state.revision !== baseRevision
          }
          onClick={() => sample.mutate('import')}
        >
          导入十二张叙事图候选
        </button>
        <button
          disabled={
            !state.chibi_sample || dirty || sample.isPending || state.revision !== baseRevision
          }
          onClick={() => sample.mutate('narrative')}
        >
          应用章节画卷编排
        </button>
      </div>
      <label>
        选择原文段落
        <select
          value={paragraphIndex}
          onChange={(e) => {
            const i = Number(e.target.value)
            setParagraphIndex(i)
            setAnchor(state.paragraphs[i].byte_start)
          }}
        >
          {state.paragraphs.map((p, i) => (
            <option value={i} key={p.byte_start}>
              第{i + 1}段 · {p.preview}
            </option>
          ))}
        </select>
      </label>
      <label>
        在原文中点选或选择文字，从选择的起点变化
        <textarea
          className="reader-source-picker"
          readOnly
          value={paragraph.text}
          onSelect={(e) =>
            setAnchor(
              paragraph.byte_start +
                byteLength(e.currentTarget.value.slice(0, e.currentTarget.selectionStart)),
            )
          }
        />
      </label>
      <p>
        当前位置：
        {source
          ? new TextDecoder()
              .decode(
                new TextEncoder()
                  .encode(source)
                  .slice(
                    Math.max(
                      0,
                      anchor -
                        (state.paragraphs.find((p) => p.byte_start <= anchor && p.byte_end > anchor)
                          ?.byte_start || 0),
                    ),
                  ),
              )
              .slice(0, 45)
          : '段落边界'}
      </p>
      <button disabled={!draft.scenes.length} onClick={add}>
        从这里变化
      </button>
      <IllustrationEditor draft={draft} state={state} anchor={anchor} update={update} />
      {(draft.presentations || []).map((p) => (
        <div className="reader-arrangement-row" key={p.id}>
          <p>
            {anchorQuote(p.start_byte)} · {p.start_byte === anchor ? '当前选择' : '原文内变化'}
          </p>
          <div>
            <label>
              呈现类型
              <select
                value={p.kind}
                onChange={(e) =>
                  patch(p.id, {
                    kind: e.target.value as ReaderPresentation['kind'],
                    ...(e.target.value === 'event' ? { cast: [] } : {}),
                  })
                }
              >
                <option value="environment">环境</option>
                <option value="dialogue">对话</option>
                <option value="event">事件插画</option>
              </select>
            </label>
            <label>
              画面
              <select
                value={p.image_asset_id}
                onChange={(e) => patch(p.id, { image_asset_id: e.target.value })}
              >
                {state.assets
                  .filter((a) => a.kind === 'scene' && a.status !== 'rejected')
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.sample_key || '上传场景'} · {a.status === 'accepted' ? '已接受' : '候选'}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              地点
              <input
                maxLength={80}
                value={p.place_label}
                onChange={(e) => patch(p.id, { place_label: e.target.value })}
              />
            </label>
            <label>
              时间
              <input
                maxLength={40}
                value={p.time_label}
                onChange={(e) => patch(p.id, { time_label: e.target.value })}
              />
            </label>
          </div>
          {p.kind !== 'event' && (
            <div>
              {(['left', 'right'] as const).map((slot) => (
                <label key={slot}>
                  {slot === 'left' ? '左侧人物' : '右侧人物'}
                  <select
                    value={p.cast.find((c) => c.slot === slot)?.figure_asset_id || ''}
                    onChange={(e) => {
                      const a = state.figures?.find((a) => a.id === e.target.value)
                      patch(p.id, {
                        cast: [
                          ...p.cast.filter((c) => c.slot !== slot),
                          ...(a
                            ? [{ slot, character_id: a.character_id, figure_asset_id: a.id }]
                            : []),
                        ],
                      })
                    }}
                  >
                    <option value="">不展示人物</option>
                    {state.figures
                      ?.filter((a) => chars.some((c) => c.id === a.character_id))
                      .map((a) => (
                        <option value={a.id} key={a.id}>
                          {a.label || chars.find((c) => c.id === a.character_id)?.display_name} ·
                          立绘{' '}
                          {(state.figures || [])
                            .filter((f) => f.character_id === a.character_id)
                            .findIndex((f) => f.id === a.id) + 1}{' '}
                          · {a.status === 'accepted' ? '已接受' : '候选'}
                        </option>
                      ))}
                  </select>
                </label>
              ))}
            </div>
          )}
          <div>
            <a
              href={`/read/${projectId}?at=${p.start_byte}&editing=1`}
              target="_blank"
              rel="noreferrer"
            >
              从这里预览 ↗
            </a>
            <button
              onClick={() => {
                setAnchor(p.start_byte)
                setParagraphIndex(
                  Math.max(
                    0,
                    state.paragraphs.findIndex(
                      (b) => b.byte_start <= p.start_byte && b.byte_end > p.start_byte,
                    ),
                  ),
                )
              }}
            >
              定位原文
            </button>
            <button
              onClick={() => {
                const scene = draft.scenes.filter((s) => s.start_byte <= anchor).at(-1)
                if (scene)
                  update({
                    presentations: draft
                      .presentations!.map((i) =>
                        i.id === p.id ? { ...i, start_byte: anchor, scene_id: scene.id } : i,
                      )
                      .sort((a, b) => a.start_byte - b.start_byte),
                  })
              }}
            >
              移至所选位置
            </button>
            <button
              onClick={() =>
                update({ presentations: draft.presentations!.filter((i) => i.id !== p.id) })
              }
            >
              移除呈现
            </button>
          </div>
        </div>
      ))}
      {draft.map_profile && (
        <details>
          <summary>正文地图入口</summary>
          <div className="reader-arrangement-tools">
            <label>
              入口文字
              <input
                value={mapLabel}
                maxLength={80}
                onChange={(e) => setMapLabel(e.target.value)}
              />
            </label>
            <label>
              阶段
              <select value={phase} onChange={(e) => setPhase(e.target.value)}>
                <option value="opposition">夹江对峙</option>
                <option value="fire">火攻推进</option>
                <option value="retreat">战后撤军</option>
              </select>
            </label>
            <label>
              地点
              <select value={place} onChange={(e) => setPlace(e.target.value)}>
                {content?.map?.places.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={() => {
                const b = state.paragraphs.find(
                  (b) => b.byte_start <= anchor && b.byte_end > anchor,
                )
                if (b)
                  update({
                    map_entries: [
                      ...(draft.map_entries || []),
                      {
                        id: crypto.randomUUID(),
                        byte_start: anchor,
                        byte_end: b.byte_end,
                        label: mapLabel,
                        phase_id: phase,
                        place_ids: [place],
                      },
                    ],
                  })
              }}
            >
              在所选位置添加入口
            </button>
          </div>
          {draft.map_entries?.map((e: ReaderMapEntry) => (
            <p key={e.id}>
              {e.label} ·{' '}
              {
                (
                  { opposition: '夹江对峙', fire: '火攻推进', retreat: '战后撤军' } as Record<
                    string,
                    string
                  >
                )[e.phase_id]
              }
              <button
                onClick={() =>
                  update({ map_entries: draft.map_entries!.filter((i) => i.id !== e.id) })
                }
              >
                移除入口
              </button>
            </p>
          ))}
        </details>
      )}
      <details open>
        <summary>制作意见</summary>
        <label>
          问题类型
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as Issue['category'])}
          >
            <option value="visual">画面</option>
            <option value="cast">人物出场</option>
            <option value="audio">声音</option>
            <option value="map">地图</option>
            <option value="reading">阅读操作</option>
          </select>
        </label>
        <label>
          在所选原文位置记录意见
          <textarea value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button
          disabled={!note.trim() || issueSave.isPending}
          onClick={() => issueSave.mutate({ anchor, category, note, state: 'open', reason: '' })}
        >
          保存位置意见
        </button>
        {editorial.data?.issues.map((i) => (
          <div className="reader-editorial-item" key={i.id}>
            <p>
              {i.note} ·{' '}
              {i.state === 'open' ? '未处理' : i.state === 'resolved' ? '已处理' : '已延期'}
            </p>
            {i.versions && i.versions.reader_revision !== state.revision && (
              <p>内容已更新，请重新核对这条意见。</p>
            )}
            <div className="reader-arrangement-tools">
              <a
                href={`/read/${projectId}?at=${i.anchor}&editing=1`}
                target="_blank"
                rel="noreferrer"
              >
                查看问题位置 ↗
              </a>
              <button
                onClick={() => {
                  setAnchor(i.anchor)
                  setParagraphIndex(
                    Math.max(
                      0,
                      state.paragraphs.findIndex(
                        (b) => b.byte_start <= i.anchor && b.byte_end > i.anchor,
                      ),
                    ),
                  )
                }}
              >
                定位编辑
              </button>
              <button
                disabled={issueSave.isPending}
                onClick={() =>
                  issueSave.mutate({
                    id: i.id,
                    anchor: i.anchor,
                    category: i.category,
                    note: i.note,
                    reason: '',
                    state: 'resolved',
                  })
                }
              >
                确认已处理
              </button>
              <button
                disabled={issueSave.isPending}
                onClick={() =>
                  issueSave.mutate({
                    id: i.id,
                    anchor: i.anchor,
                    category: i.category,
                    note: i.note,
                    reason: '',
                    state: 'open',
                  })
                }
              >
                重新打开
              </button>
              <label>
                延期理由
                <input
                  value={issueReasons[i.id!] || ''}
                  onChange={(e) => setIssueReasons((v) => ({ ...v, [i.id!]: e.target.value }))}
                />
              </label>
              <button
                disabled={!issueReasons[i.id!]?.trim() || issueSave.isPending}
                onClick={() =>
                  issueSave.mutate({
                    id: i.id,
                    anchor: i.anchor,
                    category: i.category,
                    note: i.note,
                    state: 'deferred',
                    reason: issueReasons[i.id!],
                  })
                }
              >
                记录延期
              </button>
            </div>
          </div>
        ))}
      </details>
    </section>
  )
}
