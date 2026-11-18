import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Project } from './api'
import type { ReaderAsset, ReaderState } from './reader-types'
import { ReaderPanel } from './ReaderPanel'
import { soundUrl, type Soundscapes } from './studio/soundscape'
import { voiceUrl, type Narrations } from './studio/narrationTypes'
import { useUnsavedWarning } from './studio/leave'
import './studio/studio.css'

export const studioUrl = (id: string) => '/?studio=' + encodeURIComponent(id)
const firstPlate = 'studio-first-illustration'
const studioId = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/

export function StudioIntro() {
  return (
    <section className="studio-intro" aria-label="自己的图文">
      <div>
        <p className="guided-kicker">ONE ILLUSTRATION / 单幅图文</p>
        <h1>从一段故事开始。</h1>
        <p>
          带来一段原文，不必凑齐素材。你采用的声景、插图与折页，会在读者读到对应段落时出现；只选静图，画就不动。
        </p>
      </div>
      <div>
        <a className="studio-cta" href={studioUrl('new')}>
          用自己的图文开始 <span aria-hidden="true">→</span>
        </a>
        <small>只在本机制作 · 不下载样例 · 不用 API Key</small>
      </div>
    </section>
  )
}

type StartLane = 'art' | 'voice' | 'sound' | 'finish'
function SourceStep({ onCreated }: { onCreated: (p: Project, lane: StartLane) => void }) {
  const [source, setSource] = useState('paste')
  const rightsRef = useRef<HTMLSelectElement>(null)
  function resetRights() {
    if (rightsRef.current) rightsRef.current.value = ''
  }
  const [dirty, setDirty] = useState(false)
  const [hint, setHint] = useState('')
  const lock = useRef(false)
  const create = useMutation({
    mutationFn: ({ form }: { form: FormData; lane: StartLane }) =>
      api<Project>('/api/projects', { method: 'POST', body: form }),
    onSuccess: (project, { lane }) => onCreated(project, lane),
    onSettled: () => {
      lock.current = false
    },
  })
  useUnsavedWarning(dirty || create.isPending)
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (lock.current) return
    const inputs = new FormData(event.currentTarget)
    const form = new FormData()
    form.set('rights_status', String(inputs.get('rights_status')))
    form.set('single_plate_studio', 'true')
    if (source === 'paste') {
      const passage = String(inputs.get('passage') || '')
      if (!passage.trim()) {
        setHint('请输入至少一个可显示的原文字符。')
        return
      }
      const title = String(inputs.get('title') || '').trim()
      if (!title) {
        setHint('请为这段原文起个名字。')
        return
      }
      form.set(
        'file',
        new File([passage], title.replace(/\.txt$/i, '') + '.txt', {
          type: 'text/plain;charset=utf-8',
        }),
      )
      form.set('encoding', 'utf-8')
    } else {
      const file = inputs.get('file')
      if (
        !(file instanceof File) ||
        !file.size ||
        file.size > 2_000_000 ||
        !/\.txt$/i.test(file.name)
      ) {
        setHint('请选择一份非空 TXT，文件不超过 2 MB。')
        return
      }
      form.set('file', file)
      form.set('encoding', String(inputs.get('encoding')))
    }
    lock.current = true
    setHint('')
    const submitter = (event.nativeEvent as SubmitEvent).submitter
    create.mutate({
      form,
      lane:
        submitter instanceof HTMLButtonElement &&
        (submitter.value === 'voice' || submitter.value === 'sound' || submitter.value === 'finish')
          ? submitter.value
          : 'art',
    })
  }
  return (
    <section className="studio-card" aria-labelledby="studio-source-title">
      <p className="guided-kicker">01 / 原文</p>
      <h2 id="studio-source-title">这次要读哪一段故事？</h2>
      <p>
        每次都新建独立项目，不改动旧作。原文按换行分段，之后可为某一段配朗读、环境声，或放上一幅插图。
      </p>
      <form
        onSubmit={submit}
        onChange={() => {
          setDirty(true)
          setHint('')
        }}
      >
        <fieldset disabled={create.isPending} className="studio-fields">
          <label>
            原文输入方式
            <select
              value={source}
              onChange={(e) => {
                setSource(e.target.value)
                resetRights()
              }}
            >
              <option value="paste">粘贴短文</option>
              <option value="file">导入 TXT</option>
            </select>
          </label>
          <div hidden={source !== 'paste'}>
            <label>
              作品标题
              <input
                name="title"
                required={source === 'paste'}
                maxLength={150}
                placeholder="例如：雨停之前"
              />
            </label>
            <label>
              粘贴自己的原文
              <textarea
                name="passage"
                required={source === 'paste'}
                rows={6}
                placeholder="一段就够。想分成两段时，请另起一行。"
              />
            </label>
          </div>
          <div hidden={source !== 'file'}>
            <label>
              原文 TXT 文件
              <input
                type="file"
                name="file"
                onChange={resetRights}
                required={source === 'file'}
                accept=".txt,text/plain"
              />
            </label>
            <label>
              TXT 编码
              <select name="encoding" defaultValue="auto">
                <option value="auto">自动识别（优先 UTF-8）</option>
                <option value="utf-8">UTF-8</option>
                <option value="gb18030">GB18030 / GBK</option>
              </select>
            </label>
          </div>
          <label>
            原文权利状态
            <select name="rights_status" ref={rightsRef} required defaultValue="">
              <option value="" disabled>
                请选择
              </option>
              <option value="owned">自有作品</option>
              <option value="authorized">已获授权</option>
              <option value="public_domain">公有领域</option>
              <option value="local_test">仅本地测试</option>
            </select>
          </label>
          <p className="asset-helper">
            最多 30,000 字。TXT 保留原文件；粘贴的文字按 UTF-8 保存。若想加动效，放图前需有至少 8
            个非空白字的同段原文可作依据；更短也能做静图。
          </p>
          {(hint || create.error) && (
            <p className="error" role="alert">
              {hint || create.error?.message}
            </p>
          )}
          <div className="studio-buttons">
            <button className="primary">
              {create.isPending ? '正在新建…' : '新建项目，选择插图 →'}
            </button>
            <button type="submit" value="voice">
              新建项目，先配朗读 →
            </button>
            <button className="text-button" type="submit" value="sound">
              新建项目，先编声景 →
            </button>
            <button className="text-button" type="submit" value="finish">
              只保留原文，直接试读与导出 →
            </button>
          </div>
        </fieldset>
      </form>
    </section>
  )
}

