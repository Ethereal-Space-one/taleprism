import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import type { ReaderState } from '../reader-types'
import { useUnsavedWarning } from './leave'
import { heardEntireTake, prepareNarration } from './prepareNarration'
import { voiceUrl, type Narrations, type VoiceTake } from './narrationTypes'
import './voice.css'

type Paragraph = ReaderState['paragraphs'][number]
const fmt = (n: number) =>
  n.toLocaleString('zh-CN', { maximumFractionDigits: 1, minimumFractionDigits: 1 }) + ' 秒'

export function PassageVoice({
  projectId,
  paragraphs,
  initiallyOpen,
  repairRequest = 0,
  published,
  visible,
  locked,
  onWriting,
  onAnchor,
  onDraftDirty,
}: {
  projectId: string
  paragraphs: Paragraph[]
  initiallyOpen: boolean
  repairRequest?: number
  published?: ReadonlySet<string>
  visible: boolean
  locked: boolean
  onWriting: (value: boolean) => void
  onAnchor: (value: number | undefined) => void
  onDraftDirty?: (dirty: boolean) => void
}) {
  const [open, setOpen] = useState(initiallyOpen)
  const [selection, setSelection] = useState('')
  const [writing, setWriting] = useState(false)
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    onDraftDirty?.(dirty)
  }, [dirty, onDraftDirty])
  const wrapper = useRef<HTMLDetailsElement>(null)
  const query = useQuery({
    queryKey: ['narrations', projectId],
    queryFn: () => api<Narrations>(voiceUrl(projectId)),
    enabled: visible && open,
  })
  const firstSaved =
    query.data?.takes.find((t) => t.status === 'accepted') ||
    query.data?.takes.find((t) => t.status === 'pending')
  // Accepted takes omitted by the validated reader projection are the ones
  // preventing delivery. Never steer an editor away from unstored input.
  const repairedRequest = useRef(0)
  const broken = new Set(
    query.data?.takes
      .filter((t) => t.status === 'accepted' && published && !published.has(t.id))
      .map((t) => t.byte_start),
  )
  const firstBroken = broken.size
    ? paragraphs.find((p) => broken.has(p.byte_start))?.byte_start
    : undefined
  const byte = selection || (firstSaved ? String(firstSaved.byte_start) : '')
  const paragraph = paragraphs.find((p) => String(p.byte_start) === byte)
  useEffect(() => {
    if (!selection && firstSaved) setSelection(String(firstSaved.byte_start))
  }, [selection, firstSaved])
  useEffect(() => {
    if (visible && open) onAnchor(paragraph?.byte_start)
  }, [visible, open, onAnchor, paragraph?.byte_start])
  useEffect(() => {
    if (
      !repairRequest ||
      repairedRequest.current === repairRequest ||
      !open ||
      !query.isSuccess ||
      dirty ||
      writing
    )
      return
    repairedRequest.current = repairRequest
    if (firstBroken !== undefined) setSelection(String(firstBroken))
  }, [repairRequest, open, query.isSuccess, dirty, writing, firstBroken])
  const active = visible && open
  function pause() {
    wrapper.current?.querySelectorAll('audio').forEach((el) => el.pause())
  }
  useEffect(() => {
    if (!active) pause()
  }, [active])
  useEffect(() => {
    if (initiallyOpen && visible) setOpen(true)
  }, [initiallyOpen, visible])
  useEffect(() => {
    function hide() {
      if (document.hidden) pause()
    }
    document.addEventListener('visibilitychange', hide)
    return () => document.removeEventListener('visibilitychange', hide)
  }, [])
  return (
    <details
      className="passage-voice"
      ref={wrapper}
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      onPlayCapture={(e) =>
        wrapper.current?.querySelectorAll('audio').forEach((el) => {
          if (el !== e.target) el.pause()
        })
      }
    >
      <summary>段落朗读（可选）</summary>
      <p>
        为一段原文配上你有权使用的短录音。不需要麦克风、配音服务或人物设定。读者自己点播放；不加声音也能导出。
      </p>
      <label>
        朗读对应的原文段落
        <select
          disabled={writing || !query.data}
          value={byte}
          onChange={(e) => {
            if (dirty && !window.confirm('放弃本段尚未保存的录音输入并切换段落？')) return
            pause()
            setDirty(false)
            setSelection(e.target.value)
          }}
        >
          <option value="" disabled>
            选择要朗读的一段
          </option>
          {paragraphs.map((p, i) => {
            const records = query.data?.takes.filter((t) => t.byte_start === p.byte_start) || []
            return (
              <option key={p.byte_start} value={p.byte_start}>
                第 {i + 1} 段 · {p.preview}
                {broken.has(p.byte_start)
                  ? ' · 朗读需修复'
                  : records.some((t) => t.status === 'accepted')
                    ? ' · 有朗读'
                    : records.some((t) => t.status === 'pending')
                      ? ' · 待审'
                      : ''}
              </option>
            )
          })}
        </select>
      </label>
      {query.isPending && active && <p role="status">正在读取本项目录音…</p>}
      {query.error && (
        <p className="error" role="alert">
          {query.error.message}{' '}
          <button type="button" onClick={() => query.refetch()}>
            重新读取录音
          </button>
        </p>
      )}
      {query.data && paragraph && (
        <ClipEditor
          key={projectId + ':' + paragraph.byte_start}
          projectId={projectId}
          data={query.data}
          paragraph={paragraph}
          locked={locked || !!query.error}
          onWriting={(v) => {
            setWriting(v)
            onWriting(v)
          }}
          onDirty={setDirty}
        />
      )}
    </details>
  )
}

