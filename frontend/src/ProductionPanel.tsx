import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type ReviewState } from './api'
import type { ReaderState } from './reader-types'
import { ShotExchange, type ImageTasks } from './ShotExchange'
import { BundleBackup } from './BundleBackup'
import {
  SceneLibrary,
  ShotContinuity,
  emptyContinuity,
  type Scene,
  type Continuity,
  type Check,
  type CheckDecision,
  type CheckDraft,
} from './ContinuityEditor'

type Acting = {
  character_id: string
  reference_asset_id: string | null
  goal: string
  knows: string
  public_face: string
  private_tension: string
  visible_action: string
  evidence: string
}
type Shot = {
  id: string
  title: string
  after_byte: number
  moment: string
  evidence: string
  framing: string
  environment: string
  interpretation: string
  avoid: string
  actors: Acting[]
  image_asset_id: string | null
  status: 'draft' | 'approved'
  continuity: Continuity
  continuity_check: Check
}
type Plan = { style: string; budget: number; shots: Shot[]; scenes: Scene[] }
type State = { revision: number; source_sha256: string; plan: Plan; model_configured: boolean }
// Keep drafts when switching workspace tabs; server refreshes must never replace local edits.
const drafts = new Map<
  string,
  { base: State; plan: Plan; dirty: boolean; checks: Record<string, CheckDraft> }