function ArtStep({
  project,
  data,
  onPlaced,
  onWriting,
}: {
  project: Project
  data: ReaderState
  onPlaced: () => void
  onWriting: (v: boolean) => void
}) {
  const cache = useQueryClient()
  const prefix = '/api/projects/' + project.id + '/reader'
  const [selected, setSelected] = useState('')
  const [loaded, setLoaded] = useState('')
  const [broken, setBroken] = useState('')
  const [title, setTitle] = useState(
    () => [...project.filename.replace(/\.txt$/i, '')].slice(0, 60).join('') + ' · 插图',
  )
  const [description, setDescription] = useState('')
  const [after, setAfter] = useState('')
  const [busy, setBusy] = useState(false)
  const [dirtyFile, setDirtyFile] = useState(false)
  const [dirtyPlacement, setDirtyPlacement] = useState(false)
  const [message, setMessage] = useState('')
  const [failure, setFailure] = useState('')
  const lock = useRef(false)
  const uploadForm = useRef<HTMLFormElement>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  useUnsavedWarning(busy || dirtyFile || dirtyPlacement)
  const assets = data.assets.filter((a) => a.kind === 'scene' && a.status !== 'rejected')
  const asset =
    assets.find((a) => a.id === selected) || (assets.length === 1 ? assets[0] : undefined)
  const imgKey = asset ? asset.id + ':' + asset.sha256 : ''
  const seen = !!asset && loaded === imgKey && broken !== imgKey
  const occupied = new Set(data.config.illustrations?.map((p) => p.after_byte))
  const paragraph = data.paragraphs.find(
    (p) => after && p.byte_end === Number(after) && !occupied.has(p.byte_end),
  )
  const alreadyPlaced = data.config.illustrations?.some((p) => p.id === firstPlate)
  async function run(action: () => Promise<void>, afterSave?: () => void) {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    onWriting(true)
    setFailure('')
    setMessage('')
    let saved = false
    try {
      await action()
      saved = true
    } catch (e) {
      if (mounted.current) setFailure(e instanceof Error ? e.message : '操作未完成。')
    } finally {
      try {
        await cache.invalidateQueries({ queryKey: ['reader', project.id] })
      } finally {
        lock.current = false
        if (mounted.current) {
          setBusy(false)
          onWriting(false)
          if (saved) afterSave?.()
        }
      }
    }
  }
  function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    const file = form.get('file')
    if (!(file instanceof File) || !file.size || file.size > 12_000_000) {
      setFailure('请选择一张非空图片，文件不超过 12 MB。')
      return
    }
    form.set('kind', 'scene')
    form.set('revision', String(data.revision))
    void run(async () => {
      const candidate = await api<ReaderAsset>(prefix + '/assets', { method: 'POST', body: form })
      if (!mounted.current) return
      setSelected(candidate.id)
      setDirtyFile(false)
      uploadForm.current?.reset()
      setMessage('候选图已存入项目，请查看实际图片后决定是否接受。')
    })
  }
  function accept() {
    if (!asset || !seen || asset.status !== 'pending') return
    void run(async () => {
      await api(prefix + '/assets/' + asset.id, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision: data.revision, status: 'accepted' }),
      })
      if (mounted.current) setMessage('这张底图已接受；还未放入原文，也没有已复核的动效。')
    })
  }
  function place(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (
      !asset ||
      !seen ||
      asset.status !== 'accepted' ||
      !paragraph ||
      !title.trim() ||
      dirtyFile ||
      data.config.illustrations?.some((p) => p.id === firstPlate)
    )
      return
    const illustration = {
      id: firstPlate,
      after_byte: paragraph.byte_end,
      image_asset_id: asset.id,
      title: title.trim(),
      description: description.trim(),
      motion: null,
    }
    void run(async () => {
      await api(prefix, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...data.config,
          revision: data.revision,
          reading_layout: 'illustrated',
          illustrations: [...(data.config.illustrations || []), illustration].sort(
            (a, b) => a.after_byte - b.after_byte,
          ),
        }),
      })
      if (mounted.current) setDirtyPlacement(false)
    }, onPlaced)
  }
  return (
    <section className="studio-card" aria-labelledby="studio-art-title">
      <p className="guided-kicker">02 / 底图与落点</p>
      <h2 id="studio-art-title">把插图放进原文</h2>
      <p>先上传候选图。看过实际底图、接受它并选定段落后，才把它作为静图放入阅读器。</p>
      {alreadyPlaced && !busy && (
        <p role="status">
          此插图已在另一个页面放置，本页输入未丢弃。
          <button
            onClick={() => {
              if (
                (!dirtyFile && !dirtyPlacement) ||
                window.confirm('放弃本页未保存的输入，打开已经放置的插图？')
              )
                onPlaced()
            }}
          >
            打开已放置的插图
          </button>
        </p>
      )}
      <fieldset disabled={busy || alreadyPlaced} className="studio-fields">
        <details
          className="studio-upload"
          open={!assets.length || undefined}
          key={assets.length ? 'has-assets' : 'empty'}
        >
          <summary>{assets.length ? '换一张：上传其他候选图' : '上传自己的插图'}</summary>
          <form ref={uploadForm} onSubmit={upload} onChange={() => setDirtyFile(true)}>
            <label>
              插图文件
              <input type="file" required name="file" accept="image/png,image/jpeg,image/webp" />
            </label>
            <p className="asset-helper">PNG、JPEG 或 WebP；最长边 4096 像素，文件最多 12 MB。</p>
            <label>
              图片来源与许可
              <input
                name="license_text"
                required
                maxLength={1000}
                placeholder="例如：本人绘制，允许用于此作品"
              />
            </label>
            <div className="studio-buttons">
              <button type="submit">上传为候选图</button>
              {dirtyFile && (
                <button
                  type="button"
                  onClick={() => {
                    uploadForm.current?.reset()
                    setDirtyFile(false)
                  }}
                >
                  放弃未上传的选择
                </button>
              )}
            </div>
          </form>
        </details>
        {assets.length > 1 && (
          <label>
            选择候选插图
            <select value={asset?.id || ''} onChange={(e) => setSelected(e.target.value)}>
              <option value="">选择要查看的图片</option>
              {assets.map((a, i) => (
                <option key={a.id} value={a.id}>
                  候选 {i + 1} · {a.width} × {a.height} · {a.license.slice(0, 60)}
                </option>
              ))}
            </select>
          </label>
        )}
        {asset && (
          <div className="studio-art-review">
            <figure>
              <img
                key={imgKey}
                src={asset.url}
                alt="待核对的项目底图"
                onLoad={() => {
                  setLoaded(imgKey)
                  setBroken('')
                }}
                onError={() => {
                  setLoaded('')
                  setBroken(imgKey)
                }}
              />
              <figcaption>
                {asset.width} × {asset.height} · {asset.license}
              </figcaption>
            </figure>
            {broken === imgKey && (
              <p role="alert" className="error">
                底图无法显示，不能接受或放置。请检查文件后重新上传。
              </p>
            )}
            <p>
              {asset.status === 'accepted' ? '✓ 底图已接受' : '候选图，尚未接受'}
              。底图接受和动效复核是两次不同的决定。
            </p>
            {asset.status !== 'accepted' && (
              <button type="button" disabled={!seen} onClick={accept}>
                接受这张底图
              </button>
            )}
            <form onSubmit={place} onChange={() => setDirtyPlacement(true)}>
              <label>
                插图名称
                <input
                  required
                  maxLength={80}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label>
                插图替代文字（可选）
                <textarea
                  rows={2}
                  maxLength={300}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="为看不到画面的读者描述图中实际可见的内容，不提前透露后文。"
                />
              </label>
              <label>
                放在此段之后
                <select required value={after} onChange={(e) => setAfter(e.target.value)}>
                  <option value="">选择一个原文段落</option>
                  {data.paragraphs.map((p, i) => (
                    <option key={p.byte_end} value={p.byte_end} disabled={occupied.has(p.byte_end)}>
                      第 {i + 1} 段 · {p.preview}
                      {occupied.has(p.byte_end) ? '（已有插图）' : ''}
                    </option>
                  ))}
                </select>
              </label>
              {paragraph && <blockquote>{paragraph.text}</blockquote>}
              {dirtyFile && <p className="asset-helper">还有未上传的选择，请先完成或放弃上传。</p>}
              <button
                className="primary"
                disabled={
                  !seen || asset.status !== 'accepted' || !paragraph || !title.trim() || dirtyFile
                }
              >
                放置静图，进入动效导演 →
              </button>
            </form>
          </div>
        )}
      </fieldset>
      {busy && <p role="status">正在保存到本机…</p>}
      {message && <p role="status">{message}</p>}
      {failure && (
        <p role="alert" className="error">
          {failure} 已保存的项目和素材仍在。
        </p>
      )}
    </section>
  )
}

