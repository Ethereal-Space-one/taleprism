import { useEffect, useId, useRef, useState, type ChangeEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import type { ReaderState } from '../reader-types'
import {
  images,
  lenses,
  makeBrief,
  sounds,
  type Citation,
  type Idea,
  type Lens,
  type Options,
} from './creativeTypes'
import { CreativeImage } from './CreativeImage'
import './creative.css'

export const jsonBody = (body: unknown, method = 'POST') => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})
export type Act = (work: () => Promise<void>, writes?: boolean) => Promise<void>

function Quote({ cite, label }: { cite: Citation; label: string }) {
  return (
    <div className="creative-quote">
      <small>
        {label} · 第 {cite.paragraph} 段
      </small>
      <blockquote>{cite.quote}</blockquote>
    </div>
  )
}

export function CreativeDesk({
  projectId,
  data,
  locked,
  onWriting,
  onSoundReview,
}: {
  projectId: string
  data: ReaderState
  locked: boolean
  onWriting: (v: boolean) => void
  onSoundReview: (anchor: number) => void
}) {
  const [open, setOpen] = useState(false),
    [lens, setLens] = useState<Lens>('sound')
  const [proposals, setProposals] = useState<Partial<Record<Lens, Idea>>>({})
  const [confirm, setConfirm] = useState(false),
    [busy, setBusy] = useState(false)
  const [error, setError] = useState(''),
    [note, setNote] = useState(''),
    [foldPreview, setFoldPreview] = useState(false)
  const [pendingSound, setPendingSound] = useState<number | null>(null),
    [replace, setReplace] = useState(false)
  const lock = useRef(false),
    alive = useRef(true),
    id = useId(),
    cache = useQueryClient()
  const prefix = '/api/projects/' + projectId + '/reader',
    path = prefix + '/creative'
  const options = useQuery({
    queryKey: ['creative-options', projectId],
    queryFn: () => api<Options>(path + '/options'),
    enabled: open,
    retry: false,
  })
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])
  const idea = proposals[lens],
    blocked = busy || locked
  const fold = data.config.echo_fold
  const alreadyEcho =
    !!fold &&
    !!idea?.earlier &&
    !!idea.later &&
    fold.earlier.paragraph === idea.earlier.paragraph &&
    fold.earlier.quote === idea.earlier.quote &&
    fold.later.paragraph === idea.later.paragraph &&
    fold.later.quote === idea.later.quote
  function clearStatus() {
    setConfirm(false)
    setError('')
    setNote('')
    setReplace(false)
    setPendingSound(null)
    setFoldPreview(false)
  }
  function selectLens(next: Lens) {
    clearStatus()
    setLens(next)
  }
  const act: Act = async (work, writes = true) => {
    if (lock.current || locked) return
    lock.current = true
    setBusy(true)
    if (writes) onWriting(true)
    setError('')
    setNote('')
    try {
      await work()
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : '操作未完成，请重试。')
    } finally {
      lock.current = false
      if (alive.current) {
        setBusy(false)
        if (writes) onWriting(false)
      }
    }
  }
  async function changed() {
    await Promise.all(
      ['reader', 'reader-content', 'soundscapes', 'delivery', 'jobs'].map((key) =>
        cache.invalidateQueries({ queryKey: [key, projectId] }),
      ),
    )
  }
  function propose(mode: 'local' | 'model') {
    void act(async () => {
      const opt = options.data
      if (mode === 'model' && (!opt?.configured || !confirm))
        throw Error('请先核对本次请求的接口与原文范围。')
      setConfirm(false)
      const value = await api<Idea>(
        path + '/propose',
        jsonBody({
          mode,
          lens,
          ...(mode === 'model'
            ? { consent: true, destination: opt!.destination, model: opt!.model }
            : {}),
        }),
      )
      if (!alive.current) return
      clearStatus()
      setProposals((p) => ({ ...p, [lens]: value }))
    }, false)
  }
  async function fileChanged(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    await act(async () => {
      if (file.size > 8192) throw Error('提案文件过大：最多 8 KiB。请选择 JSON，不是原文或图片。')
      let input
      try {
        input = JSON.parse(await file.text())
      } catch {
        throw Error('这不是可读的 JSON 提案。')
      }
      if (input?.lens !== lens)
        throw Error('此提案的方向与当前选项不同，请先选择对应的声音、影像或呈现方式。')
      const value = await api<Idea>(path + '/import', jsonBody(input))
      if (!alive.current) return
      clearStatus()
      setProposals((p) => ({ ...p, [lens]: value }))
    }, false)
  }
  function download() {
    if (!options.data) return
    const blob = new Blob([makeBrief(lens, options.data.source_sha256, data.paragraphs)], {
      type: 'text/plain;charset=utf-8',
    })
    const url = URL.createObjectURL(blob),
      a = document.createElement('a')
    a.href = url
    a.download = 'Taleprism-' + lens + '-创意任务.txt'
    a.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 2000)
    setNote('任务文件含本篇全文，已在本机准备下载。不会替你交给任何服务。')
  }
  async function saveFold(remove = false) {
    await act(async () => {
      if (
        !remove &&
        (!idea?.earlier || !idea.later || !foldPreview || alreadyEcho || (fold && !replace))
      )
        throw Error('请先试翻，并确认是否替换已有折页。')
      await api(
        prefix,
        jsonBody(
          {
            ...data.config,
            revision: data.revision,
            echo_fold: remove ? null : { earlier: idea!.earlier, later: idea!.later },
          },
          'PATCH',
        ),
      )
      await changed()
      setReplace(false)
      setNote(
        remove
          ? '折页已撤下，原文仍在原位。'
          : '折页已采用。导出新版后，读到后段时才会展开前文原句；安静阅读时可自己翻开。',
      )
    })
  }
  function stageSound() {
    if (!idea?.later || !idea.sound) return
    const paragraph = data.paragraphs[idea.later.paragraph - 1],
      quote = idea.later.quote
    void act(async () => {
      const at = paragraph?.text.indexOf(quote) ?? -1
      if (at < 0) throw Error('引文与当前原文不符，请重新读稿。')
      await api(
        prefix + '/soundscapes',
        jsonBody({
          revision: data.revision,
          byte_start: paragraph.byte_start,
          evidence: quote,
          evidence_start:
            paragraph.byte_start + new TextEncoder().encode(paragraph.text.slice(0, at)).length,
          rain: idea.sound === 'rain',
          wind: idea.sound === 'wind',
          pencil: idea.sound === 'pencil',
          car_at: idea.sound === 'car' ? 6 : null,
        }),
      )
      await changed()
      setPendingSound(paragraph.byte_start)
      setNote('待审试听已生成，尚未采用。旧声景和成品都没变。')
    })
  }
  const heading =
    idea?.decision === 'quiet'
      ? '这一处，不必再加。'
      : idea?.sound
        ? sounds[idea.sound]
        : idea?.image
          ? images[idea.image]
          : '让后一句翻回前一句。'
  return (
    <details
      className="creative-desk"
      onToggle={(e) => {
        setOpen(e.currentTarget.open)
        if (!e.currentTarget.open) setConfirm(false)
      }}
    >
      <summary>
        <span>
          <small>CODIRECTOR / 收尾</small>One More Thing · 可选创意终审
        </span>
        <span aria-hidden="true" className="creative-mark">
          ＋
        </span>
      </summary>
      {open && (
        <div className="creative-interior">
          <p className="creative-intro">
            上方可按现有编排试读、导出，不必经过这里。若还想多看一眼，选一个方向：只在原文确实需要时动一处。
          </p>
          <fieldset disabled={blocked} className="creative-methods">
            <legend className="creative-label">用哪种眼光重读？</legend>
            <div className="creative-lenses">
              {(Object.keys(lenses) as Lens[]).map((k) => (
                <button
                  type="button"
                  key={k}
                  aria-pressed={lens === k}
                  onClick={() => selectLens(k)}
                >
                  <small aria-hidden="true">{lenses[k][1]}</small>
                  <span>{lenses[k][0]}</span>
                </button>
              ))}
            </div>
            <h3>{lenses[lens][2]}</h3>
            <div className="creative-actions">
              <button type="button" onClick={() => propose('local')}>
                本机规则试读
              </button>
              <button
                type="button"
                disabled={!options.data?.configured}
                onClick={() => setConfirm(true)}
              >
                请文本模型读这一遍
              </button>
            </div>
            <p className="creative-fine">
              本机规则不调用 AI。
              {options.data && !options.data.configured
                ? '未配置可用模型；仍可导入提案。'
                : '只有单独确认后，才会把本篇原文发给已配置的接口。'}
              {options.isError ? '模型设置暂时不可读；可继续本机试读、导入或直接导出。' : ''}
            </p>
            {confirm && options.data && (
              <div className="creative-consent" role="group" aria-label="本次模型请求">
                <strong>只发送这一次：{lenses[lens][0]}</strong>
                <p>
                  将本篇全部 {data.paragraphs.length} 个非空段落的完整文字和创作任务发往{' '}
                  <code>{options.data.destination}</code>，模型 <code>{options.data.model}</code>
                  。服务商可能保存输入、产生费用；不会发送图片、声音或其他工程记录。
                </p>
                <button type="button" onClick={() => propose('model')}>
                  确认，发送本篇全文一次
                </button>{' '}
                <button type="button" onClick={() => setConfirm(false)}>
                  取消，不发送
                </button>
              </div>
            )}
            <details className="creative-import">
              <summary>已有模型，或想导入提案？</summary>
              <p>只下载任务不发送。你可以自行选择是否把全文交给自己的工具，再把结果带回来。</p>
              <button type="button" onClick={download} disabled={!options.data}>
                下载本方向的创意任务
              </button>
              <label>
                导入本篇提案 JSON
                <input type="file" accept=".json,application/json" onChange={fileChanged} />
              </label>
            </details>
          </fieldset>
          {idea && (
            <section className="creative-proof" aria-label="候选提案" key={JSON.stringify(idea)}>
              <small className="creative-label">
                {idea.origin === 'model'
                  ? '配置的模型返回'
                  : idea.origin === 'local'
                    ? '本机规则 · 非模型输出'
                    : '导入的提案 · 未验证作者身份'}{' '}
                / {lenses[lens][0]}
              </small>
              <h3>{heading}</h3>
              {idea.earlier && <Quote cite={idea.earlier} label="先前" />}
              {idea.later && <Quote cite={idea.later} label={idea.earlier ? '读到' : '原文'} />}
              <p className="creative-reason">
                <strong>为什么是这里</strong>
                {idea.rationale}
              </p>
              {idea.decision === 'sound' && (
                <div>
                  <button
                    type="button"
                    disabled={blocked || pendingSound !== null}
                    onClick={stageSound}
                  >
                    制成待审试听，不采用
                  </button>
                  {pendingSound !== null && (
                    <button
                      type="button"
                      disabled={blocked}
                      onClick={() => onSoundReview(pendingSound)}
                    >
                      去试听这一段 →
                    </button>
                  )}
                </div>
              )}
              {idea.decision === 'image' && (
                <CreativeImage
                  idea={idea}
                  projectId={projectId}
                  data={data}
                  act={act}
                  blocked={blocked}
                  refresh={changed}
                  tell={setNote}
                />
              )}
              {idea.decision === 'echo' && (
                <div>
                  <details
                    className="creative-fold-test"
                    onToggle={(e) => {
                      if (e.currentTarget.open) setFoldPreview(true)
                    }}
                  >
                    <summary>试翻折页：读到第 {idea.later?.paragraph} 段时</summary>
                    <small>回看第 {idea.earlier?.paragraph} 段 · 只有原文</small>
                    <blockquote>{idea.earlier?.quote}</blockquote>
                  </details>
                  {fold && !alreadyEcho && (
                    <label>
                      <input
                        type="checkbox"
                        checked={replace}
                        disabled={blocked}
                        onChange={(e) => setReplace(e.target.checked)}
                      />
                      替换已有折页（第 {fold.later.paragraph} 段）
                    </label>
                  )}
                  <button
                    type="button"
                    disabled={blocked || !foldPreview || alreadyEcho || (!!fold && !replace)}
                    onClick={() => void saveFold()}
                  >
                    {alreadyEcho ? '这处折页已采用' : '采用这处回声折页'}
                  </button>
                </div>
              )}
              {idea.decision === 'quiet' && <p>不制作素材，不增加读者按钮，不改动本篇。</p>}
              <button
                className="creative-discard"
                type="button"
                disabled={blocked}
                onClick={() => {
                  clearStatus()
                  setProposals((p) => ({ ...p, [lens]: undefined }))
                  setNote('这条提案已收起。已保存的作品没有改变。')
                }}
              >
                不用这条提案
              </button>
            </section>
          )}
          {lens === 'presentation' && fold && (
            <details className="creative-withdraw">
              <summary>当前已采用 · 第 {fold.later.paragraph} 段后有一处折页</summary>
              <p>“{fold.earlier.quote}”</p>
              <button disabled={blocked} type="button" onClick={() => void saveFold(true)}>
                从作品撤下这处折页
              </button>
            </details>
          )}
          <p role="status" id={id} className="creative-status">
            {busy ? '正在处理本次操作…' : note}
          </p>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <p className="creative-end">
            提案理由只在制作台。未采用的提案不会进入阅读包，离开页面不会保留。
          </p>
        </div>
      )}
    </details>
  )
}
