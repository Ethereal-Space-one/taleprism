import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReaderContent, ReaderIllustration } from '../reader-types'
import { resolveReadingMotion } from '../reader/motion/recipes'
import { startEnvironmentMotion } from '../reader/motion/runtime'
import { inspectPhrase, proofAt, publicAudio } from './passageProofModel'
import './passage-proof.css'

function Motion({ data, plate }: { data: ReaderContent; plate: ReaderIllustration }) {
  const box = useRef<HTMLDivElement>(null),
    img = useRef<HTMLImageElement>(null),
    canvas = useRef<HTMLCanvasElement>(null)
  const [running, setRunning] = useState(false),
    [broken, setBroken] = useState(false)
  const recipe = useMemo(() => resolveReadingMotion(data, plate), [data, plate])
  useEffect(() => {
    if (!running || !recipe || !img.current || !box.current || !canvas.current) return
    return startEnvironmentMotion(img.current, canvas.current, box.current, recipe)
  }, [running, recipe])
  const media = data.media[plate.image_asset_id]
  return (
    <figure>
      <div className="proof-plate" ref={box}>
        {media && !broken && (
          <img
            src={media.url}
            ref={img}
            alt={plate.description || plate.title}
            onError={() => setBroken(true)}
          />
        )}
        <canvas ref={canvas} hidden aria-hidden="true" />
      </div>
      <figcaption>
        {plate.title} ·{' '}
        {broken || !media
          ? '底图不可用。'
          : recipe
            ? '本段已有可播放的局部动效；减少动态效果时保留静图。'
            : '当前为静图；没有可播放的已复核动效。'}
      </figcaption>
      {!!recipe && !!media && !broken && (
        <button type="button" aria-pressed={running} onClick={() => setRunning(!running)}>
          {running ? '停止局部动效' : '试演已复核动效'}
        </button>
      )}
    </figure>
  )
}

function CoverProof({ data }: { data: ReaderContent }) {
  const [broken, setBroken] = useState(false)
  const { title, subtitle, cover_asset_id: id } = data.config
  const asset = id ? data.media[id] : undefined
  const image = asset?.type === 'image' && !broken ? asset : undefined
  return (
    <section className="proof-cover" aria-label="卷首校样">
      <h4>卷首校样 · 读第一段之前</h4>
      <p>
        把章名、副标题和封面图一起看：第一次翻开，读者已经知道什么？这是不是你想让读者此时知道的？
      </p>
      <p>{title}</p>
      {subtitle && <p>{subtitle}</p>}
      {image ? (
        <figure>
          <img src={image.url} alt={title + '章节封面'} onError={() => setBroken(true)} />
          <figcaption>这里展示封面原图，实际裁切请以导出读本为准。</figcaption>
        </figure>
      ) : (
        <p>{id ? '已选封面图无法显示，不能视为已校对。' : '没有设置封面图。'}</p>
      )}
      <small>有意预告不等于剧透。工具不替作者判断，也不会改动章名或封面。</small>
    </section>
  )
}

function Listening({ src, label }: { src: string; label: string }) {
  const [broken, setBroken] = useState(false)
  const audio = useRef<HTMLAudioElement>(null)
  useEffect(() => {
    const el = audio.current
    const hide = () => {
      if (document.hidden) el?.pause()
    }
    document.addEventListener('visibilitychange', hide)
    return () => {
      el?.pause()
      document.removeEventListener('visibilitychange', hide)
    }
  }, [src])
  return (
    <div>
      <audio
        ref={audio}
        aria-label={label}
        controls
        preload="none"
        src={src}
        onError={() => setBroken(true)}
      />
      {broken && <p role="alert">此声音暂时无法播放，不能据此判断听感。</p>}
    </div>
  )
}

export function PassageProof({
  data,
  locked,
  onSound,
}: {
  data: ReaderContent
  locked: boolean
  onSound: (anchor: number) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <details className="passage-proof" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>段落试演与防剧透校对</summary>
      {open && <ProofBody data={data} locked={locked} onSound={onSound} />}
    </details>
  )
}

