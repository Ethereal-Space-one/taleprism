import { useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { byteLength, sourceSlice } from '../reader/model'
import type { ReaderState } from '../reader-types'
import { heardEntireTake } from './prepareNarration'
import {
  layers,
  occurrences,
  selectedSoundEvidence,
  soundUrl,
  type Soundscapes,
  type SoundTake,
} from './soundscape'
import './voice.css'

type Paragraph = ReaderState['paragraphs'][number]

/** The review belongs to the particular candidate AND the active version it would replace. */
function Audition({
  take,
  decide,
  disabled,
  replacing,
}: {
  take: SoundTake
  decide: () => void
  disabled: boolean
  replacing: boolean
}) {
  const [heard, setHeard] = useState(false),
    [failure, setFailure] = useState('')
  const witnessing = useRef(false)
  return (
    <section className="voice-candidate" aria-label="待审声景">
      <h3>听一遍，再决定</h3>
      <p>
        原文依据：<q>{take.evidence}</q>
      </p>
      <p>{layers(take)} · 12 秒</p>
      <audio
        controls
        preload="metadata"
        src={take.url}
        aria-label="试听待审声景"
        onPlay={(e) => {
          const a = e.currentTarget
          if (a.currentTime < 0.06 && !a.muted && a.volume > 0) {
            witnessing.current = true
            setFailure('')
          }
        }}
        onSeeking={() => {
          witnessing.current = false
        }}
        onSeeked={(e) => {
          const a = e.currentTarget
          if (!a.paused && a.currentTime < 0.06 && !a.muted && a.volume > 0)
            witnessing.current = true
        }}
        onVolumeChange={(e) => {
          if (e.currentTarget.muted || !e.currentTarget.volume) witnessing.current = false
        }}
        onEnded={(e) => {
          const a = e.currentTarget
          const full =
            witnessing.current && !a.muted && a.volume > 0 && heardEntireTake(a.played, a.duration)
          setHeard(full)
          setFailure(full ? '' : '请从头到尾试听；拖动到结尾不算完整播放。')
        }}
        onError={() => {
          witnessing.current = false
          setHeard(false)
          setFailure('候选音频无法播放，不能采用。请重新生成；现用版本不会变化。')
        }}
      />
      <p>
        {heard
          ? '已完整播放。请自己判断这些声音是否符合原文。'
          : '请完整试听，并核对声音和出现的时刻是否符合这段原文。'}
        {replacing ? '采用后才会替换读者当前听到的声景。' : ''}
      </p>
      {failure && <p role="status">{failure}</p>}
      <button type="button" disabled={disabled || !heard} onClick={decide}>
        已对照原文，采用此声景
      </button>
    </section>
  )
}

export function PassageSoundscape({
  projectId,
  paragraphs,
  initiallyOpen,
  visible,
  locked,
  onDirty,
  onWriting,
  onAnchor,
  repairRequest = 0,
  creativeTarget,
  published,
}: {
  projectId: string
  paragraphs: Paragraph[]
  initiallyOpen: boolean
  visible: boolean
  locked: boolean
  onDirty: (v: boolean) => void
  onWriting: (v: boolean) => void
  onAnchor: (n: number | undefined) => void
  repairRequest?: number
  creativeTarget?: { anchor: number; seq: number }
  published?: ReadonlySet<string>
}) {
  const [open, setOpen] = useState(initiallyOpen),
    [selection, setSelection] = useState('')
  const [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false)
  const area = useRef<HTMLDetailsElement>(null),
    lastRepair = useRef(0)
  const list = useQuery({
    queryKey: ['soundscapes', projectId],
    queryFn: () => api<Soundscapes>(soundUrl(projectId)),
    enabled: open && visible,
  })
  const creativeSeq = useRef(0)
  useEffect(() => {
    if (
      creativeTarget &&
      creativeTarget.seq !== creativeSeq.current &&
      !dirty &&
      !busy &&
      visible
    ) {
      creativeSeq.current = creativeTarget.seq
      setOpen(true)
      setSelection(String(creativeTarget.anchor))
    }
  }, [creativeTarget, dirty, busy, visible])
  const [visited, setVisited] = useState(initiallyOpen)
  const stageByAnchor = useMemo(() => {
    const byAnchor = new Map<number, string>()
    for (const t of list.data?.takes || []) {
      if (t.status === 'accepted' || (t.status === 'pending' && !byAnchor.has(t.byte_start)))
        byAnchor.set(t.byte_start, t.status)
    }
    return byAnchor
  }, [list.data])
  const active =
    list.data?.takes.find((t) => t.status === 'accepted') ||
    list.data?.takes.find((t) => t.status === 'pending')
  const byte = selection || (active ? String(active.byte_start) : '')
  const paragraph = paragraphs.find((p) => String(p.byte_start) === byte)
  const broken = new Set(
    list.data?.takes
      .filter((t) => t.status === 'accepted' && published && !published.has(t.id))
      .map((t) => t.byte_start),
  )
  const firstBroken = broken.size
    ? paragraphs.find((p) => broken.has(p.byte_start))?.byte_start
    : undefined
  useEffect(() => {
    if (!selection && active) setSelection(String(active.byte_start))
  }, [selection, active])
  useEffect(() => {
    if (visible && initiallyOpen) setOpen(true)
  }, [visible, initiallyOpen])
  useEffect(() => {
    if (open && visible && paragraph) onAnchor(paragraph.byte_start)
  }, [open, visible, paragraph?.byte_start, onAnchor])
  useEffect(() => {
    if (
      repairRequest !== lastRepair.current &&
      !dirty &&
      !busy &&
      firstBroken !== undefined &&
      open
    ) {
      lastRepair.current = repairRequest
      setSelection(String(firstBroken))
    }
  }, [repairRequest, firstBroken, open, dirty, busy])
  useLayoutEffect(() => onDirty(dirty), [dirty, onDirty])
  useLayoutEffect(() => onWriting(busy), [busy, onWriting])
  useEffect(() => {
    const pause = () => area.current?.querySelectorAll('audio').forEach((a) => a.pause())
    if (!visible || !open) pause()
    const hide = () => {
      if (document.hidden) pause()
    }
    document.addEventListener('visibilitychange', hide)
    return () => document.removeEventListener('visibilitychange', hide)
  }, [visible, open])
  return (
    <details
      ref={area}
      className="passage-soundscape"
      open={open}
      onToggle={(e) => {
        setOpen(e.currentTarget.open)
        if (e.currentTarget.open) setVisited(true)
      }}
    >
      <summary>段落声景（可选）</summary>
      {(visited || open) && (
        <>
          <p>
            一处声音，给原文留出安静。可以单用纸上的铅笔声，也可用雨、风或一辆经过的车。每次只有 12
            秒，没有对白。采用后，读者读到这一段时听见；也可安静阅读，再自己点听。
          </p>
          <label>
            声景对应的原文段落
            <select
              aria-label="声景对应的原文段落"
              disabled={!list.data || busy || locked}
              value={byte}
              onChange={(e) => {
                if (dirty && !window.confirm('放弃本段尚未生成的声景设置，切换段落？')) return
                setDirty(false)
                setSelection(e.target.value)
              }}
            >
              <option value="" disabled>
                选择要配环境声的一段
              </option>
              {paragraphs.map((p, i) => (
                <option key={p.byte_start} value={p.byte_start}>
                  第 {i + 1} 段 · {p.preview}
                  {broken.has(p.byte_start)
                    ? ' · 声景需修复'
                    : stageByAnchor.get(p.byte_start) === 'accepted'
                      ? ' · 有声景'
                      : stageByAnchor.get(p.byte_start) === 'pending'
                        ? ' · 待审'
                        : ''}
                </option>
              ))}
            </select>
          </label>
          {list.isPending && visible && open && <p role="status">正在读取工程内的声景…</p>}
          {list.error && (
            <p role="alert">
              {list.error.message} <button onClick={() => list.refetch()}>重读声景记录</button>
            </p>
          )}
          {list.data && paragraph && (
            <SoundEditor
              key={projectId + ':' + paragraph.byte_start}
              projectId={projectId}
              paragraph={paragraph}
              state={list.data}
              locked={locked || !!list.error}
              onDirty={setDirty}
              onWriting={setBusy}
            />
          )}
          {locked && <p role="status">请先保存或放弃其他编辑，或等当前操作完成，再改动声景。</p>}
        </>
      )}
    </details>
  )
}

function SoundEditor({
  projectId,
  paragraph,
  state,
  locked,
  onDirty,
  onWriting,
}: {
  projectId: string
  paragraph: Paragraph
  state: Soundscapes
  locked: boolean
  onDirty: (v: boolean) => void
  onWriting: (v: boolean) => void
}) {
  const cache = useQueryClient(),
    endpoint = soundUrl(projectId)
  const [evidence, setEvidence] = useState(''),
    [occurrence, setOccurrence] = useState('')
  const [base, setBase] = useState<'rain' | 'wind' | 'pencil' | null>('rain'),
    [car, setCar] = useState(false),
    [peak, setPeak] = useState('6')
  const [pick, setPick] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [msg, setMsg] = useState('')
  const [reviewEpoch, setReviewEpoch] = useState(0)
  const source = useRef<HTMLTextAreaElement>(null),
    lock = useRef(false),
    abort = useRef<AbortController | null>(null),
    live = useRef(true)
  const matches = occurrences(paragraph.text, evidence)
  const nth = matches.length === 1 ? 1 : Number(occurrence)
  const start = Number.isSafeInteger(nth) && nth > 0 ? matches[nth - 1] : undefined
  const rain = base === 'rain',
    wind = base === 'wind',
    pencil = base === 'pencil'
  const dirty = !!evidence || !rain || car
  useLayoutEffect(() => onDirty(dirty), [dirty, onDirty])
  useEffect(() => {
    live.current = true
    return () => {
      live.current = false
      abort.current?.abort()
    }
  }, [])
  const all = state.takes.filter(
    (t) => t.byte_start === paragraph.byte_start && t.byte_end === paragraph.byte_end,
  )
  const current = all.find((t) => t.status === 'accepted'),
    pending = all.filter((t) => t.status === 'pending'),
    old = all.filter((t) => t.status === 'withdrawn')
  const candidate = pending.find((t) => t.id === pick) || pending.at(-1)
  function clear() {
    setEvidence('')
    setOccurrence('')
    setBase('rain')
    setCar(false)
    setPeak('6')
  }
  function selectedText() {
    const el = source.current
    if (!el || el.selectionEnd <= el.selectionStart) {
      setError('请先在原文里选中几个字，或直接在「原文依据」填写。')
      return
    }
    const selected = selectedSoundEvidence(paragraph.text, el.selectionStart, el.selectionEnd)
    if (!selected) {
      setError('请选择 1 至 300 个字，不能只有空白。')
      return
    }
    setEvidence(selected.text)
    setOccurrence(String(selected.occurrence))
    setError('')
  }
  async function change(action: 'generate' | 'accepted' | 'withdrawn', take?: SoundTake) {
    if (locked || lock.current) return
    if (
      action === 'withdrawn' &&
      !window.confirm(
        take?.status === 'accepted'
          ? '撤下当前声景？新的阅读包不再含这段环境声；此前交付的包不受影响。'
          : '撤回这条待审声景？编辑历史仍会保留。',
      )
    )
      return
    if (action === 'generate' && (start === undefined || (!base && !car))) return
    lock.current = true
    setBusy(true)
    onWriting(true)
    setError('')
    setMsg('')
    const controller = new AbortController()
    abort.current = controller
    const signal = controller.signal,
      revision = state.revision
    try {
      if (action === 'generate') {
        const pre = await api<{
          can_export: boolean
          uncompressed_bytes: number
          limits: { uncompressed_bytes: number }
        }>(`/api/projects/${projectId}/bundle/preflight`, { signal })
        if (
          !pre.can_export ||
          pre.limits.uncompressed_bytes - pre.uncompressed_bytes < 1_152_044 + 64_000
        ) {
          if (
            !window.confirm(
              '此工程已接近完整备份容量上限，或已有素材问题。撤下声景不会释放备份空间。可以取消；若继续，可能需停止工作台，再复制整个数据目录。仍要生成待审声景吗？',
            )
          ) {
            if (live.current) setMsg('已取消生成，当前设置仍保留。')
            return
          }
        }
      }
      const next = await api<Soundscapes>(
        action === 'generate' ? endpoint : endpoint + '/' + take!.id,
        {
          method: action === 'generate' ? 'POST' : 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          signal,
          body: JSON.stringify(
            action === 'generate'
              ? {
                  revision,
                  byte_start: paragraph.byte_start,
                  evidence,
                  evidence_start: paragraph.byte_start + byteLength(paragraph.text.slice(0, start)),
                  rain,
                  wind,
                  ...(pencil ? { pencil: true } : {}),
                  car_at: car ? Number(peak) : null,
                }
              : { revision, status: action },
          ),
        },
      )
      if (live.current) {
        cache.setQueryData<Soundscapes>(['soundscapes', projectId], (prev) =>
          prev && prev.revision > next.revision ? prev : next,
        )
        if (action === 'generate') {
          const ids = new Set(state.takes.map((t) => t.id))
          const created = next.takes.find(
            (t) =>
              !ids.has(t.id) && t.byte_start === paragraph.byte_start && t.status === 'pending',
          )
          if (created) setPick(created.id)
          clear()
          setMsg('已生成待审声景。尚未改变读者当前版本。')
        } else
          setMsg(
            action === 'accepted'
              ? '已采用此声景，可重新试读或导出。'
              : '已撤回此声景，制作历史保留。',
          )
      }
    } catch (e) {
      if (live.current) {
        setError(
          (e instanceof Error ? e.message : '操作未完成。') +
            ' 请核对最新版本后重试；当前输入保留。',
        )
        setReviewEpoch((n) => n + 1)
      }
    } finally {
      await Promise.all(
        [
          'soundscapes',
          'narrations',
          'reader',
          'reader-content',
          'delivery',
          'jobs',
          'editorial',
          'bundle-preflight',
        ].map((k) =>
          cache.invalidateQueries({
            queryKey: [k, k === 'bundle-preflight' ? '/api/projects/' + projectId : projectId],
          }),
        ),
      )
      lock.current = false
      abort.current = null
      if (live.current) {
        setBusy(false)
        onWriting(false)
      }
    }
  }

  return (
    <div className="sound-editor">
      <p>
        <b>读者当前声景：</b>
        {current ? layers(current) + ' · 12 秒' : '无声景，仅保留原文与其他已采用素材。'}
      </p>
      {current && (
        <div className="voice-stored">
          <audio
            key={current.id}
            controls
            preload="none"
            aria-label="已采用的段落声景"
            src={current.url}
          />
          <small>
            工程内原文依据：<q>{current.evidence}</q>
          </small>
          <button disabled={locked || busy || dirty} onClick={() => change('withdrawn', current)}>
            撤下当前声景
          </button>
        </div>
      )}
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          void change('generate')
        }}
      >
        <fieldset disabled={locked || busy}>
          <label>
            声景原文
            <textarea aria-label="声景原文" ref={source} readOnly rows={3} value={paragraph.text} />
          </label>
          <button className="text-button" type="button" onClick={selectedText}>
            使用框选的原文
          </button>
          <label>
            原文依据
            <input
              required
              value={evidence}
              maxLength={600}
              onChange={(e) => {
                setEvidence(e.target.value)
                setOccurrence('')
                setError('')
              }}
              placeholder="摘录本段里支持这处声音的原句或几个字"
            />
          </label>
          {evidence && !matches.length && (
            <p role="status">请选择本段中连续的 1–300 个原文字，标点、空格也需一致。</p>
          )}
          {matches.length > 1 && (
            <label>
              相同引文的位置（共 {matches.length} 处）
              <input
                required
                type="number"
                min={1}
                max={matches.length}
                step={1}
                placeholder="选第几处"
                value={occurrence}
                onChange={(e) => setOccurrence(e.target.value)}
              />
            </label>
          )}
          {start !== undefined && matches.length > 1 && (
            <p>
              所选位置：…{sourceSlice(paragraph.text, start - 12, start)}
              <mark>{evidence}</mark>
              {sourceSlice(paragraph.text, start + evidence.length, start + evidence.length + 12)}…
            </p>
          )}
          <p className="asset-helper">
            纸上铅笔声单独使用，停笔后不铺底声。若选雨或风，可以加上一辆车。
          </p>
          <div className="sound-layers">
            <label className="voice-credit">
              <input
                type="checkbox"
                checked={rain}
                onChange={(e) => setBase(e.target.checked ? 'rain' : null)}
              />
              持续细雨
            </label>
            <label className="voice-credit">
              <input
                type="checkbox"
                checked={wind}
                onChange={(e) => setBase(e.target.checked ? 'wind' : null)}
              />
              持续风声
            </label>
            <label className="voice-credit">
              <input
                type="checkbox"
                checked={car}
                onChange={(e) => {
                  setCar(e.target.checked)
                  if (e.target.checked && pencil) setBase(null)
                }}
              />
              一辆车驶过
            </label>
            <label className="voice-credit">
              <input
                type="checkbox"
                checked={pencil}
                onChange={(e) => {
                  setBase(e.target.checked ? 'pencil' : null)
                  if (e.target.checked) setCar(false)
                }}
              />
              纸上铅笔，停笔留白
            </label>
          </div>
          {car && (
            <label>
              车辆经过的时刻（秒）
              <input
                type="number"
                aria-label="车辆经过的时刻（秒）"
                min={2}
                max={10}
                step={1}
                required
                value={peak}
                onChange={(e) => setPeak(e.target.value)}
              />
              <small>整个声景 12 秒，可选第 2 至 10 秒作为车辆最接近的时刻。</small>
            </label>
          )}
          {!base && !car && <p>选择至少一种声音，也可以放弃设置，让本段保持安静。</p>}
          <p className="asset-helper">
            声音由工作台在本机合成，不使用外部录音或麦克风。阅读包只带已采用的混音和简短声音描述；引文位置、声层设置和待审／撤回版本只随可编辑工程保留。
          </p>
          <div className="voice-actions">
            <button disabled={start === undefined || (!base && !car)}>生成待审声景</button>
            {dirty && (
              <button
                type="button"
                onClick={() => {
                  if (window.confirm('放弃尚未生成的声景设置？已保存的版本不受影响。')) {
                    clear()
                    setError('')
                    setMsg('')
                  }
                }}
              >
                放弃声景设置
              </button>
            )}
          </div>
        </fieldset>
      </form>
      {candidate && (
        <>
          <label>
            待审声景版本
            <select
              value={candidate.id}
              disabled={busy || locked || dirty}
              onChange={(e) => setPick(e.target.value)}
            >
              {pending.map((t, i) => (
                <option key={t.id} value={t.id}>
                  版本 {i + 1} · {layers(t)}
                </option>
              ))}
            </select>
          </label>
          <Audition
            key={candidate.id + ':' + (current?.id || '') + ':' + reviewEpoch}
            take={candidate}
            disabled={busy || locked || dirty}
            replacing={!!current}
            decide={() => {
              void change('accepted', candidate)
            }}
          />
          <button disabled={locked || busy || dirty} onClick={() => change('withdrawn', candidate)}>
            撤回待审声景
          </button>
        </>
      )}
      {old.length > 0 && (
        <details className="voice-history">
          <summary>已撤回声景（{old.length}）</summary>
          {old.map((t, i) => (
            <div key={t.id}>
              <p>
                {layers(t)} · 依据：<q>{t.evidence}</q>
              </p>
              <audio controls preload="none" src={t.url} aria-label={'已撤回声景 ' + (i + 1)} />
            </div>
          ))}
        </details>
      )}
      {busy && <p role="status">正在本机处理声景…</p>}
      {msg && <p role="status">{msg}</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  )
}
