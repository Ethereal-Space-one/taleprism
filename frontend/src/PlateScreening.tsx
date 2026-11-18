import { useEffect, useRef, useState } from 'react'
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
type Data = {
  revision: number
  reader_revision: number
  worksheet: Sheet
  changed: string[]
  notices: string[]
  display: Record<string, { title: string; paragraph: string; carrier: string | null }>
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
  title: string
  paragraph: string
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
  const [selected, select] = useState('')
  const [draft, edit] = useState<Draft | null>(null),
    [changed, setChanged] = useState(false)
  const [seen, see] = useState(''),
    [broken, failImage] = useState(false)
  const [working, start] = useState(false),
    lock = useRef(false)
  const [error, setError] = useState(''),
    [message, tell] = useState('')
  const row =
    draft?.row ||
    data?.worksheet.plates.find((r) => r.plate_id === selected) ||
    data?.worksheet.plates[0]
  const detail = row && (draft || data?.display[row.plate_id])
  const imageKey = row
    ? [
        row.plate_id,
        row.image_asset_id,
        row.image_sha256,
        row.after_byte,
        data?.worksheet.source_sha256,
      ].join(':')
    : ''
  const dirty = !!draft && changed
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
    setChanged(false)
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
  function update(key: keyof Fields, value: string) {
    if (!data || !row || !detail) return
    const base = draft || {
      revision: data.revision,
      reader_revision: data.reader_revision,
      title: detail.title,
      paragraph: detail.paragraph,
      row,
    }
    edit({
      ...base,
      row: {
        ...row,
        ...(key === 'decision' && value !== 'motion' ? { proposed_effect: null } : {}),
        [key]: value,
      },
    })
    setChanged(true)
    setError('')
    tell('')
  }
  async function write(path: string, body: object, success: string) {
    if (lock.current) return
    lock.current = true
    start(true)
    setError('')
    tell('')
    try {
      const d = await api<Data>(endpoint(projectId) + path, {
        method: path === '/plate' ? 'PUT' : 'POST',
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
    !!draft && (draft.revision !== data?.revision || draft.reader_revision !== data.reader_revision)
  const report = data?.report,
    n = report?.counts
  const issue = report?.plates
    .find((r) => r.plate_id === row?.plate_id)
    ?.errors.filter((s) => !s.includes('not screened'))
  const disabled = locked || working || q.isError || outdated
  return (
    <section className="plate-screening" aria-label="逐幅动静审图">
      <h3>
        <button type="button" aria-expanded={expanded} onClick={() => open(!expanded)}>
          逐幅动静审图 <span aria-hidden="true">{expanded ? '▴' : '▾'}</span>
        </button>
      </h3>
      {n && (
        <p className="screening-count" role="status">
          共 {n.total} 幅 · 未审 {n.unassessed} · 保留静图 {n.still} · 动效候选 {n.motion} · 延期{' '}
          {n.deferred}
          {!report?.ok && n.unassessed === 0 ? ' · 有待处理冲突' : ''}
        </p>
      )}
      <p>
        逐幅看实图和原文再判断。画面现在没动，不等于已决定留静。普通试读、阅读包和工程备份不受此步骤限制；阅读器正式签核前须完成。
      </p>
      {q.error && (
        <p role="alert">
          无法核对当前插图：{q.error.message}{' '}
          <button type="button" onClick={() => void q.refetch()}>
            重新读取
          </button>
        </p>
      )}
      {expanded && data && (
        <>
          <p>
            只审已经放进章节的插图，不把素材库候选、封面或背景当作段后插图。此处记录不会启用、停用或生成任何动效。
          </p>
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
          {!!data.changed.length && (
            <p role="status">
              原有判断已过期：{data.changed.map((k) => data.display[k]?.title || k).join('、')}
              。请按当前实图和位置重审。
            </p>
          )}
          {!row && <p>当前没有已放置的章节插图，无需逐幅判断。</p>}
          {row && detail && (
            <div className="screening-entry">
              <label>
                选择要审的章节插图
                <select
                  value={row.plate_id}
                  disabled={working}
                  onChange={(e) => choose(e.target.value)}
                >
                  {data.worksheet.plates.map((r, i) => (
                    <option key={r.plate_id} value={r.plate_id}>
                      {i + 1}. {data.display[r.plate_id].title} · {names[r.decision]}
                    </option>
                  ))}
                </select>
              </label>
              <figure>
                <img
                  key={imageKey}
                  src={`/api/projects/${projectId}/reader/assets/${encodeURIComponent(row.image_asset_id)}?sha256=${row.image_sha256}`}
                  alt={'待审底图：' + detail.title}
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
                  {detail.title} · {row.width} × {row.height} · 段后字节 {row.after_byte}
                </figcaption>
              </figure>
              {broken && <p role="alert">实图无法核对，不能保存判断。</p>}
              <p>
                此幅之前刚读到的原文（字节 {row.paragraph_start}–{row.after_byte}）
              </p>
              <blockquote>{detail.paragraph}</blockquote>
              {data.display[row.plate_id]?.carrier && (
                <p>此幅已有可播放的导演设置；这里只记录意见，不代表已经核验播放像素。</p>
              )}
              {issue?.map((f) => (
                <p role="alert" key={f}>
                  {fault(f)}
                </p>
              ))}
              {outdated && (
                <p role="alert">
                  编排或审图单已更新。请复制需要保留的输入，再放弃草稿并查看最新图文。
                </p>
              )}
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (!draft || disabled || seen !== imageKey || row.decision === 'unassessed')
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
                        value={row.proposed_effect || data.display[row.plate_id]?.carrier || ''}
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
          <div className="screening-files">
            <p>
              本机自动保留已保存的判断。换机前另存私有审图单；普通阅读包和工程 ZIP
              都不含这份单。还原工程后可导入完全匹配的副本。
            </p>
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
          </div>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  )
}