function StudioProject({ project }: { project: Project }) {
  const reader = useQuery({
    queryKey: ['reader', project.id],
    queryFn: () => api<ReaderState>('/api/projects/' + project.id + '/reader'),
  })
  return (
    <>
      <div className="studio-project">
        <p className="guided-kicker">SINGLE-PLATE STUDIO / 单幅图文制作</p>
        <h1>{project.filename.replace(/\.txt$/i, '')}</h1>
        <p>
          原文已保存 · {project.character_count.toLocaleString()} 字 ·{' '}
          <a href={'/api/projects/' + project.id + '/source'}>下载原文</a>
        </p>
      </div>
      {reader.error && (
        <p role="alert" className="error">
          {reader.error.message} <button onClick={() => reader.refetch()}>重试</button>
        </p>
      )}
      {reader.isPending && <p role="status">正在读取项目…</p>}
      {reader.data && <StudioSteps project={project} data={reader.data} />}
    </>
  )
}

function StudioSteps({ project, data }: { project: Project; data: ReaderState }) {
  // Only our successful placement (or an explicit join) changes the active
  // step. A late cross-tab refetch cannot tear down the user's local draft.
  const [placed, setPlaced] = useState(
    () => !!data.config.illustrations?.some((p) => p.id === firstPlate),
  )
  type Lane = 'resolve' | StartLane | 'director'
  const [lane, setLane] = useState<Lane>(() => {
    const route = new URLSearchParams(location.search).get('lane')
    return placed
      ? 'director'
      : route === 'voice' || route === 'art' || route === 'sound' || route === 'finish'
        ? route
        : 'resolve'
  })
  const [hasVisited, setHasVisited] = useState(lane !== 'art' && lane !== 'resolve')
  const [writing, setWriting] = useState(false)
  // Resume sound-only work even after an editable project travels to a different browser.
  // Resolve once, before showing editable forms. Never switch away after a later refetch.
  const savedVoice = useQuery({
    queryKey: ['narrations', project.id],
    queryFn: () => api<Narrations>(voiceUrl(project.id)),
    enabled: lane === 'resolve',
  })
  const savedSounds = useQuery({
    queryKey: ['soundscapes', project.id],
    queryFn: () => api<Soundscapes>(soundUrl(project.id)),
    enabled: lane === 'resolve',
  })
  useEffect(() => {
    if (
      lane !== 'resolve' ||
      (!savedVoice.data && !savedVoice.isError) ||
      (!savedSounds.data && !savedSounds.isError)
    )
      return
    const next = savedVoice.data?.takes.length
      ? 'voice'
      : savedSounds.data?.takes.length
        ? 'sound'
        : data.config.echo_fold || data.config.illustrations?.length
          ? 'finish'
          : 'art'
    setLane(next)
    if (next !== 'art') setHasVisited(true)
  }, [
    lane,
    savedVoice.data,
    savedVoice.isError,
    savedSounds.data,
    savedSounds.isError,
    data.config.echo_fold,
    data.config.illustrations,
  ])
  const heading = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (lane !== 'art' && lane !== 'resolve') heading.current?.focus()
  }, [lane])
  function visit(next: Exclude<Lane, 'resolve'>) {
    history.replaceState(
      null,
      '',
      studioUrl(project.id) + (next === 'director' ? '' : '&lane=' + next),
    )
    setLane(next)
    if (next !== 'art') setHasVisited(true)
  }
  if (lane === 'resolve') return <p role="status">正在读取已保存的制作进度…</p>
  return (
    <div tabIndex={-1} ref={heading}>
      {!placed && (
        <nav className="studio-lane" aria-label="制作方式">
          {lane === 'art' ? (
            <>
              <button type="button" disabled={writing} onClick={() => visit('voice')}>
                先配一段朗读，不加插图 →
              </button>
              <button type="button" disabled={writing} onClick={() => visit('sound')}>
                先编一段声景，不加插图 →
              </button>
            </>
          ) : (
            <button type="button" disabled={writing} onClick={() => visit('art')}>
              添加插图或返回底图制作 →
            </button>
          )}
          {lane === 'art' && (
            <button type="button" disabled={writing} onClick={() => visit('finish')}>
              不加素材，直接试读与导出 →
            </button>
          )}
          <small>可随时换一种做法，已保存的作品仍在。</small>
        </nav>
      )}
      {!placed && (
        <div hidden={lane !== 'art'}>
          <ArtStep
            project={project}
            data={data}
            onWriting={setWriting}
            onPlaced={() => {
              setPlaced(true)
              visit('director')
            }}
          />
        </div>
      )}
      {hasVisited && (
        <div hidden={lane === 'art'}>
          <ReaderPanel
            projectId={project.id}
            studioPlateId={placed ? firstPlate : undefined}
            voiceOnly={!placed}
            soundFirst={lane === 'sound'}
            finishOnly={lane === 'finish'}
            studioActive={lane !== 'art'}
            onVoiceWriting={setWriting}
          />
        </div>
      )}
    </div>
  )
}

