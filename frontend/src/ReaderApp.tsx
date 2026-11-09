import {
  lazy,
  Fragment,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type CSSProperties,
} from 'react'
import { ReaderMap } from './ReaderMap'
import type { ReaderContent, ReaderMapEntry } from './reader-types'
import {
  blockAt,
  highlightedRuns,
  navigationReducer,
  normalizeContent,
  quoteAt,
  readRecord,
  search,
  type Mark,
  type Position,
  type RecordData,
  validPosition,
  byteLength,
} from './reader/model'
import { capturePosition, restorePosition, selectedExcerpt } from './reader/position'
import { useDialogueAudio, type AudioPoint } from './reader/useDialogueAudio'
import { useStagePreload } from './reader/useStagePreload'
import { ReaderPlate } from './reader/ReaderPlate'
import './reader.css'

const EditorialPreview = lazy(() => import('./reader/EditorialPreview'))

type Panel =
  | 'contents'
  | 'map'
  | 'settings'
  | 'about'
  | 'search'
  | 'marks'
  | 'voices'
  | 'image'
  | 'restart'
  | 'gallery'
  | null
type Screen = {
  session: string
  depth: number
  started: boolean
  panel: Panel
  view: Position
  visits: Position[]
  sound: AudioPoint
}
export function ReaderApp({ projectId, exportUrl }: { projectId?: string; exportUrl?: string }) {
  const [data, setData] = useState<ReaderContent | null>(null),
    [error, setError] = useState(''),
    [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError('')
    fetch(exportUrl || `/api/projects/${projectId}/reader/content`, { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}))
          throw Error(body.detail || '阅读内容暂时无法打开。')
        }
        return r.json()
      })
      .then((d) => setData(normalizeContent(d)))
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => controller.abort()
  }, [projectId, exportUrl, attempt])
  if (!data)
    return (
      <div className="reader-root reader-loading">
        <p role={error ? 'alert' : 'status'}>{error || '正在展开这一卷…'}</p>
        {error && <button onClick={() => setAttempt((v) => v + 1)}>重新打开</button>}
        <a href="/">返回 Taleprism</a>
      </div>
    )
  return <ReaderView key={data.project.id} data={data} standalone={!!exportUrl} />
}
function ReaderView({ data, standalone }: { data: ReaderContent; standalone: boolean }) {
  const storageKey = `storygal-reader:${data.project.id}:${data.project.canonical_sha256}`
  const editing = !standalone && new URLSearchParams(location.search).get('editing') === '1'
  const previewApplied = useRef(false)
  const [saved] = useState(() => {
    try {
      return readRecord(data, localStorage.getItem(storageKey))
    } catch {
      return readRecord(data, null)
    }
  })
  const [nav, dispatch] = useReducer(navigationReducer, {
    view: saved.resume,
    resume: saved.resume,
    furthest: saved.furthest,
    visits: [],
  })
  const navRef = useRef(nav)
  navRef.current = nav
  const [preferences, setPreferences] = useState(saved.preferences),
    [marks, setMarks] = useState<Mark[]>(saved.marks),
    [completed, setCompleted] = useState(saved.completed)
  const [started, setStarted] = useState(false),
    [panel, setPanel] = useState<Panel>(null),
    [notice, setNotice] = useState(''),
    [storageError, setStorageError] = useState(false)
  const [externalRecord, setExternalRecord] = useState<string | null>(null),
    conflict = useRef(false)
  const [tools, setTools] = useState(true),
    [query, setQuery] = useState(''),
    [selection, setSelection] = useState<ReturnType<typeof selectedExcerpt>>(null)
  const [failedImages, setFailedImages] = useState<string[]>([]),
    [mapEntry, setMapEntry] = useState<ReaderMapEntry | null>(null)
  const [viewerAsset, setViewerAsset] = useState<string | null>(null)
  const [viewerZoom, setViewerZoom] = useState(false)
  const imageViewport = useRef<HTMLDivElement>(null)
  useEffect(() => {
    setViewerZoom(false)
    imageViewport.current?.scrollTo(0, 0)
  }, [viewerAsset])
  const scroll = useRef<HTMLDivElement>(null),
    dialog = useRef<HTMLDialogElement>(null),
    opener = useRef<HTMLElement | null>(null)
  const audio = useDialogueAudio(data),
    audioRef = useRef(audio)
  audioRef.current = audio
  const screen = useRef<Screen>({
    session: crypto.randomUUID(),
    depth: 0,
    started: false,
    panel: null as Panel,
    view: saved.resume,
    visits: [] as Position[],
    sound: null as AudioPoint,
  })
  const layoutLocked = useRef(false)
  const freeze = useRef(0),
    raf = useRef(0),
    settle = useRef<ReturnType<typeof setTimeout> | null>(null),
    previousY = useRef(0)
  const record = useRef<RecordData>({ ...saved })
  record.current = {
    version: 2,
    resume: nav.resume,
    furthest: nav.furthest,
    preferences,
    marks,
    completed,
    updated: record.current.updated,
  }
  const media = (id?: string | null) => (id && !failedImages.includes(id) ? data.media[id] : null)
  const failed = (id: string) => setFailedImages((v) => [...new Set([...v, id])])
  const at = nav.view.byte,
    scene = data.config.scenes.filter((s) => s.start_byte <= at).at(-1)
  const presentation = data.presentations.filter((p) => p.start_byte <= at).at(-1)
  const illustrated = preferences.layout === 'illustrated'
  const plates = data.config.illustrations || []
  const expandedImage = media(viewerAsset) || media(presentation?.image_asset_id)
  const expandedPlate = plates.find((p) => p.image_asset_id === expandedImage?.id)
  useStagePreload(data, presentation?.id, started && preferences.stage && !illustrated)
  const active = blockAt(data.blocks, at),
    cover = media(data.config.cover_asset_id),
    image = media(presentation?.image_asset_id)
  const clip = data.blocks.flatMap((b) => b.audio).find((c) => c.take_id === audio.current)
  const progress = Math.min(
    100,
    Math.round(
      ((at - data.blocks[0].byte_start) /
        Math.max(1, data.blocks.at(-1)!.byte_end - data.blocks[0].byte_start)) *
        100,
    ),
  )
  const results = useMemo(() => search(data, query), [data, query])
  const voices = data.blocks.flatMap((b) =>
    b.audio.map((a, i) => ({ block: b, clip: a, index: i })),
  )
  const voiceGroups = voices.reduce<
    { block: (typeof data.blocks)[number]; clips: (typeof data.blocks)[number]['audio'] }[]
  >((groups, v) => {
    const last = groups.at(-1),
      previous = last?.clips.at(-1)
    if (
      last?.block.id === v.block.id &&
      previous?.speaker_id === v.clip.speaker_id &&
      previous.byte_end === v.clip.byte_start
    )
      last.clips.push(v.clip)
    else groups.push({ block: v.block, clips: [v.clip] })
    return groups
  }, [])

  const persist = useCallback(() => {
    if (conflict.current) return
    try {
      const value = { ...record.current, updated: Date.now() }
      localStorage.setItem(storageKey, JSON.stringify(value))
      record.current.updated = value.updated
      setStorageError(false)
    } catch {
      setStorageError(true)
    }
  }, [storageKey])
  useEffect(() => {
    if (!notice) return
    const id = setTimeout(() => setNotice(''), 2400)
    return () => clearTimeout(id)
  }, [notice])
  useEffect(() => {
    const id = setTimeout(persist, 200)
    return () => clearTimeout(id)
  }, [nav.resume, nav.furthest, preferences, marks, completed, persist])
  useEffect(() => {
    const leave = () => persist()
    const storage = (event: StorageEvent) => {
      if (event.key === storageKey && event.newValue) {
        conflict.current = true
        setExternalRecord(event.newValue)
      }
    }
    window.addEventListener('pagehide', leave)
    window.addEventListener('storage', storage)
    return () => {
      window.removeEventListener('pagehide', leave)
      window.removeEventListener('storage', storage)
    }
  }, [storageKey, persist])
  const locate = useCallback((position: Position, focus = true) => {
    freeze.current = performance.now() + 300
    requestAnimationFrame(() => {
      if (scroll.current) {
        restorePosition(scroll.current, position, focus)
        previousY.current = scroll.current.scrollTop
      }
    })
  }, [])
  function snapshot(): Screen {
    return {
      ...screen.current,
      started,
      panel,
      view: navRef.current.view,
      visits: navRef.current.visits,
      sound: audio.point(),
    }
  }
  function commit(next: Screen, replace = false) {
    screen.current = next
    if (replace) history.replaceState({ storygal: next }, '', location.href)
    else history.pushState({ storygal: next }, '', location.href)
  }
  function remember() {
    const s = snapshot()
    screen.current = s
    history.replaceState({ storygal: s }, '', location.href)
    return s
  }
  useEffect(() => {
    history.replaceState({ storygal: screen.current }, '', location.href)
    const pop = (event: PopStateEvent) => {
      const s = event.state?.storygal as Screen | undefined
      if (!s || s.session !== screen.current.session) return
      audioRef.current.restore(s.sound)
      screen.current = s
      setStarted(s.started)
      setPanel(s.panel)
      dispatch({ type: 'restore', position: s.view, visits: s.visits })
      locate(s.view, !s.panel)
    }
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [locate])
  useEffect(() => {
    const param = new URLSearchParams(location.search).get('at')
    if (!previewApplied.current && param && Number.isFinite(Number(param))) {
      previewApplied.current = true
      const position = validPosition(data, { byte: Number(param), offset: 0 })
      dispatch({ type: 'visit', position })
      setStarted(true)
      locate(position, false)
    }
  }, [locate])
  useEffect(() => {
    const previous = document.title
    document.title = `${data.config.title} · Taleprism`
    return () => {
      document.title = previous
    }
  }, [data.config.title])
  useLayoutEffect(() => {
    if (started) locate(navRef.current.view, false)
  }, [started, preferences, locate])
  useEffect(() => {
    const root = scroll.current
    if (!started || !root) return
    let width = root.clientWidth,
      height = root.clientHeight
    const observer = new ResizeObserver(() => {
      if (root.clientWidth === width && root.clientHeight === height) return
      width = root.clientWidth
      height = root.clientHeight
      layoutLocked.current = true
      cancelAnimationFrame(raf.current)
      locate(navRef.current.view, false)
    })
    const resizing = () => {
      layoutLocked.current = true
      cancelAnimationFrame(raf.current)
      locate(navRef.current.view, false)
    }
    observer.observe(root)
    window.addEventListener('resize', resizing)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', resizing)
    }
  }, [started, locate])
  useEffect(() => {
    const d = dialog.current
    if (panel && !d?.open) d?.showModal()
    if (panel) d?.querySelector<HTMLElement>('#reader-panel-title')?.focus()
    if (!panel && d?.open) {
      d.close()
      if (opener.current?.isConnected) opener.current.focus({ preventScroll: true })
      else scroll.current?.focus({ preventScroll: true })
    }
  }, [panel])
  useEffect(
    () => () => {
      cancelAnimationFrame(raf.current)
      if (settle.current) clearTimeout(settle.current)
    },
    [],
  )
  function open(next: Exclude<Panel, null>) {
    opener.current = document.activeElement as HTMLElement
    const old = remember()
    audio.suspend()
    commit({ ...old, depth: old.depth + 1, panel: next })
    setPanel(next)
  }
  function close() {
    if (screen.current.panel && screen.current.depth > 0) history.back()
    else setPanel(null)
  }
  function visit(byte: number) {
    const old = remember(),
      position = { byte, offset: 0 },
      visits = [...nav.visits, nav.view]
    audio.suspend()
    dispatch({ type: 'visit', position })
    setPanel(null)
    commit(
      {
        ...old,
        depth: panel ? old.depth : old.depth + 1,
        panel: null,
        view: position,
        visits,
        sound: null,
      },
      !!panel,
    )
    locate(position)
  }
  function returnMain() {
    const old = remember(),
      position = nav.resume
    audio.suspend()
    dispatch({ type: 'restore', position, visits: [] })
    setPanel(null)
    commit({ ...old, depth: old.depth + 1, panel: null, view: position, visits: [], sound: null })
    locate(position)
  }
  function continueHere() {
    dispatch({ type: 'continue' })
    const s = snapshot()
    commit({ ...s, visits: [] }, true)
    audio.suspend()
  }
  function start(fresh = false) {
    const position = fresh ? { byte: data.blocks[0].byte_start, offset: 0 } : nav.resume
    const old = remember()
    audio.stop()
    audio.setAutomatic(false)
    if (fresh) {
      dispatch({ type: 'restart', position })
      setCompleted(false)
    } else dispatch({ type: 'restore', position, visits: [] })
    const s = {
      ...old,
      started: true,
      depth: old.depth + 1,
      panel: null,
      view: position,
      visits: [],
      sound: null,
    }
    // Preserve the furthest location on continue; start-over intentionally resets the reading session.
    if (!fresh) dispatch({ type: 'scroll', position })
    commit(s, panel === 'restart')
    setPanel(null)
    setStarted(true)
    locate(position)
  }
  function trackScroll() {
    cancelAnimationFrame(raf.current)
    raf.current = requestAnimationFrame(() => {
      const root = scroll.current
      if (!root || panel || layoutLocked.current || performance.now() < freeze.current) return
      const before = navRef.current.view.byte,
        position = capturePosition(root)
      const slow = Math.abs(root.scrollTop - previousY.current) < root.clientHeight * 0.7
      previousY.current = root.scrollTop
      dispatch({ type: 'scroll', position })
      audio.leave(position.byte)
      if (settle.current) clearTimeout(settle.current)
      if (!navRef.current.visits.length && slow && position.byte > before)
        settle.current = setTimeout(() => {
          if (
            !screen.current.panel &&
            !navRef.current.visits.length &&
            performance.now() >= freeze.current
          )
            audioRef.current.autoAt(before, position.byte)
        }, 220)
    })
  }
  function bookmark() {
    if (marks.some((m) => !m.ranges && m.position.byte === at)) {
      setNotice('这里已经有书签。')
      return
    }
    setMarks((v) => [
      ...v,
      { id: crypto.randomUUID(), position: nav.view, text: quoteAt(data, at) },
    ])
    setNotice('书签已保存。')
  }
  function excerpt() {
    if (!selection) return
    setMarks((v) => [...v, { id: crypto.randomUUID(), ...selection }])
    setSelection(null)
    window.getSelection()?.removeAllRanges()
    setNotice('原文摘录已保存。')
  }
  function read(id: string, byte?: number) {
    if (byte !== undefined && (byte < active.byte_start || byte >= active.byte_end)) visit(byte)
    else if (panel) {
      const old = snapshot()
      commit({ ...old, panel: null }, true)
      setPanel(null)
    }
    audio.play(id)
  }
  function settings(update: Partial<typeof preferences>) {
    audio.suspend()
    setPreferences((v) => ({ ...v, ...update }))
  }
  const title = (
    {
      contents: '章节与场景',
      map: '赤壁战区地图',
      settings: '阅读设置',
      about: '本卷说明',
      search: '搜索原文',
      marks: '书签与摘录',
      voices: '本章对白',
      image: '查看画面',
      restart: '从头阅读',
      gallery: '本章画卷',
    } as const
  )[panel || 'about']
  return (
    <div
      className={`reader-root ${started ? 'is-reading' : 'is-cover'} ${preferences.stage ? '' : 'stage-collapsed'} ${illustrated ? 'is-illustrated' : ''} ${plates.length ? 'has-plates' : ''}`}
      data-view-byte={at}
      data-view-plate={nav.view.plate}
      data-resume-byte={nav.resume.byte}
      data-visiting={!!nav.visits.length}
    >
      <audio ref={audio.element} preload="metadata" onEnded={audio.ended} onError={audio.failed} />
      {!started ? (
        <section className="reader-cover" aria-label="章节封面">
          {cover && (
            <img
              className="reader-cover-art"
              src={cover.url}
              alt={`${data.config.title}章节封面`}
              onError={() => failed(cover.id)}
            />
          )}
          <div className="reader-cover-shade" />
          <header className="reader-cover-header">
            <span className="reader-wordmark">
              Taleprism<span>视觉小说</span>
            </span>
            {standalone && (
              <a
                href="https://github.com/Ethereal-Space-one/taleprism"
                target="_blank"
                rel="noreferrer"
              >
                用 Taleprism 制作 ↗
              </a>
            )}
            {!standalone && (
              <a
                href="/"
                onClick={() => {
                  try {
                    localStorage.setItem('storygal-project', data.project.id)
                  } catch {}
                }}
              >
                制作台 ↗
              </a>
            )}
          </header>
          <div className="reader-cover-copy">
            <p className="reader-cover-source">
              {data.config.map_profile === 'chibi'
                ? '三国演义 · 第四十九—五十回'
                : data.project.filename.replace(/\.txt$/i, '')}
            </p>
            <h1 className={data.config.title.length > 8 ? 'reader-long-title' : ''}>
              {data.config.title}
            </h1>
            <p className="reader-cover-subtitle">
              {data.config.subtitle || '以原文为卷，随文字入境。'}
            </p>
            {nav.resume.byte > data.blocks[0].byte_start && (
              <div className="reader-resume">
                <span>
                  上次读到 ·{' '}
                  {data.config.scenes.filter((s) => s.start_byte <= nav.resume.byte).at(-1)
                    ?.title || '原文'}
                </span>
                <p>{quoteAt(data, nav.resume.byte)}</p>
              </div>
            )}
            <div className="reader-cover-actions">
              <button className="reader-primary" onClick={() => start()}>
                {nav.resume.byte > data.blocks[0].byte_start ? '继续阅读' : '开始阅读'} →
              </button>
              {nav.resume.byte > data.blocks[0].byte_start && (
                <button onClick={() => open('restart')}>从头读起</button>
              )}
            </div>
            <p className="reader-cover-meta">
              {data.project.character_count.toLocaleString()} 字 · {data.config.scenes.length}{' '}
              个场景{!!plates.length && ` · ${plates.length} 幅叙事插图`}
              <span>原文完整保留</span>
            </p>
          </div>
          <button className="reader-cover-about" onClick={() => open('about')}>
            素材与说明
          </button>
        </section>
      ) : (
        <>
          <header className="reader-header">
            <button
              onClick={() => {
                const old = remember()
                audio.stop()
                audio.setAutomatic(false)
                commit({ ...old, depth: old.depth + 1, started: false })
                setStarted(false)
                persist()
              }}
            >
              ← 封面
            </button>
            <span>
              {data.config.title}
              <small>
                {(nav.view.plate && plates.find((p) => p.id === nav.view.plate)?.title) ||
                  presentation?.place_label ||
                  scene?.title ||
                  '原文阅读'}
                {audio.automatic ? ' · 自动对白已开' : ''}
              </small>
            </span>
            <button onClick={() => open('contents')} aria-label="打开章节目录">
              目录
            </button>
          </header>
          {!!nav.visits.length && (
            <div className="reader-visit" role="status">
              <span>临时查阅 · 续读位置已保留</span>
              <div>
                <button onClick={() => history.back()}>返回上一处</button>
                <button onClick={returnMain}>返回阅读处</button>
                <button onClick={continueHere}>从这里继续</button>
              </div>
            </div>
          )}
          {editing && (
            <Suspense fallback={null}>
              <EditorialPreview projectId={data.project.id} anchor={at} />
            </Suspense>
          )}
          <div className="reader-layout">
            {preferences.stage && !illustrated && (
              <aside
                className="reader-stage"
                aria-label="当前场景"
                data-scene-id={scene?.id || 'none'}
                data-presentation-id={presentation?.id}
              >
                {image && (
                  <img
                    key={image.id}
                    className="reader-background"
                    src={image.url}
                    alt={presentation?.place_label || scene?.title || '场景'}
                    onError={() => failed(image.id)}
                  />
                )}
                <div className="reader-stage-shade" />
                {!image && (
                  <div className="reader-stage-fallback">
                    <span>{data.config.title}</span>
                    <p>场景图片暂不可用，正文仍可阅读。</p>
                  </div>
                )}
                <div
                  className={`reader-portraits count-${presentation?.cast.length || 0} ${presentation?.cast.some((c) => data.media[c.figure_asset_id]?.portrait_state === 'ill-seated') ? 'has-seated' : ''}`}
                >
                  {presentation?.cast.map((member) => {
                    const c = data.characters[member.character_id],
                      figure = media(member.figure_asset_id)
                    return (
                      c &&
                      figure && (
                        <figure
                          key={member.slot}
                          data-slot={member.slot}
                          data-state={figure.portrait_state || 'base'}
                          className={
                            clip?.speaker_id === c.id && audio.status === 'playing'
                              ? 'is-speaking'
                              : ''
                          }
                        >
                          <img
                            src={figure.url}
                            alt={`${c.name}立绘`}
                            onError={() => failed(figure.id)}
                          />
                          <figcaption>{c.name}</figcaption>
                        </figure>
                      )
                    )
                  })}
                </div>
                <div className="reader-stage-caption">
                  <span>
                    {presentation?.place_label || scene?.title}
                    {presentation?.time_label && ` · ${presentation.time_label}`}
                  </span>
                  <button
                    aria-label="放大当前画面"
                    disabled={!image}
                    onClick={() => {
                      setViewerAsset(null)
                      open('image')
                    }}
                  >
                    放大
                  </button>
                </div>
              </aside>
            )}
            <div
              className="reader-scroll"
              ref={scroll}
              onScroll={trackScroll}
              onWheel={() => {
                layoutLocked.current = false
                freeze.current = 0
              }}
              onTouchMove={() => {
                layoutLocked.current = false
                freeze.current = 0
              }}
              onPointerDown={() => {
                layoutLocked.current = false
              }}
              onKeyDown={() => {
                layoutLocked.current = false
                freeze.current = 0
              }}
              onPointerUp={() => {
                if (scroll.current) setSelection(selectedExcerpt(scroll.current))
              }}
              onKeyUp={() => {
                if (scroll.current) setSelection(selectedExcerpt(scroll.current))
              }}
              tabIndex={0}
              aria-label="连续阅读正文"
              style={
                {
                  '--reader-size': `${preferences.size}px`,
                  '--reader-leading': preferences.leading,
                  '--reader-width': `${preferences.width}px`,
                } as CSSProperties
              }
            >
              <article className="reader-prose">
                {data.blocks.map((block) => (
                  <Fragment key={block.id}>
                    <section
                      className={`reader-paragraph ${block.heading ? 'reader-chapter' : ''} ${active.id === block.id ? 'is-current' : ''}`}
                      id={block.id}
                      key={block.id}
                      data-byte-start={block.byte_start}
                    >
                      {block.heading ? (
                        <h2 className="reader-paragraph-text">
                          {highlightedRuns(block, query).map((r) => (
                            <span
                              key={r.byte_start}
                              data-source-start={r.byte_start}
                              data-source-end={r.byte_end}
                            >
                              {r.text}
                            </span>
                          ))}
                        </h2>
                      ) : (
                        <p className="reader-paragraph-text">
                          {highlightedRuns(block, query).map((r) => (
                            <span
                              key={r.byte_start}
                              data-source-start={r.byte_start}
                              data-source-end={r.byte_end}
                              data-take={r.take_id || undefined}
                              className={
                                audio.current &&
                                audio.status === 'playing' &&
                                r.take_id === audio.current
                                  ? 'reader-spoken'
                                  : r.match
                                    ? 'reader-search-match'
                                    : ''
                              }
                            >
                              {r.text}
                            </span>
                          ))}
                        </p>
                      )}
                      {!!block.audio.length && (
                        <div className="reader-inline-audio">
                          {block.audio.map((a, i) => (
                            <button
                              key={a.take_id}
                              onClick={() => read(a.take_id)}
                              aria-label={`播放${data.characters[a.speaker_id]?.name || '对白'}第${i + 1}段`}
                            >
                              {data.characters[a.speaker_id]?.name} · 播放
                              {block.audio.length > 1 ? ` ${i + 1}` : ''} ▷
                            </button>
                          ))}
                        </div>
                      )}
                      {data.map_entries
                        .filter(
                          (e) => e.byte_start >= block.byte_start && e.byte_start < block.byte_end,
                        )
                        .map((e) => (
                          <div className="reader-inline-audio" key={e.id}>
                            <button
                              onClick={() => {
                                setMapEntry(e)
                                open('map')
                              }}
                            >
                              {e.label} ↗
                            </button>
                          </div>
                        ))}
                    </section>
                    {illustrated &&
                      preferences.stage &&
                      plates
                        .filter((p) => p.after_byte === block.byte_end)
                        .map((p) => (
                          <ReaderPlate
                            key={p.id}
                            plate={p}
                            asset={data.media[p.image_asset_id]}
                            sourceByte={block.byte_end - byteLength([...block.text].at(-1)!)}
                            failed={failedImages.includes(p.image_asset_id)}
                            onError={() => failed(p.image_asset_id)}
                            onOpen={() => {
                              setViewerAsset(p.image_asset_id)
                              open('image')
                            }}
                          />
                        ))}
                  </Fragment>
                ))}
                <footer className="reader-end">
                  <h2>已到本卷结尾。</h2>
                  <p>抵达结尾不代表已经通读。你可以回看，也可以标记本轮阅读完成。</p>
                  <button aria-pressed={completed} onClick={() => setCompleted((v) => !v)}>
                    {completed ? '本轮已完成 · 撤销' : '标记本轮阅读完成'}
                  </button>
                  <div className="reader-end-actions">
                    <button onClick={() => open('contents')}>回顾场景</button>
                    {voices.length > 0 && <button onClick={() => open('voices')}>重听对白</button>}
                    {data.map && (
                      <button
                        onClick={() => {
                          setMapEntry(null)
                          open('map')
                        }}
                      >
                        回顾地图
                      </button>
                    )}
                  </div>
                </footer>
              </article>
            </div>
          </div>
          {audio.current && (
            <div className="reader-playback" aria-label="对白播放器">
              <span>
                {data.characters[clip?.speaker_id || '']?.name || '对白'} ·{' '}
                {audio.status === 'playing'
                  ? '播放中'
                  : audio.status === 'failed'
                    ? '播放失败'
                    : '已暂停'}
              </span>
              <button onClick={audio.status === 'playing' ? audio.suspend : audio.resume}>
                {audio.status === 'playing' ? '暂停' : '继续播放'}
              </button>
              <button onClick={() => audio.current && audio.play(audio.current)}>重听</button>
              <button onClick={audio.stop}>停止</button>
            </div>
          )}
          <nav className="reader-toolbar" aria-label="阅读工具">
            <div className="reader-tool-pill">
              <span className="reader-progress" aria-label={`当前位置 ${progress}%`}>
                {progress}%
              </span>
              {tools && (
                <>
                  <button onClick={() => open('search')}>搜索</button>
                  <button onClick={() => open('marks')}>收藏</button>
                </>
              )}
              {data.map && (
                <button
                  onClick={() => {
                    setMapEntry(null)
                    open('map')
                  }}
                >
                  地图
                </button>
              )}
              <button onClick={() => setTools((v) => !v)} aria-expanded={tools}>
                {tools ? '收起' : '工具'}
              </button>
              <button onClick={() => open('settings')}>设置</button>
            </div>
          </nav>
        </>
      )}
      {(notice || audio.notice || storageError || externalRecord) && (
        <div className="reader-notice" role="status">
          <span>
            {externalRecord
              ? '另一窗口保存了阅读记录。当前阅读位置保持不变。'
              : storageError
                ? '本机存储不可用，本次阅读记录暂不能保存。'
                : notice || audio.notice}
          </span>
          {externalRecord && (
            <>
              <button
                onClick={() => {
                  const r = readRecord(data, externalRecord)
                  conflict.current = false
                  setExternalRecord(null)
                  dispatch({ type: 'restart', position: r.resume })
                  setPreferences(r.preferences)
                  setMarks(r.marks)
                  setCompleted(r.completed)
                  locate(r.resume)
                  audio.stop()
                }}
              >
                采用记录
              </button>
              <button
                onClick={() => {
                  conflict.current = false
                  setExternalRecord(null)
                  persist()
                }}
              >
                保留本窗口
              </button>
            </>
          )}
          <button
            aria-label="关闭提示"
            onClick={() => {
              setNotice('')
              audio.setNotice('')
            }}
          >
            ×
          </button>
        </div>
      )}
      {selection && started && (
        <div className="reader-selection">
          <button onPointerDown={(e) => e.preventDefault()} onClick={excerpt}>
            保存原文摘录
          </button>
          <button onClick={() => setSelection(null)}>取消</button>
        </div>
      )}
      <dialog
        ref={dialog}
        className={`reader-dialog ${panel === 'map' ? 'reader-map-dialog' : ''} ${panel === 'image' || panel === 'gallery' ? 'reader-art-dialog' : ''}`}
        onCancel={(e) => {
          e.preventDefault()
          close()
        }}
        onClick={(e) => {
          if (e.target === e.currentTarget) close()
        }}
        aria-labelledby="reader-panel-title"
      >
        <div className="reader-dialog-head">
          <h2 id="reader-panel-title" tabIndex={-1}>
            {title}
          </h2>
          <button onClick={close} aria-label="关闭面板">
            ×
          </button>
        </div>
        <div className="reader-dialog-body">
          {panel === 'restart' && (
            <>
              <p>将从卷首开始新的阅读，保留书签、摘录和显示偏好。</p>
              <button onClick={() => start(true)}>确认从头阅读</button>
              <button onClick={close}>取消</button>
            </>
          )}
          {panel === 'map' && data.map && (
            <ReaderMap key={mapEntry?.id || at} data={data.map} at={at} entry={mapEntry} />
          )}
          {panel === 'image' && expandedImage && (
            <>
              <div
                ref={imageViewport}
                className={`reader-image-viewport ${viewerZoom ? 'is-zoomed' : ''}`}
                tabIndex={0}
                aria-label="插图细节，可横向和纵向移动"
              >
                <img
                  className="reader-expanded-image"
                  src={expandedImage.url}
                  alt={expandedPlate?.description || presentation?.place_label || '当前画面'}
                />
              </div>
              <button aria-pressed={viewerZoom} onClick={() => setViewerZoom((v) => !v)}>
                {viewerZoom ? '恢复完整画面' : '放大细节 2×'}
              </button>
              {expandedPlate && (
                <div className="reader-gallery-controls">
                  <button
                    disabled={plates.indexOf(expandedPlate) === 0}
                    onClick={() =>
                      setViewerAsset(plates[plates.indexOf(expandedPlate) - 1].image_asset_id)
                    }
                  >
                    上一幅
                  </button>
                  <span>{expandedPlate.title}</span>
                  <button
                    disabled={plates.indexOf(expandedPlate) === plates.length - 1}
                    onClick={() =>
                      setViewerAsset(plates[plates.indexOf(expandedPlate) + 1].image_asset_id)
                    }
                  >
                    下一幅
                  </button>
                </div>
              )}
            </>
          )}
          {panel === 'gallery' && (
            <div className="reader-gallery">
              <p>全章插图，可自由回看；查看画面不会改变续读位置。</p>
              <div>
                {plates.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => {
                      setViewerAsset(p.image_asset_id)
                      open('image')
                    }}
                  >
                    <img src={data.media[p.image_asset_id]?.url} alt="" loading="lazy" />
                    <span>{p.title}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {panel === 'contents' && (
            <div className="reader-contents">
              {data.blocks
                .filter((b) => b.heading)
                .map((b) => (
                  <button key={b.id} onClick={() => visit(b.byte_start)}>
                    {b.text}
                  </button>
                ))}
              <h3>场景</h3>
              {data.config.scenes.map((s) => (
                <button
                  key={s.id}
                  onClick={() => visit(s.start_byte)}
                  aria-current={s.id === scene?.id ? 'location' : undefined}
                >
                  {s.title}
                  <span>→</span>
                </button>
              ))}
              <button onClick={() => open('voices')}>本章对白</button>
            </div>
          )}
          {panel === 'search' && (
            <div className="reader-search">
              <label htmlFor="reader-search">
                查找原文
                <input
                  id="reader-search"
                  type="search"
                  maxLength={200}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  autoFocus
                />
              </label>
              <p role="status">
                {query
                  ? `${results.length} 个匹配${results.length === 300 ? '（最多显示 300 项）' : ''}`
                  : '输入原文中的字词，保留简繁与标点。'}
              </p>
              <div className="reader-results">
                {results.map((r, i) => (
                  <button key={r.byte + ':' + i} onClick={() => visit(r.byte)}>
                    {r.text}
                  </button>
                ))}
              </div>
            </div>
          )}
          {panel === 'marks' && (
            <div className="reader-marks">
              <button onClick={bookmark}>在当前阅读处加书签</button>
              <p>选择正文可保存原文摘录。记录仅在当前浏览器。</p>
              {!marks.length && <p>还没有书签或摘录。</p>}
              {marks.map((m) => (
                <div className="reader-mark" key={m.id}>
                  <button onClick={() => visit(m.position.byte)}>
                    {m.ranges ? '摘录 · ' : '书签 · '}
                    {m.text}
                  </button>
                  <button
                    onClick={() => setMarks((v) => v.filter((i) => i.id !== m.id))}
                    aria-label={`删除${m.ranges ? '摘录' : '书签'}`}
                  >
                    删除
                  </button>
                </div>
              ))}
            </div>
          )}
          {panel === 'voices' && (
            <div className="reader-results">
              <p>本章只为部分对白制作了声音。</p>
              {voices.length ? (
                voiceGroups.map(({ block, clips }, i) => (
                  <button
                    key={clips[0].take_id}
                    onClick={() => read(clips[0].take_id, clips[0].byte_start)}
                  >
                    {data.characters[clips[0].speaker_id]?.name} · {i + 1} ·{' '}
                    {block.runs
                      .filter((r) => clips.some((c) => c.take_id === r.take_id))
                      .map((r) => r.text)
                      .join('')}
                  </button>
                ))
              ) : (
                <p>本章尚未制作对白声音。</p>
              )}
            </div>
          )}
          {panel === 'settings' && (
            <div className="reader-settings">
              <h3>阅读与画面</h3>
              {!!plates.length && (
                <>
                  <label>
                    画面排布
                    <select
                      aria-label="画面排布"
                      value={preferences.layout || 'split'}
                      onChange={(e) =>
                        settings({ layout: e.target.value as 'split' | 'illustrated' })
                      }
                    >
                      <option value="illustrated">画卷阅读 · 完整插图穿插原文</option>
                      <option value="split">图文并读 · 画面与正文并置</option>
                    </select>
                  </label>
                  <button onClick={() => open('gallery')}>本章画卷 · {plates.length} 幅</button>
                </>
              )}
              <label htmlFor="reader-font-size">
                正文字号 <output>{preferences.size}</output>
                <input
                  id="reader-font-size"
                  aria-label="正文字号"
                  type="range"
                  min="18"
                  max="28"
                  value={preferences.size}
                  onChange={(e) => settings({ size: Number(e.target.value) })}
                />
              </label>
              <label htmlFor="reader-line-height">
                行距 <output>{preferences.leading.toFixed(2)}</output>
                <input
                  id="reader-line-height"
                  aria-label="行距"
                  type="range"
                  min="1.6"
                  max="2.3"
                  step="0.05"
                  value={preferences.leading}
                  onChange={(e) => settings({ leading: Number(e.target.value) })}
                />
              </label>
              <label htmlFor="reader-text-width">
                文字区域宽度 <output>{preferences.width}</output>
                <input
                  id="reader-text-width"
                  aria-label="文字区域宽度"
                  type="range"
                  min="480"
                  max="960"
                  step="40"
                  value={preferences.width}
                  onChange={(e) => settings({ width: Number(e.target.value) })}
                />
              </label>
              <button
                aria-pressed={preferences.stage}
                onClick={() => settings({ stage: !preferences.stage })}
              >
                {preferences.stage ? '收起场景画面' : '展开场景画面'}
              </button>
              <h3>对白与地图</h3>
              <p>声音由 AI 合成，仅覆盖已制作的部分对白；快速跳读与回看不会自动重播。</p>
              <button
                disabled={!voices.length}
                aria-pressed={audio.automatic}
                onClick={() => {
                  audio.setAutomatic((v) => !v)
                  audio.suspend()
                }}
              >
                {audio.automatic ? '关闭自动播放对白' : '开启自动播放对白'}
              </button>
              <button onClick={() => open('voices')}>本章对白</button>
              {data.map && (
                <button
                  onClick={() => {
                    setMapEntry(null)
                    open('map')
                  }}
                >
                  查看战区地图
                </button>
              )}
              <p>个人记录保存在当前浏览器，不跨设备同步。重新打开时声音等待主动开启。</p>
            </div>
          )}
          {panel === 'about' && (
            <div className="reader-about">
              <p>正文完整保留。画面为艺术化阅读辅助；声音由 AI 合成，声音与地图仍需人工审校。</p>
              {data.preview && <p>当前素材仍待确认。</p>}
              {data.issues.map((s, i) => (
                <p key={i}>{s}</p>
              ))}
              <h3>图像来源</h3>
              {Object.values(data.media)
                .filter((m) => m.type === 'image')
                .map((m) => (
                  <p key={m.id}>{m.license}</p>
                ))}
              {data.map && <p>{data.map.note}</p>}
            </div>
          )}
        </div>
      </dialog>
    </div>
  )
}
