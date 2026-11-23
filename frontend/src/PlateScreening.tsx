import { useEffect, useId, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import { useUnsavedWarning } from './studio/leave'
import './plate-screening.css'

type Choice = 'unassessed' | 'still' | 'motion' | 'deferred'
const names: Record<Choice, string> = {
  unassessed: '未审',
  still: '保留静图',
  motion: '可支持的动效候选',
  deferred: '值得动，但暂不支持',
}
const labels = {
  evidence: '可见原文依据（逐字短引）',
  observation: '实际画面里看到了什么？',
  action: '哪些部分动或不动？',
  protect: '必须保护的区域或主体',
  reason: '这样选择对这段阅读有什么作用？',
  verification: '私有核验备注（可不填）',
}
type Fields = Record<keyof typeof labels, string> & {
  decision: Choice
  proposed_effect?: string | null
}
type Row = Fields & {
  plate_id: string
  image_asset_id: string
  image_sha256: string
  width: number
  height: number
  after_byte: number
  paragraph_start: number
}
type Sheet = { schema_version: number; work_id: string; source_sha256: string; plates: Row[] }
type Lens = 'timing' | 'motion'
type TimingStatus = 'unchecked' | 'clear' | 'revise'
const timingNames: Record<TimingStatus, string> = {
  unchecked: '未审时机',
  clear: '此处可出场',
  revise: '需要调整',
}
type Timing = {
  status: TimingStatus
  evidence: string
  reason: string
  binding: string
  stale: boolean
}
type Display = {
  title: string
  description: string
  alt: string
  paragraph: string
  display_after_byte: number
  display_paragraph: string
  carrier: string | null
}
type Data = {
  revision: number
  reader_revision: number
  worksheet: Sheet
  changed: string[]
  notices: string[]
  display: Record<string, Display>
  timing: {
    revision: number
    ok: boolean
    counts: Record<TimingStatus | 'total', number>
    plates: Record<string, Timing>
  }
  report: {
    ok: boolean
    counts: Record<string, number>
    plates: { plate_id: string; errors: string[] }[]
  }
}
const endpoint = (id: string) => '/api/projects/' + id + '/plate-screening'
export function usePlateScreening(id: string, enabled = true) {
  return useQuery({
    queryKey: ['plate-screening', id],
    queryFn: () => api<Data>(endpoint(id)),
    enabled,
  })
}

type Draft = {
  row: Row
  revision: number
  reader_revision: number
  display: Display
  timing: Timing
  timing_revision: number
}
type Guard = (dirty: boolean, writing: boolean) => void
const fields = Object.keys(labels) as (keyof typeof labels)[]
function fault(s: string) {
  if (s.includes('exact UTF-8 quotation')) return '依据需逐字出自此图之前已经读到的原文。'
  if (s.includes('conflicts with an eligible'))
    return '此判断要求静止，但编排仍保留了可播放动效。请到动效导演停用，或重新审图。'
  if (s.includes('not screened')) return '尚未逐幅判断。'
  return s
}
function changeNotice(s: string) {
  return s
    .replace(
      /: changed source\/art\/anchor\/identity; reset to unassessed$/,
      '：原文、底图或位置已变，已重置为未审。',
    )
    .replace(/: new plate; unassessed$/, '：新增插图，尚未审图。')
    .replace(/: removed from edition$/, '：本版已移除。')
}
function download(sheet: Sheet) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(sheet, null, 2) + '\n'], { type: 'application/json' }),
  )
  const a = document.createElement('a')
  a.href = url
  a.download = 'taleprism-private-plate-screening.json'
  a.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function PlateScreening({
  projectId,
  readerRevision,
  locked = false,
  onGuard,
}: {
  projectId: string
  readerRevision?: number
  locked?: boolean
  onGuard?: Guard
}) {
  const q = usePlateScreening(projectId),
    data = q.data,
    cache = useQueryClient()
  const [expanded, open] = useState(false)
  const [lens, setLens] = useState<Lens>('timing')
  const panelId = useId()
  const [imageAttempt, retryImage] = useState(0)
  const [selected, select] = useState('')
  const [draft, edit] = useState<Draft | null>(null),
    dirty = !!draft
  const [seen, see] = useState(''),
    [broken, failImage] = useState(false)
  const [working, start] = useState(false),
    lock = useRef(false)
  const [error, setError] = useState(''),
    [message, tell] = useState('')
  const row =
    draft?.row ||
    data?.worksheet.plates.find((r) => r.plate_id === selected) ||
    data?.worksheet.plates.find((r) => data.timing.plates[r.plate_id]?.status !== 'clear') ||
    data?.worksheet.plates[0]
  const detail = draft?.display || (row && data?.display[row.plate_id])
  const timing = draft?.timing || (row && data?.timing.plates[row.plate_id])
  const imageKey = row
    ? [
        row.plate_id,
        row.image_asset_id,
        row.image_sha256,
        row.after_byte,
        data?.worksheet.source_sha256,
        imageAttempt,
      ].join(':')
    : ''
  const imageUrl = row
    ? `/api/projects/${encodeURIComponent(projectId)}/reader/assets/${encodeURIComponent(row.image_asset_id)}?sha256=${row.image_sha256}&attempt=${imageAttempt}`
    : ''
  useUnsavedWarning(dirty || working)
  useEffect(() => {
    onGuard?.(dirty, working)
    return () => onGuard?.(false, false)
  }, [dirty, working, onGuard])
  useEffect(() => {
    if (readerRevision !== undefined)
      void cache.invalidateQueries({ queryKey: ['plate-screening', projectId] })
  }, [readerRevision, cache, projectId])
  function reset() {
    edit(null)
    setError('')
    tell('')
  }
  function mayDiscard() {
    return !dirty || window.confirm('放弃本幅尚未保存的审图输入？')
  }
  function choose(id: string) {
    if (!mayDiscard()) return
    reset()
    select(id)
    see('')
    failImage(false)
  }
  function baseline(): Draft | null {
    if (!data || !row || !detail || !timing) return null
    return (
      draft || {
        revision: data.revision,
        reader_revision: data.reader_revision,
        display: detail,
        row,
        timing,
        timing_revision: data.timing.revision,
      }
    )
  }
  function begin() {
    setError('')
    tell('')
    const base = baseline()
    if (base) select(base.row.plate_id)
    return base
  }
  function updateTiming(key: 'status' | 'evidence' | 'reason', value: string) {
    const base = begin()
    if (base) edit({ ...base, timing: { ...base.timing, [key]: value } })
  }
  function update(key: keyof Fields, value: string) {
    const base = begin()
    if (!base) return
    edit({
      ...base,
      row: {
        ...base.row,
        ...(key === 'decision' && value !== 'motion' ? { proposed_effect: null } : {}),
        [key]: value,
      },
    })
  }
  async function write(path: string, body: object, success: string) {
    if (lock.current) return
    lock.current = true
    start(true)
    setError('')
    tell('')
    try {
      const d = await api<Data>(endpoint(projectId) + path, {
        method: path === '/import' ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      cache.setQueryData(['plate-screening', projectId], d)
      void cache.invalidateQueries({ queryKey: ['delivery', projectId] })
      reset()
      tell(success)
    } catch (e) {
      setError(e instanceof Error ? fault(e.message) : '未保存。')
      void q.refetch()
    } finally {
      lock.current = false
      start(false)
    }
  }
  async function importFile(file?: File) {
    if (!file || !data || dirty || working || locked) return
    try {
      if (file.size > 2_000_000) throw Error('审图单不得超过 2 MB。')
      const text = await file.text(),
        foreign = JSON.parse(text)?.work_id !== data.worksheet.work_id
      if (
        !window.confirm(
          foreign
            ? '这份审图单来自另一工程。确认是同一作品的还原副本？只在全部原文、实图、编号和位置严格相同时移入，不覆盖不同判断。'
            : '合并私有审图单？只填入完全匹配的判断，不覆盖本机不同的判断。',
        )
      )
        return
      await write(
        '/import',
        {
          revision: data.revision,
          reader_revision: data.reader_revision,
          worksheet: text,
          exact_copy: foreign,
        },
        '已核对全部绑定并合并私有审图单。',
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : '无法读取审图单。')
    }
  }
  const outdated =
    !!draft &&
    (draft.reader_revision !== data?.reader_revision ||
      (lens === 'motion'
        ? draft.revision !== data?.revision
        : draft.timing_revision !== data?.timing.revision ||
          draft.timing.binding !== data?.timing.plates[draft.row.plate_id]?.binding))
  const report = data?.report,
    n = report?.counts
  const issue = report?.plates
    .find((r) => r.plate_id === row?.plate_id)
    ?.errors.filter((s) => !s.includes('not screened'))
  const disabled = locked || working || q.isError || outdated
  const counts = data?.timing.counts
  const next = data?.worksheet.plates.filter(
    (r) =>
      r.plate_id !== row?.plate_id &&
      (lens === 'timing'
        ? data.timing.plates[r.plate_id]?.status !== 'clear'
        : r.decision === 'unassessed'),
  )
  function switchLens(nextLens: Lens) {
    if (lens === nextLens || working || !mayDiscard()) return
    reset()
    setLens(nextLens)
  }
  // Re-read this exact placement after a collapse or failed image load. Never use a
  // previously viewed thumbnail as permission to write a new author decision.
  function toggle() {
    if (working || (expanded && !mayDiscard())) return
    if (expanded) {
      reset()
      see('')
      failImage(false)
    }
    open(!expanded)
  }
  const canJudge = !disabled && !!row && !!seen && seen === imageKey
  const saveTiming = (status: TimingStatus) => {
    const base = baseline()
    if (
      !base ||
      !canJudge ||
      (status !== 'unchecked' &&
        (!dirty || !base.timing.evidence.trim() || !base.timing.reason.trim()))
    )
      return
    void write(
      '/timing',
      {
        plate_id: base.row.plate_id,
        revision: base.timing_revision,
        reader_revision: base.reader_revision,
        binding: base.timing.binding,
        status,
        evidence: status === 'unchecked' ? '' : base.timing.evidence,
        reason: status === 'unchecked' ? '' : base.timing.reason,
      },
      status === 'unchecked'
        ? '已撤回时机判断。'
        : status === 'clear'
          ? '已确认：本幅可以在此处出场。'
          : '已记为需要调整。原图、位置和读者文案均未改动。',
    )
  }
  return (
    <section className="plate-screening" aria-label="逐幅审图">
      <h3>
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={panelId}
          disabled={working}
          onClick={toggle}
        >
          逐幅审图 <span aria-hidden="true">{expanded ? '▴' : '▾'}</span>
        </button>
      </h3>
      {counts && counts.total > 0 && (
        <p className="screening-count" role="status">
          时机：未审 {counts.unchecked} · 需调整 {counts.revise} · 已确认 {counts.clear}
        </p>
      )}
      {data && (
        <p className="screening-helper">
          {!counts?.total
            ? '当前没有已放进章节的插图，无需逐幅审图。'
            : data.timing.ok && report?.ok
              ? '时机和动静均已审完。仍需实际试读后，才能正式签核。'
              : '可以先试读、导出草稿；正式签核前，须确认每幅图的出场时机与动静。'}
        </p>
      )}
      {q.isPending && <p role="status">正在读取已放置的插图…</p>}
      {q.error && (
        <p role="alert">
          无法核对当前插图：{q.error.message}{' '}
          <button type="button" onClick={() => void q.refetch()}>
            重新读取
          </button>
        </p>
      )}
      <div id={panelId} hidden={!expanded}>
        {expanded && data && (
          <>
            {!!data.notices.length && (
              <details>
                <summary>图文清单发生变化（{data.notices.length} 项）</summary>
                <ul>
                  {data.notices.map((v) => (
                    <li key={v}>{changeNotice(v)}</li>
                  ))}
                </ul>
              </details>
            )}
            {row && detail && timing && (
              <div className="screening-entry">
                <div className="screening-picker">
                  <label>
                    选择要审的章节插图
                    <select
                      value={row.plate_id}
                      disabled={working}
                      onChange={(e) => choose(e.target.value)}
                    >
                      {data.worksheet.plates.map((r, i) => (
                        <option key={r.plate_id} value={r.plate_id}>
                          {i + 1}. {data.display[r.plate_id].title} ·{' '}
                          {lens === 'timing'
                            ? timingNames[data.timing.plates[r.plate_id].status]
                            : names[r.decision]}
                        </option>
                      ))}
                    </select>
                  </label>
                  {!!next?.length && (
                    <button
                      type="button"
                      disabled={working}
                      onClick={() => {
                        const i = data.worksheet.plates.findIndex(
                          (r) => r.plate_id === row.plate_id,
                        )
                        const one =
                          data.worksheet.plates.slice(i + 1).find((r) => next.includes(r)) ||
                          next[0]
                        choose(one.plate_id)
                      }}
                    >
                      下一幅待审 →
                    </button>
                  )}
                </div>
                <div className="screening-lenses" role="group" aria-label="审图内容">
                  <button
                    type="button"
                    disabled={working}
                    aria-pressed={lens === 'timing'}
                    onClick={() => switchLens('timing')}
                  >
                    出场时机
                  </button>
                  <button
                    type="button"
                    disabled={working}
                    aria-pressed={lens === 'motion'}
                    onClick={() => switchLens('motion')}
                  >
                    动静选择
                  </button>
                </div>
                <div className="screening-spread">
                  <div className="screening-prose">
                    <p className="screening-kicker">
                      {lens === 'timing' ? '出图前，读者刚读到' : '插图所依据的原文段'}
                    </p>
                    <blockquote>
                      {lens === 'timing' ? detail.display_paragraph : detail.paragraph}
                    </blockquote>
                    {lens === 'timing' && detail.display_after_byte !== row.after_byte && (
                      <details>
                        <summary>查看这幅图原先依据的段落</summary>
                        <p className="original-paragraph">{detail.paragraph}</p>
                      </details>
                    )}
                  </div>
                  <figure>
                    <img
                      key={imageKey}
                      src={imageUrl}
                      alt={'已放置的插图：' + detail.title}
                      onLoad={(e) => {
                        const ok =
                          e.currentTarget.naturalWidth === row.width &&
                          e.currentTarget.naturalHeight === row.height
                        see(ok ? imageKey : '')
                        failImage(!ok)
                      }}
                      onError={() => {
                        see('')
                        failImage(true)
                      }}
                    />
                    <figcaption>
                      {seen === imageKey && !broken && !outdated && !q.isError && (
                        <a
                          className="screening-original"
                          href={imageUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          查看原图（新标签页）<span aria-hidden="true">↗</span>
                          <small>
                            {row.width} × {row.height}
                          </small>
                        </a>
                      )}
                      <span className="screening-kicker">读者看到的标题</span>
                      <strong>{detail.title}</strong>
                      <span className="screening-kicker">图片说明（替代文本）</span>
                      <span>{detail.alt}</span>
                      {detail.description && detail.description !== detail.alt && (
                        <>
                          <span className="screening-kicker">编排中另有说明</span>
                          <span>{detail.description}</span>
                        </>
                      )}
                    </figcaption>
                  </figure>
                </div>
                {broken && (
                  <p role="alert">
                    实图无法核对，不能保存判断。{' '}
                    <button
                      type="button"
                      onClick={() => {
                        failImage(false)
                        see('')
                        retryImage((i) => i + 1)
                      }}
                    >
                      重新载入实图
                    </button>
                  </p>
                )}
                {outdated && (
                  <p role="alert">
                    编排或审图记录已更新。请复制需要保留的输入，再放弃草稿并查看最新图文。
                  </p>
                )}
                {lens === 'timing' ? (
                  <form
                    aria-label="本幅出场时机"
                    className="timing-form"
                    onSubmit={(e) => {
                      e.preventDefault()
                      if (timing.status !== 'unchecked') saveTiming(timing.status)
                    }}
                  >
                    <fieldset disabled={!canJudge}>
                      <legend>读到这里，画面或文字有没有说破后文？</legend>
                      <p className="screening-helper">
                        只看这幅图、标题和说明，不以你已经知道的结局作依据。
                      </p>
                      <div className="timing-options">
                        {(['clear', 'revise'] as const).map((s) => (
                          <label key={s}>
                            <input
                              type="radio"
                              name={panelId + '-timing'}
                              checked={timing.status === s}
                              onChange={() => updateTiming('status', s)}
                            />
                            {timingNames[s]}
                          </label>
                        ))}
                      </div>
                      {timing.stale && (
                        <p role="status">原文、图片、出场位置或文案已变，请按当前版本重新判断。</p>
                      )}
                      {timing.status !== 'unchecked' && (
                        <>
                          <label>
                            原文短引
                            <textarea
                              required
                              rows={2}
                              maxLength={300}
                              value={timing.evidence}
                              placeholder="引用读者此刻已经读过的一句原文"
                              onChange={(e) => updateTiming('evidence', e.target.value)}
                            />
                          </label>
                          {detail.display_paragraph.length <= 300 && (
                            <button
                              className="screening-use-quote"
                              type="button"
                              onClick={() => updateTiming('evidence', detail.display_paragraph)}
                            >
                              引用上方整段
                            </button>
                          )}
                          <label>
                            判断理由
                            <textarea
                              required
                              rows={2}
                              maxLength={1000}
                              value={timing.reason}
                              placeholder={
                                timing.status === 'clear'
                                  ? '一句话：图中和说明里出现的内容，读者为什么已经可以知道？'
                                  : '一句话：什么出现得太早？应推迟画面、修改标题，还是换图？'
                              }
                              onChange={(e) => updateTiming('reason', e.target.value)}
                            />
                          </label>
                          <button
                            className="primary"
                            type="submit"
                            disabled={!dirty || !timing.reason.trim() || !timing.evidence.trim()}
                          >
                            保存时机判断
                          </button>
                        </>
                      )}
                    </fieldset>
                    {data.timing.plates[row.plate_id]?.status !== 'unchecked' && !dirty && (
                      <button
                        type="button"
                        className="screening-secondary"
                        disabled={!canJudge}
                        onClick={() => {
                          if (
                            window.confirm('撤回这幅图的时机判断并恢复未审？正式签核前须重新确认。')
                          )
                            saveTiming('unchecked')
                        }}
                      >
                        撤回时机判断
                      </button>
                    )}
                    {data.timing.plates[row.plate_id]?.status === 'revise' && !dirty && (
                      <p className="screening-helper">
                        本幅仍可试读。请在章节插图编排中改图、文案或位置，再回来确认。
                      </p>
                    )}
                    <p className="screening-helper">
                      时机判断只保存在本机，不会写入读本、工程 ZIP 或动静审图单。
                    </p>
                  </form>
                ) : (
                  <>
                    {n && (
                      <p className="screening-helper" role="status">
                        共 {n.total} 幅 · 未审 {n.unassessed} · 保留静图 {n.still} · 动效候选{' '}
                        {n.motion} · 延期 {n.deferred}
                      </p>
                    )}
                    {data.changed.includes(row.plate_id) && (
                      <p role="status">原有动静判断已过期，请对照当前实图与原文重新判断。</p>
                    )}
                    {detail.carrier && (
                      <p>此幅已有可播放的导演设置；这里只记录意见，不代表已经核验播放像素。</p>
                    )}
                    {issue?.map((f) => (
                      <p role="alert" key={f}>
                        {fault(f)}
                      </p>
                    ))}
                    <form
                      onSubmit={(e) => {
                        e.preventDefault()
                        if (
                          !draft ||
                          disabled ||
                          seen !== imageKey ||
                          row.decision === 'unassessed'
                        )
                          return
                        void write(
                          '/plate',
                          {
                            revision: draft.revision,
                            reader_revision: draft.reader_revision,
                            plate_id: row.plate_id,
                            decision: row.decision,
                            proposed_effect:
                              row.decision === 'motion'
                                ? row.proposed_effect || data.display[row.plate_id]?.carrier || null
                                : null,
                            ...Object.fromEntries(fields.map((k) => [k, row[k]])),
                          },
                          '已保存本幅判断。读者版和动效配置均未修改。',
                        )
                      }}
                    >
                      <fieldset disabled={disabled || seen !== imageKey}>
                        <legend>本幅编辑判断</legend>
                        <label>
                          动静选择
                          <select
                            required
                            value={row.decision === 'unassessed' ? '' : row.decision}
                            onChange={(e) => update('decision', e.target.value)}
                          >
                            <option disabled value="">
                              请先看图，再选择
                            </option>
                            <option value="still">保留静图</option>
                            <option value="motion">可支持的动效候选（雨地／岸浪）</option>
                            <option value="deferred">值得动，但暂不支持；保持静图并延期</option>
                          </select>
                        </label>
                        {row.decision === 'motion' && (
                          <label>
                            候选动效类型
                            <select
                              required
                              value={
                                row.proposed_effect || data.display[row.plate_id]?.carrier || ''
                              }
                              onChange={(e) => update('proposed_effect', e.target.value)}
                            >
                              <option value="" disabled>
                                按实图选择支持的类型
                              </option>
                              <option value="rain-wet-ground">雨与湿地</option>
                              <option value="wave-impact-backwash">岸浪拍击与回流</option>
                            </select>
                            <small>其他运动请选「暂不支持」。候选不是已播放或已验证。</small>
                          </label>
                        )}
                        {fields.map((k) => (
                          <label key={k}>
                            {labels[k]}
                            <textarea
                              rows={k === 'verification' ? 1 : 2}
                              maxLength={k === 'evidence' ? 300 : 1000}
                              required={k !== 'verification'}
                              value={row[k]}
                              onChange={(e) => update(k, e.target.value)}
                            />
                          </label>
                        ))}
                        <button type="submit" disabled={!dirty || row.decision === 'unassessed'}>
                          保存本幅判断
                        </button>
                      </fieldset>
                    </form>
                  </>
                )}
                {dirty && (
                  <button
                    type="button"
                    disabled={working}
                    onClick={() => {
                      if (mayDiscard()) {
                        reset()
                        void q.refetch()
                      }
                    }}
                  >
                    放弃未保存的审图输入
                  </button>
                )}
              </div>
            )}
            {lens === 'motion' && (
              <details className="screening-files">
                <summary>动静审图单 · 备份与导入</summary>
                <p>只转移动静判断，不包含出场时机判断。此 JSON、阅读包和工程 ZIP 各自独立。</p>
                <button
                  type="button"
                  disabled={working || dirty || q.isError}
                  onClick={() => download(data.worksheet)}
                >
                  下载私有审图单 JSON
                </button>
                <label>
                  导入私有审图单 JSON
                  <input
                    type="file"
                    accept=".json,application/json"
                    disabled={locked || working || dirty || q.isError}
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      e.target.value = ''
                      void importFile(f)
                    }}
                  />
                </label>
              </details>
            )}
          </>
        )}
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  )
}