export function CreatorStudio({ initialId }: { initialId: string }) {
  const cache = useQueryClient()
  const [id, setId] = useState(initialId)
  const valid = studioId.test(id)
  const project = useQuery({
    queryKey: ['project', id],
    queryFn: () => api<Project>('/api/projects/' + id),
    enabled: valid,
  })
  function created(p: Project, lane: StartLane) {
    cache.setQueryData(['project', p.id], p)
    // Keep one history entry and do not move an open workbench off its previous
    // project. Returning here or reloading resumes the same saved project.
    history.replaceState(null, '', studioUrl(p.id) + (lane === 'art' ? '' : '&lane=' + lane))
    setId(p.id)
  }
  return (
    <div className="creator-workbench studio-shell">
      <header className="masthead">
        <a className="brand" href="/">
          <b>
            Taleprism<span className="brand-dot">.</span>
          </b>
          <span>VISUAL STORIES</span>
        </a>
        <a
          className="studio-return"
          href={valid && project.data?.single_plate_studio ? '/?project=' + id : '/'}
        >
          返回完整工作台
        </a>
      </header>
      <main className="studio-page">
        {id === 'new' ? (
          <>
            <div className="studio-project">
              <p className="guided-kicker">SINGLE-PLATE STUDIO / 单幅图文制作</p>
              <h1>你的文字，自己的声音与画。</h1>
              <p>
                原文按段保留。朗读、环境声和插图任选；不需要其他素材就能开始制作、试读和导出。全程在本机完成。
              </p>
            </div>
            <SourceStep onCreated={created} />
          </>
        ) : valid && project.data?.single_plate_studio ? (
          <StudioProject key={id} project={project.data} />
        ) : valid && project.isPending ? (
          <p role="status">正在载入作品…</p>
        ) : (
          <section>
            <p role="alert">
              {project.error?.message || '这不是通过单幅图文入口建立的项目，未作任何修改。'}
            </p>
            <a href={studioUrl('new')}>从新项目开始</a>
          </section>
        )}
      </main>
    </div>
  )
}