function ProofBody({
  data,
  locked,
  onSound,
}: {
  data: ReaderContent
  locked: boolean
  onSound: (anchor: number) => void
}) {
  const [idx, setIdx] = useState(0),
    [mode, setMode] = useState<'quiet' | 'sound' | 'motion'>('quiet'),
    [moment, setMoment] = useState<'before' | 'after'>('after'),
    [phrase, setPhrase] = useState('')
  const proof = useMemo(() => proofAt(data, idx, moment), [data, idx, moment])
  const hits = useMemo(() => proof && inspectPhrase(data, proof, phrase), [data, proof, phrase])
  if (!proof) return <p>没有可校对的原文段落。</p>
  const { block } = proof
  const audio = proof.last ? publicAudio(proof.last, data) : []
  const sound = block.soundscape && data.media[block.soundscape.id]
  return (
    <div className="proof-body">
      <label>
        试演原文段落
        <select value={idx} onChange={(e) => setIdx(Number(e.target.value))}>
          {data.blocks.map((b, i) => (
            <option value={i} key={b.id}>
              第 {i + 1} 段 · {b.text.slice(0, 40)}
            </option>
          ))}
        </select>
      </label>
      <blockquote>{block.text}</blockquote>
      <fieldset>
        <legend>同一段，换一种读法</legend>
        <div className="proof-modes">
          {(
            [
              ['quiet', '留白'],
              ['sound', '声景'],
              ['motion', '局部动效'],
            ] as const
          ).map(([key, title]) => (
            <button
              key={key}
              type="button"
              aria-pressed={mode === key}
              onClick={() => setMode(key)}
            >
              {title}
            </button>
          ))}
        </div>
      </fieldset>
      <div key={idx + ':' + mode} className="proof-choice">
        {mode === 'quiet' && (
          <p>只读上面的原文，不播放声音，也不显示叙事插图。已保存的编排没有改变。</p>
        )}
        {mode === 'sound' && (
          <>
            <p>
              {sound
                ? '试听本段已采用的声景。'
                : block.soundscape
                  ? '本段已采用声景，但文件不可用。不能用样音代替它。'
                  : '试听样音：本地合成的 12 秒细雨。它不是原文推断，也没有被采用。'}
            </p>
            {(!block.soundscape || sound) && (
              <Listening
                key={sound?.id ?? 'demo'}
                src={sound?.url || '/api/studio/preview/rain.wav'}
                label="同段声景试听"
              />
            )}
            <button
              type="button"
              disabled={locked}
              onClick={() => {
                setMode('quiet')
                onSound(block.byte_start)
              }}
            >
              在这个段落编辑声景
            </button>
            <small>需另选原文依据、完整试听，再独立决定是否采用。</small>
          </>
        )}
        {mode === 'motion' &&
          (!proof.landed.length ? (
            <p>
              本段没有落点插图。不会用示例假装效果；要试演，请先放置自己的插图，并在动效导演中标定、复核。
            </p>
          ) : (
            proof.landed.map((p) => <Motion key={p.id} data={data} plate={p} />)
          ))}
      </div>
      <section className="proof-review" aria-label="防剧透校对">
        <h3>在读者的位置校对</h3>
        <p>这是一张作者校样，不会删改作品或自动签核。上面的选段是编辑参考，不代表读者已经读到。</p>
        <label>
          读者检查位置
          <select value={moment} onChange={(e) => setMoment(e.target.value as typeof moment)}>
            <option value="before">进入所选段落前</option>
            <option value="after">读完所选段落时</option>
          </select>
        </label>
        <CoverProof
          key={data.config.cover_asset_id + ':' + data.versions.reader_revision}
          data={data}
        />
        <h4>原文摘录</h4>
        <p>{proof.last ? proof.last.text : '卷首，尚无已读原文。'}</p>
        <h4>画卷与图说</h4>
        <p>
          已解锁 {proof.gallery.length} 幅，后续 {proof.hiddenCount}{' '}
          幅。未解锁的名称与缩略图不在清单中。
        </p>
        {proof.gallery.map((p) => (
          <figure key={p.id}>
            {data.media[p.image_asset_id] && (
              <img
                loading="lazy"
                src={data.media[p.image_asset_id].url}
                alt={proof.presentations.get(p.id)?.visualDescription || p.description || p.title}
              />
            )}
            <figcaption>
              {p.title} ·{' '}
              {proof.presentations.get(p.id)?.visualDescription || p.description || '无独立图说'}
            </figcaption>
          </figure>
        ))}
        <h4>刚读过一段的声音</h4>
        {audio.length ? (
          audio.map((a, i) => (
            <div key={a.id + ':' + i}>
              <p>
                {a.kind} · {a.label}
                {a.media?.credit ? ' · ' + a.media.credit : ''}
              </p>
              {a.media ? (
                <Listening src={a.media.url} label={'试听' + a.kind} />
              ) : (
                <p>缺少音频，需人工核对。</p>
              )}
            </div>
          ))
        ) : (
          <p>无已编入的声景、朗读或对白。</p>
        )}
        <label>
          可选：检查尚不应透露的名字或短语
          <input
            maxLength={100}
            value={phrase}
            placeholder="例如：真实身份"
            onChange={(e) => setPhrase(e.target.value)}
          />
        </label>
        {phrase.trim() && (
          <p role="status">
            {hits?.length
              ? '截至检查位置已出现：' + hits.join('、')
              : '当前可核对的文字中未发现逐字匹配。'}
          </p>
        )}
        <small>
          仅检查封面文字、截至此处的原文、已解锁图说、声音标签与署名。画中人物、录音说出的内容、同义暗示仍需亲自看和听。导出后请用接收者身份再读一次。
        </small>
      </section>
    </div>
  )
}