function ClipEditor({
  projectId,
  data,
  paragraph,
  locked,
  onWriting,
  onDirty,
}: {
  projectId: string
  data: Narrations
  paragraph: Paragraph
  locked: boolean
  onWriting: (v: boolean) => void
  onDirty: (v: boolean) => void
}) {
  const cache = useQueryClient()
  const [file, setFile] = useState<File | null>(null),
    [credit, setCredit] = useState(''),
    [share, setShare] = useState(false)
  const [pick, setPick] = useState(''),
    [heard, setHeard] = useState(''),
    [message, setMessage] = useState(''),
    [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const lock = useRef(false),
    live = useRef(true),
    abort = useRef<AbortController | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  useEffect(() => {
    live.current = true
    return () => {
      live.current = false
      abort.current?.abort()
    }
  }, [])
  useUnsavedWarning(busy || !!(file || credit || share))
  const unsaved = !!(file || credit || share)
  useEffect(() => {
    onDirty(unsaved)
  }, [unsaved, onDirty])
  const all = data.takes.filter(
    (t) => t.byte_start === paragraph.byte_start && t.byte_end === paragraph.byte_end,
  )
  const pending = all.filter((t) => t.status === 'pending'),
    current = all.find((t) => t.status === 'accepted')
  const archives = all.filter((t) => t.status === 'withdrawn')
  const candidate = pending.find((t) => t.id === pick) || pending.at(-1)
  const reviewKey = candidate ? candidate.id + ':' + (current?.id || '') : ''
  const witnessing = useRef('')
  useEffect(() => {
    if (candidate && pick !== candidate.id) setPick(candidate.id)
  }, [pick, candidate])
  const ready = !!reviewKey && heard === reviewKey
  async function run(
    action: (signal: AbortSignal) => Promise<Narrations>,
    confirmed: (next: Narrations) => void,
  ) {
    if (locked || lock.current) return
    lock.current = true
    onWriting(true)
    setBusy(true)
    setError('')
    setMessage('')
    const controller = new AbortController()
    abort.current = controller
    try {
      const next = await action(controller.signal)
      if (live.current) {
        // Never rewind cache to an old snapshot if another tab won a later save.
        cache.setQueryData<Narrations>(['narrations', projectId], (old) =>
          old && old.revision > next.revision ? old : next,
        )
        confirmed(next)
      }
    } catch (e) {
      if (live.current) setError(e instanceof Error ? e.message : '录音操作未完成，请重试。')
    } finally {
      await Promise.all(
        [
          'narrations',
          'soundscapes',
          'reader',
          'reader-content',
          'delivery',
          'jobs',
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
  function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!file || !credit.trim()) return
    const known = new Set(data.takes.map((t) => t.id))
    const revision = data.revision
    void run(
      async (signal) => {
        const audio = await prepareNarration(file, signal)
        signal.throwIfAborted()
        // The backup count includes every take, even a later withdrawal. Ask
        // before committing a file that threatens portability, never prune.
        const capacity = await api<{
          can_export: boolean
          uncompressed_bytes: number
          limits: { uncompressed_bytes: number }
          errors: string[]
        }>('/api/projects/' + projectId + '/bundle/preflight', { signal })
        const remaining = capacity.limits.uncompressed_bytes - capacity.uncompressed_bytes
        if (!capacity.can_export || remaining - audio.size < 64_000) {
          const notice = capacity.can_export
            ? '保存后可能达到可编辑工程 ZIP 上限。当前余量约 ' +
              Math.max(0, remaining / 1e6).toFixed(2) +
              ' MB；这条录音约 ' +
              (audio.size / 1e6).toFixed(2) +
              ' MB，另需清单空间。'
            : '当前工程已经无法完整导出 ZIP：' + capacity.errors.slice(0, 2).join('；')
          if (
            !window.confirm(
              notice +
                '\n撤回旧录音不会释放备份空间。可以取消并缩短录音；若继续，可能需停止工作台后复制完整数据目录。仍要存为待审录音吗？',
            )
          )
            throw Error('已取消保存，录音输入仍保留。')
        }
        signal.throwIfAborted()
        const form = new FormData()
        form.set('revision', String(revision))
        form.set('byte_start', String(paragraph.byte_start))
        form.set('credit', credit.trim())
        form.set('publish_credit', String(share))
        form.set('file', audio, 'paragraph.wav')
        return api<Narrations>(voiceUrl(projectId), { method: 'POST', body: form, signal })
      },
      (next) => {
        setPick(
          next.takes.find(
            (t) =>
              !known.has(t.id) && t.status === 'pending' && t.byte_start === paragraph.byte_start,
          )?.id || '',
        )
        setFile(null)
        setCredit('')
        setShare(false)
        if (fileInput.current) fileInput.current.value = ''
        setHeard('')
        setMessage('已存为待审录音，还没有替换读者当前听到的版本。')
      },
    )
  }
  function change(take: VoiceTake, status: 'accepted' | 'withdrawn') {
    if (status === 'accepted' && (!ready || take.id !== candidate?.id)) return
    if (
      status === 'withdrawn' &&
      !window.confirm(
        take.status === 'accepted'
          ? '从今后的阅读预览和新阅读包撤下这段朗读？原录音仍保留在可编辑工程里；已发出的旧阅读包不会改变。'
          : '撤回这条待审录音？已采用的版本不变，录音仍保留在工程历史里。',
      )
    )
      return
    void run(
      (signal) =>
        api<Narrations>(voiceUrl(projectId) + '/' + take.id, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ revision: data.revision, status }),
          signal,
        }),
      () => {
        setHeard('')
        setMessage(
          status === 'accepted'
            ? '已采用。新预览和下一份阅读包将使用这条录音。'
            : '已撤回。此录音保留在工程历史里，不随新阅读包交付。',
        )
      },
    )
  }
  return (
    <div className="passage-voice-inner">
      <blockquote aria-label="朗读原文">{paragraph.text}</blockquote>
      <p className="voice-current">
        <b>读者当前版本：</b>
        {current ? '已采用朗读 · ' + fmt(current.duration) : '无朗读，保留纯文字。'}
      </p>
      {current && (
        <div className="voice-stored">
          <audio
            key={current.id}
            controls
            preload="none"
            src={current.url}
            aria-label="已采用的段落朗读"
          />
          <small>
            {current.publish_credit ? '随阅读包公开' : '仅工程内可见'}：{current.credit}
          </small>
          <button
            type="button"
            disabled={busy || locked}
            onClick={() => change(current, 'withdrawn')}
          >
            撤下当前朗读
          </button>
        </div>
      )}
      <form onSubmit={upload}>
        <fieldset disabled={busy || locked}>
          <label>
            选择本机录音
            <input
              type="file"
              ref={fileInput}
              accept=".wav,.mp3,.m4a,audio/wav,audio/mpeg,audio/mp4"
              onChange={(e) => {
                setFile(e.target.files?.[0] || null)
                setError('')
              }}
            />
          </label>
          <p className="asset-helper">
            最长 120 秒，最多 24 MB。WAV、MP3 或 M4A 取决于此浏览器的解码能力。本机转换为单声道
            WAV，不上传原文件名或录音标签。
          </p>
          <label>
            录音来源与使用许可
            <input
              maxLength={200}
              required
              value={credit}
              onChange={(e) => setCredit(e.target.value)}
              placeholder="例如：本人朗读，允许在这篇作品中使用"
            />
          </label>
          <label className="voice-credit">
            <input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} />
            在阅读包中公开上面整条来源与许可说明（默认不公开）
          </label>
          <p className="asset-helper">
            全部录音和说明都保存在可编辑工程 ZIP
            内，包括待审和已撤回版本。阅读包只包含已采用的声音；不勾选时不附来源说明。
          </p>
          {unsaved && (
            <button
              type="button"
              onClick={() => {
                if (
                  !window.confirm(
                    '放弃本段尚未保存的文件选择和来源说明？已存入工程的录音不会改变。',
                  )
                )
                  return
                setFile(null)
                setCredit('')
                setShare(false)
                if (fileInput.current) fileInput.current.value = ''
                setError('')
              }}
            >
              放弃未上传的录音输入
            </button>
          )}
          <button type="submit" disabled={!file || !credit.trim()}>
            存为待审录音
          </button>
        </fieldset>
      </form>
      {candidate && (
        <section className="voice-candidate" aria-label="试听待审录音">
          <h3>试听待审录音</h3>
          {pending.length > 1 && (
            <label>
              待审版本
              <select
                disabled={busy}
                value={candidate.id}
                onChange={(e) => {
                  setPick(e.target.value)
                  setMessage('')
                  setHeard('')
                }}
              >
                {pending.map((t, i) => (
                  <option key={t.id} value={t.id}>
                    版本 {i + 1} · {fmt(t.duration)} · {t.credit}
                  </option>
                ))}
              </select>
            </label>
          )}
          <p>
            {fmt(candidate.duration)} · {candidate.credit} ·{' '}
            {candidate.publish_credit ? '采用时公开这条说明' : '说明只在工程内'}
          </p>
          <audio
            key={reviewKey}
            controls
            preload="metadata"
            src={candidate.url}
            aria-label="试听待审段落朗读"
            onPlay={(e) => {
              const a = e.currentTarget
              if (!a.muted && a.volume > 0 && a.currentTime < 0.04) witnessing.current = reviewKey
            }}
            onSeeking={() => {
              witnessing.current = ''
            }}
            onSeeked={(e) => {
              const a = e.currentTarget
              if (!a.paused && !a.muted && a.volume > 0 && a.currentTime < 0.04)
                witnessing.current = reviewKey
            }}
            onVolumeChange={(e) => {
              if (e.currentTarget.muted || e.currentTarget.volume === 0) witnessing.current = ''
            }}
            onEnded={(e) => {
              const el = e.currentTarget
              if (
                witnessing.current === reviewKey &&
                !el.muted &&
                el.volume > 0 &&
                heardEntireTake(el.played, el.duration)
              ) {
                setHeard(reviewKey)
                setMessage('已完整播放。请自己核对读音、内容和使用权，再决定是否采用。')
              } else {
                setHeard('')
                setMessage('需要从头到尾试听；拖到结尾不会算作完整播放。')
              }
            }}
            onError={() => {
              setHeard('')
              setError('待审录音无法播放，不能采用。可以重载页面或另选录音；原版本不会被替换。')
            }}
          />
          <p>
            对照上面的原文完整试听。
            {current ? '采用后才会替换当前版本。' : '只有明确采用后读者才会听到。'}
          </p>
          <div className="voice-actions">
            <button
              type="button"
              disabled={!ready || busy || locked}
              onClick={() => change(candidate, 'accepted')}
            >
              已对照原文，采用此朗读
            </button>
            <button
              type="button"
              disabled={busy || locked}
              onClick={() => change(candidate, 'withdrawn')}
            >
              撤回待审录音
            </button>
          </div>
        </section>
      )}
      {!!archives.length && (
        <details className="voice-history">
          <summary>已撤回录音（{archives.length}）</summary>
          {archives.map((t, i) => (
            <div key={t.id}>
              <small>
                历史 {i + 1} · {fmt(t.duration)} · {t.credit}
              </small>
              <audio controls preload="none" src={t.url} aria-label={'已撤回录音 ' + (i + 1)} />
            </div>
          ))}
        </details>
      )}
      {locked && (
        <p role="status">先保存章节或动效修改，或等当前操作结束，再改动录音；本页的选择仍在。</p>
      )}
      {busy && <p role="status">正在本机处理录音，请稍候…</p>}
      {message && <p role="status">{message}</p>}
      {error && (
        <p className="error" role="alert">
          {error} 已采用的版本不会因操作失败而改变。
        </p>
      )}
    </div>
  )
}