>()
const actorLabels: [keyof Omit<Acting, 'character_id' | 'reference_asset_id'>, string][] = [
  ['goal', '想得到什么'],
  ['knows', '此刻知道什么'],
  ['public_face', '向对方表现的姿态'],
  ['private_tension', '没有说出口的顾虑'],
  ['visible_action', '目光、神情与手势'],
  ['evidence', '原文依据（推断留在艺术解释）'],
]
export function ProductionPanel({ projectId }: { projectId: string }) {
  const prefix = `/api/projects/${projectId}`,
    cache = useQueryClient()
  const state = useQuery({
    queryKey: ['production', projectId],
    queryFn: () => api<State>(prefix + '/production'),
  })
  const reader = useQuery({
    queryKey: ['reader', projectId],
    queryFn: () => api<ReaderState>(prefix + '/reader'),
  })
  const tasks = useQuery({
    queryKey: ['production-tasks', projectId],
    queryFn: () => api<ImageTasks>(prefix + '/production/tasks'),
  })
  const review = useQuery({
    queryKey: ['review', projectId],
    queryFn: () => api<ReviewState>(prefix + '/review'),
  })
  if (state.error || reader.error || review.error)
    return (
      <p className="error" role="alert">
        {(state.error || reader.error || review.error)?.message}
      </p>
    )
  if (!state.data || !reader.data || !review.data) return <p>正在读取制作方案…</p>
  return (
    <Editor
      key={projectId}
      initial={state.data}
      reader={reader.data}
      tasks={tasks.data}
      taskError={tasks.error?.message}
      retryTasks={() => {
        void tasks.refetch()
      }}
      review={review.data}
      prefix={prefix}
      refresh={async () => {
        await Promise.all(
          ['production', 'production-tasks', 'reader', 'reader-content', 'delivery'].map((k) =>
            cache.invalidateQueries({ queryKey: [k, projectId] }),
          ),
        )
      }}
    />
  )
}
function Editor({
  initial,
  reader,
  tasks,
  taskError,
  retryTasks,
  review,
  prefix,
  refresh,
}: {
  initial: State
  reader: ReaderState
  tasks?: ImageTasks
  taskError?: string
  retryTasks: () => void
  review: ReviewState
  prefix: string
  refresh: () => Promise<void>
}) {
  const cached = drafts.get(prefix)
  const [base, setBase] = useState<State>(cached?.base || initial),
    [plan, setPlan] = useState<Plan>(cached?.plan || initial.plan),
    [dirty, setDirty] = useState(cached?.dirty || false),
    [checkDrafts, setCheckDrafts] = useState<Record<string, CheckDraft>>(cached?.checks || {}),
    [message, setMessage] = useState(''),
    [importError, setImportError] = useState(''),
    [importPending, setImportPending] = useState(false),
    [uploadPending, setUploadPending] = useState(false)
  const importing = useRef(false)
  const uploading = useRef(false)
  const mutationInFlight = useRef(false)

  const hasCheckDrafts = Object.values(checkDrafts).some((d) => d.notes || d.checks.length)
  const unsaved = dirty || hasCheckDrafts
  const remoteChanged = initial.revision > base.revision
  const change = (next: Plan) => {
    setPlan(next)
    setDirty(true)
    setMessage('')
  }
  const update = (id: string, patch: Partial<Shot>) =>
    change({
      ...plan,
      shots: plan.shots.map((s) => (s.id === id ? { ...s, ...patch, status: 'draft' } : s)),
    })
  const operation = useMutation({
    mutationFn: async (
      request: string | { action: string; notes: string; decision: CheckDecision },
    ) => {
      const action = typeof request === 'string' ? request : request.action
      if (importing.current || uploading.current) throw Error('正在核对导入或上传图片，请稍候。')
      if (dirty && action !== 'save') throw Error('请先保存方案草稿，再进行检查或应用。')
      const headers = { 'Content-Type': 'application/json' }
      if (action === 'save')
        return api<State>(prefix + '/production', {
          method: 'PUT',
          headers,
          body: JSON.stringify({
            revision: base.revision,
            source_sha256: base.source_sha256,
            plan,
          }),
        })
      return api<State | { applied: number }>(prefix + '/production/' + action, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          revision: base.revision,
          ...(action === 'apply' ? { reader_revision: reader.revision } : {}),
          ...(typeof request !== 'string'
            ? { notes: request.notes, decision: request.decision, reviewer: 'creator' }
            : {}),
        }),
      })
    },
    onSettled: () => {
      mutationInFlight.current = false
    },
    onSuccess: async (data, action) => {
      if ('plan' in data) {
        setBase(data)
        setPlan(data.plan)
      }
      if (typeof action !== 'string') {
        const id = action.action.split('/')[0]
        setCheckDrafts((current) =>
          Object.fromEntries(Object.entries(current).filter(([key]) => key !== id)),
        )
      }
      setDirty(false)
      setMessage(action === 'apply' ? '已应用到画卷阅读。请继续核对图片并预览。' : '方案已保存。')
      await refresh()
    },
  })
  function runOperation(
    request: string | { action: string; notes: string; decision: CheckDecision },
  ) {
    if (mutationInFlight.current || importing.current || uploading.current) return
    mutationInFlight.current = true
    operation.mutate(request)
  }
  const busy = operation.isPending || importPending || uploadPending
  useEffect(() => {
    if (!unsaved && !busy && initial.revision >= base.revision) {
      setBase(initial)
      setPlan(initial.plan)
    }
  }, [initial, base.revision, unsaved, busy])
  useEffect(() => {
    if (unsaved) drafts.set(prefix, { base, plan, dirty, checks: checkDrafts })
    else drafts.delete(prefix)
  }, [prefix, base, plan, dirty, checkDrafts, unsaved])
  useEffect(() => {
    if (!unsaved) return
    const protect = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', protect)
    return () => window.removeEventListener('beforeunload', protect)
  }, [unsaved])
  const chars = review.characters.filter((c) => !['merged', 'rejected'].includes(c.status))
  async function importPlan(file?: File) {
    if (
      !file ||
      unsaved ||
      operation.isPending ||
      mutationInFlight.current ||
      importing.current ||
      uploading.current
    )
      return
    importing.current = true
    setImportPending(true)
    setImportError('')
    setMessage('')
    try {
      const data = JSON.parse(await file.text())
      if (!data || typeof data !== 'object' || Array.isArray(data))
        throw Error('请选择导出任务对应的 JSON 方案文件。')
      if (typeof data.project_id !== 'string' || !Number.isInteger(data.base_plan_revision))
        throw Error('旧版方案缺少项目与基础版本。请重新导出 AI 任务，原文件可保留作手工参考。')
      if (data.source_sha256 !== initial.source_sha256)
        throw Error('方案原文不匹配，请使用当前项目导出的任务。')
      if (!data.plan || !Array.isArray(data.plan.shots))
        throw Error('方案文件缺少 plan 或镜头列表，请按任务中的 schema 返回 JSON。')
      const validated = await api<Plan>(prefix + '/production/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // Do not replace the task's binding with the latest project or revision.
        body: JSON.stringify(data),
      })
      setBase({
        ...initial,
        revision: data.base_plan_revision,
        source_sha256: data.source_sha256,
      })
      change(validated)
      setMessage('已导入待审草稿，尚未保存。请核对内容后保存；保存时会再次检查版本。')
    } catch (e) {
      setImportError((e as Error).message)
    } finally {
      importing.current = false
      setImportPending(false)
    }
  }
  function addShot() {
    const p = reader.paragraphs.find((p) => !plan.shots.some((s) => s.after_byte === p.byte_end))
    if (!p) return
    change({
      ...plan,
      shots: [
        ...plan.shots,
        {
          id: crypto.randomUUID(),
          title: '新镜头',
          after_byte: p.byte_end,
          moment: '',
          evidence: '',
          framing: '',
          environment: '',
          interpretation: '',
          avoid: '',
          actors: [],
          image_asset_id: null,
          status: 'draft',
          continuity: emptyContinuity(),
          continuity_check: null,
        },
      ],
    })
  }
  return (
    <fieldset
      className="production-panel"
      disabled={busy}
      style={{ border: 0, margin: 0, minWidth: 0 }}
    >
      <div className="panel-head">
        <div>
          <h2>章节制作方案</h2>
          <p>先读懂人物处境，再安排镜头与素材。每个镜头放在对应原文段落之后。</p>
        </div>
        <BundleBackup prefix={prefix} disabled={unsaved || busy} />
      </div>
      <div className="production-toolbar">
        <button onClick={() => runOperation('save')} disabled={!dirty || busy}>
          保存方案
        </button>
        <button
          disabled={unsaved || busy || !initial.model_configured}
          onClick={() => {
            if (
              window.confirm(
                '将本章原文和人物资料发送到你配置的文本模型，生成候选方案并替换当前方案（可能产生服务费用）。继续吗？',
              )
            )
              runOperation('generate')
          }}
        >
          AI 起草候选
        </button>
        <a
          href={prefix + '/production/tasks?kind=plan'}
          aria-disabled={unsaved || busy}
          onClick={(e) => {
            if (unsaved || busy) e.preventDefault()
          }}
        >
          导出 AI 任务
        </a>
        <label className="file-button">
          导入 AI 方案
          <input
            aria-label="导入制作方案"
            disabled={unsaved || busy}
            type="file"
            accept=".json"
            onChange={(e) => {
              const file = e.target.files?.[0]
              e.target.value = ''
              void importPlan(file)
            }}
          />
        </label>
        <a
          href={prefix + '/production/tasks'}
          aria-disabled={unsaved || busy}
          onClick={(e) => {
            if (unsaved || busy) e.preventDefault()
          }}
        >
          下载生图提示词
        </a>
        <button disabled={unsaved || busy} onClick={() => runOperation('apply')}>
          应用已确认镜头
        </button>
        <a href={prefix.replace('/api/projects/', '/read/')} target="_blank" rel="noreferrer">
          阅读预览 ↗
        </a>
      </div>
      <p className="notice">
        外部 AI
        任务绑定当前项目与已保存的方案版本。任务导出后若修改方案，请重新导出，不要修改旧结果的版本字段。
      </p>
      {taskError && (
        <p className="error" role="alert">
          素材任务暂时无法核对：{taskError} <button onClick={retryTasks}>重试任务核对</button>
          。方案与本地草稿仍然保留。
        </p>
      )}
      {importPending && <p role="status">正在核对任务归属、版本与方案内容…</p>}
      {!initial.model_configured && (
        <p className="notice">
          可直接手工填写，也可导出任务交给你使用的 AI，再导入方案。生图提示词可用于 Codex
          或其他图片工具。每个镜头可下载带实际参考图的任务包，完成后直接在该镜头上传候选并绑定。
        </p>
      )}
      {dirty && <p role="status">有未保存修改。保存后才能确认镜头、下载最新提示词或应用编排。</p>}
      {hasCheckDrafts && (
        <p role="status">检查说明尚未提交，请选择通过、不通过或撤销；切换页签会保留草稿。</p>
      )}
      {remoteChanged && (
        <p role="alert">制作方案或参考已在其他位置更新。本地草稿已保留，请核对后再操作。</p>
      )}
      {unsaved && (
        <button
          onClick={() => {
            if (!window.confirm('放弃本页未保存的方案和检查说明，并读取最新已保存内容？')) return
            setPlan(initial.plan)
            setBase(initial)
            setDirty(false)
            setCheckDrafts({})
          }}
        >
          放弃本地草稿并刷新
        </button>
      )}
      {(operation.error || importError) && (
        <p className="error" role="alert">
          {operation.error?.message || importError}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <div className="production-fields">
        <label>
          全章视觉风格
          <textarea
            value={plan.style}
            onChange={(e) =>
              change({
                ...plan,
                style: e.target.value,
                shots: plan.shots.map((s) => ({ ...s, status: 'draft' })),
              })
            }
          />
        </label>
        <label>
          插图预算
          <input
            type="number"
            min={0}
            max={64}
            value={plan.budget}
            onChange={(e) => change({ ...plan, budget: Number(e.target.value) })}
          />
        </label>
      </div>
      <SceneLibrary
        scenes={plan.scenes}
        shots={plan.shots}
        assets={reader.assets}
        change={(scenes) =>
          change({
            ...plan,
            scenes,
            shots: plan.shots.map((s) => ({
              ...s,
              continuity_check: null,
              continuity: {
                ...s.continuity,
                states: (scenes.find((sc) => sc.id === s.continuity.scene_id)?.objects || []).map(
                  (o) => {
                    const old = s.continuity.states.find((st) => st.object_id === o.id)
                    return old
                      ? { ...old, position: o.kind === 'fixed' ? o.home : old.position }
                      : {
                          object_id: o.id,
                          visibility: 'visible' as const,
                          position: o.home,
                          reason: '',
                        }
                  },
                ),
              },
            })),
          })
        }
      />
      {plan.shots.length === 0 && (
        <p className="notice">
          从一个关键瞬间开始：选择原文段落，写清双方各自的目的，再选择能看见其反应的镜头。
        </p>
      )}
      {plan.shots.map((s, index) => (
        <details
          className="production-shot"
          key={s.id}
          id={`shot-${s.id}`}
          open={plan.shots.length < 3 ? true : undefined}
        >
          <summary>
            {index + 1}. {s.title} · {s.status === 'approved' ? '方案已确认' : '待审方案'}
          </summary>
          <div className="production-fields">
            <label>
              镜头名称
              <input value={s.title} onChange={(e) => update(s.id, { title: e.target.value })} />
            </label>
            <label>
              插图跟随的原文段落
              <select
                value={s.after_byte}
                onChange={(e) => update(s.id, { after_byte: Number(e.target.value), evidence: '' })}
              >
                {reader.paragraphs.map((p) => (
                  <option key={p.byte_end} value={p.byte_end}>
                    {p.preview}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="shot-exchange-eyebrow">原文锚点 · 段落结束字节 {s.after_byte}</p>
          <blockquote>
            {reader.paragraphs.find((p) => p.byte_end === s.after_byte)?.text}
          </blockquote>
          <ShotExchange
            prefix={prefix}
            shot={s}
            revision={base.revision}
            reader={reader}
            task={
              !taskError && tasks?.plan_revision === base.revision
                ? tasks.tasks.find((task) => task.id === s.id)
                : undefined
            }
            locked={unsaved}
            stale={remoteChanged}
            pending={busy}
            bind={(id) => update(s.id, { image_asset_id: id, continuity_check: null })}
            setBusy={(value) => {
              if (value && (mutationInFlight.current || importing.current || uploading.current))
                return false
              uploading.current = value
              setUploadPending(value)
              return true
            }}
            refresh={refresh}
          />
          <div className="production-fields">
            {(
              [
                ['moment', '具体发生在哪一刻'],
                ['evidence', '原文依据（逐字摘录本段）'],
                ['framing', '镜头与视角'],
                ['environment', '环境、光线与群像'],
                ['interpretation', '艺术解释与尚不确定的理解'],
                ['avoid', '不能提前表现的情节／应避免的误读'],
              ] as const
            ).map(([k, label]) => (
              <label key={k}>
                {label}
                <textarea value={s[k]} onChange={(e) => update(s.id, { [k]: e.target.value })} />
              </label>
            ))}
          </div>
          {s.actors.map((a, ai) => (
            <fieldset key={ai}>
              <legend>人物 {ai + 1}</legend>
              <label>
                身份
                <select
                  value={a.character_id}
                  onChange={(e) =>
                    update(s.id, {
                      actors: s.actors.map((v, i) =>
                        i === ai
                          ? { ...v, character_id: e.target.value, reference_asset_id: null }
                          : v,
                      ),
                    })
                  }
                >
                  {chars.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                本镜头的人物生图参考
                <select
                  value={a.reference_asset_id || ''}
                  onChange={(e) =>
                    update(s.id, {
                      actors: s.actors.map((v, i) =>
                        i === ai ? { ...v, reference_asset_id: e.target.value || null } : v,
                      ),
                    })
                  }
                >
                  <option value="">跟随当前展示立绘</option>
                  {a.reference_asset_id &&
                    !review.assets.some(
                      (asset) =>
                        asset.id === a.reference_asset_id &&
                        asset.character_id === a.character_id &&
                        asset.status === 'accepted',
                    ) && <option value={a.reference_asset_id}>原选参考已失效，请重新选择</option>}
                  {review.assets
                    .filter(
                      (asset) =>
                        asset.character_id === a.character_id && asset.status === 'accepted',
                    )
                    .map((asset) => (
                      <option key={asset.id} value={asset.id}>
                        {asset.label || asset.license.slice(0, 35) || '人物图片'} ·{' '}
                        {asset.kind === 'reference' ? '仅供身份参考' : '立绘'} ·{' '}
                        {asset.sha256.slice(0, 8)}
                      </option>
                    ))}
                </select>
              </label>
              <p>明确选图只影响本镜头生图与检查，不会切换阅读器中的展示立绘。</p>
              <div className="production-fields">
                {actorLabels.map(([k, label]) => (
                  <label key={k}>
                    {label}
                    <textarea
                      value={a[k]}
                      onChange={(e) =>
                        update(s.id, {
                          actors: s.actors.map((v, i) =>
                            i === ai ? { ...v, [k]: e.target.value } : v,
                          ),
                        })
                      }
                    />
                  </label>
                ))}
              </div>
              <button onClick={() => update(s.id, { actors: s.actors.filter((_, i) => i !== ai) })}>
                移除此人物
              </button>
            </fieldset>
          ))}
          <div className="production-toolbar">
            <button
              disabled={!chars.length || s.actors.length >= 12}
              onClick={() =>
                update(s.id, {
                  actors: [
                    ...s.actors,
                    {
                      character_id:
                        chars.find((c) => !s.actors.some((a) => a.character_id === c.id))?.id ||
                        chars[0].id,
                      reference_asset_id: null,
                      goal: '',
                      knows: '',
                      public_face: '',
                      private_tension: '',
                      visible_action: '',
                      evidence: '',
                    },
                  ],
                })
              }
            >
              添加在场人物
            </button>
            <label>
              回填图片
              <select
                disabled={s.continuity.method === 'reuse' && !!s.continuity.reuse_asset_id}
                value={s.image_asset_id || ''}
                onChange={(e) => update(s.id, { image_asset_id: e.target.value || null })}
              >
                <option value="">稍后选择</option>
                {reader.assets
                  .filter((a) => a.kind === 'scene' && a.status !== 'rejected')
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.label || a.license.slice(0, 45)} ·{' '}
                      {a.status === 'accepted' ? '图片已接受' : '图片待审'}
                    </option>
                  ))}
              </select>
            </label>
            <button
              disabled={dirty || busy || s.status === 'approved'}
              onClick={() => runOperation(s.id + '/approve')}
            >
              确认此镜头方案
            </button>
            <button
              onClick={() => change({ ...plan, shots: plan.shots.filter((v) => v.id !== s.id) })}
            >
              删除镜头
            </button>
          </div>
          <ShotContinuity
            shot={s}
            shots={plan.shots}
            scenes={plan.scenes}
            assets={reader.assets}
            update={(continuity) =>
              update(s.id, {
                continuity,
                continuity_check: null,
                ...(continuity.method === 'reuse' && continuity.reuse_asset_id
                  ? { image_asset_id: continuity.reuse_asset_id }
                  : {}),
              })
            }
            locked={dirty || busy}
            draft={checkDrafts[s.id] || { notes: '', checks: [] }}
            changeDraft={(draft) => setCheckDrafts((current) => ({ ...current, [s.id]: draft }))}
            references={s.actors.map((actor) => {
              const character = review.characters.find((c) => c.id === actor.character_id)
              const asset = review.assets.find(
                (a) => a.id === (actor.reference_asset_id || character?.active_figure_id),
              )
              return {
                name: character?.display_name || '未知人物',
                selection: actor.reference_asset_id ? '本镜头明确选用' : '跟随展示立绘',
                valid: asset?.status === 'accepted' && character?.status === 'confirmed',
                url: asset?.url,
                sha256: asset?.sha256,
              }
            })}
            check={(notes, decision) =>
              runOperation({ action: s.id + '/continuity-check', notes, decision })
            }
          />
        </details>
      ))}
      <button disabled={plan.shots.length >= plan.budget} onClick={addShot}>
        添加镜头 · {plan.shots.length}/{plan.budget}
      </button>
    </fieldset>
  )
}
