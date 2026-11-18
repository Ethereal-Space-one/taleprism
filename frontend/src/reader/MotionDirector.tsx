import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import type {
  IllustrationMotion,
  MotionPoint,
  ReaderAsset,
  ReaderContent,
  ReaderIllustration,
  ReaderState,
} from '../reader-types'
import { ReaderExpandedImage } from './ReaderExpandedImage'
import { bankHits, directionProblem, newDirection } from './motion/authoring'
import {
  directionRecipe,
  resolveEnvironmentMotion,
  simplePolygon,
  validMotionRecipe,
} from './motion/recipes'
import './motion/director.css'

export function MotionDirector({
  plate,
  asset,
  state,
  content,
  onChange,
  onPendingChange,
  initiallyOpen = false,
}: {
  plate: ReaderIllustration
  asset: ReaderAsset
  state: ReaderState
  content: ReaderContent
  onChange: (motion: IllustrationMotion | null) => void
  onPendingChange: (id: string, pending: boolean) => void
  initiallyOpen?: boolean
}) {
  const [open, setOpen] = useState(initiallyOpen),
    [dirty, setDirty] = useState(false)
  const [draft, setDraft] = useState<IllustrationMotion>(
    () =>
      plate.motion ||
      newDirection('rain-wet-ground', asset, content.project.canonical_sha256, plate.after_byte),
  )
  const [points, setPoints] = useState<MotionPoint[]>([]),
    [target, setTarget] = useState<'area' | 'bank' | 'ground'>('area')
  const [x, setX] = useState('50'),
    [y, setY] = useState('50'),
    [message, setMessage] = useState('')
  const [previewed, setPreviewed] = useState(false),
    [previewKey, setPreviewKey] = useState(0)
  const [showPreview, setShowPreview] = useState(false),
    [loaded, setLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)
  const viewport = useRef<HTMLDivElement>(null),
    labelId = useId()
  const builtin = !Object.hasOwn(plate, 'motion') ? resolveEnvironmentMotion(content, plate) : null
  const problem = directionProblem(
    draft,
    plate,
    asset,
    content.project.canonical_sha256,
    state.paragraphs,
  )
  const areas = draft.effect === 'rain-wet-ground' ? draft.areas : draft.water
  const candidate = useMemo(() => directionRecipe(draft, plate.id), [draft, plate.id])
  const renderable = validMotionRecipe(candidate)
  const currentStatus =
    plate.motion === null
      ? '静图'
      : plate.motion
        ? plate.motion.reviewed
          ? '已复核 · 可随阅读呈现'
          : '待复核 · 读者保持静图'
        : builtin
          ? '示例动效 · 可随阅读呈现'
          : '静图'
  useEffect(() => {
    onPendingChange(plate.id, dirty)
    return () => onPendingChange(plate.id, false)
  }, [dirty, plate.id, onPendingChange])
  const [reviewSeconds, setReviewSeconds] = useState(0)
  const sawCycle = useCallback(() => setPreviewed(true), [])
  function edit(next: IllustrationMotion) {
    setDraft({ ...next, reviewed: false })
    setDirty(true)
    setPreviewed(false)
    setShowPreview(false)
    setMessage('')
    setPreviewKey((n) => n + 1)
    setReviewSeconds(0)
  }
  function addPoint(point: MotionPoint) {
    if (points.length >= 64) {
      setMessage('每个范围最多 64 个点。')
      return
    }
    if (target === 'bank' && points.length && point[0] <= points.at(-1)![0]) {
      setMessage('岸线请从左向右标点，横坐标须递增。')
      return
    }
    setPoints((v) => [...v, point])
    setDirty(true)
    setMessage('')
  }
  function finish() {
    if (target === 'bank') {
      if (points.length < 2) {
        setMessage('岸线至少两个点。')
        return
      }
      if (draft.effect === 'wave-impact-backwash')
        edit({ ...draft, bank: points, hits: bankHits(points, 3) })
    } else {
      if (!simplePolygon(points)) {
        setMessage('范围至少三个不同的点，不可交叉或折返；末点无需重复首点。')
        return
      }
      if (
        (target === 'ground' && draft.effect === 'rain-wet-ground'
          ? draft.ground.length
          : areas.length) >= 8
      ) {
        setMessage('每幅最多 8 个允许区。请先移除一个。')
        return
      }
      edit(
        draft.effect === 'rain-wet-ground'
          ? target === 'ground'
            ? { ...draft, ground: [...draft.ground, points] }
            : { ...draft, areas: [...areas, points] }
          : { ...draft, water: [...areas, points] },
      )
    }
    setPoints([])
  }
  function resetFromSaved() {
    setDraft(
      plate.motion ||
        newDirection('rain-wet-ground', asset, content.project.canonical_sha256, plate.after_byte),
    )
    setPoints([])
    setDirty(false)
    setPreviewed(false)
    setShowPreview(false)
    setMessage('已放弃本面板尚未纳入的修改。')
  }
  const evidenceParagraphs = state.paragraphs.filter((p) => p.byte_end <= plate.after_byte)
  return (
    <details
      className="motion-director"
      open={initiallyOpen ? open : undefined}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>
        场景动效导演 · {currentStatus}
        {dirty ? ' · 尚未纳入草稿' : ''}
      </summary>
      <p>
        用同一张底图指认环境的作用范围，不移动镜头、不改原图。雨只在雨区，江岸只在水与水花允许区。无法保护人物或接触线时，请选静图。
      </p>
      <div className="motion-director-actions">
        <button
          type="button"
          onClick={() => {
            onChange(null)
            setDraft(
              newDirection(
                'rain-wet-ground',
                asset,
                content.project.canonical_sha256,
                plate.after_byte,
              ),
            )
            setDirty(false)
            setPoints([])
            setPreviewed(false)
            setShowPreview(false)
            setMessage('已在章节草稿中设为静图，保存章节编排后生效。')
          }}
        >
          只用静图
        </button>
        <button type="button" onClick={resetFromSaved}>
          放弃本面板修改
        </button>
        {builtin && (
          <button
            type="button"
            onClick={() => {
              const base = newDirection(
                builtin.effect,
                asset,
                content.project.canonical_sha256,
                plate.after_byte,
              )
              edit(
                builtin.effect === 'rain-wet-ground'
                  ? {
                      ...base,
                      effect: builtin.effect,
                      areas: builtin.areas,
                      ground: builtin.ground || [],
                      drops: builtin.drops,
                      rings: builtin.rings,
                    }
                  : {
                      ...base,
                      effect: builtin.effect,
                      water: builtin.water,
                      bank: builtin.bank,
                      hits: builtin.hits,
                    },
              )
              setPoints([])
            }}
          >
            从此图已有动效继续导演
          </button>
        )}
      </div>
      <label>
        环境动作
        <select
          value={draft.effect}
          onChange={(e) => {
            edit(
              newDirection(
                e.target.value as IllustrationMotion['effect'],
                asset,
                content.project.canonical_sha256,
                plate.after_byte,
              ),
            )
            setPoints([])
            setTarget('area')
          }}
        >
          <option value="rain-wet-ground">雨线与落地涟漪</option>
          <option value="wave-impact-backwash">推水、碰岸与回流</option>
        </select>
      </label>
      <label>
        选择已出现的原文段落
        <select
          value=""
          onChange={(e) => {
            const p = evidenceParagraphs.find((p) => p.byte_start === Number(e.target.value))
            if (p) edit({ ...draft, evidence: [...p.text].slice(0, 300).join('') })
          }}
        >
          <option value="">选择一段作为依据，再保留需要的逐字引句</option>
          {evidenceParagraphs.map((p, i) => (
            <option key={p.byte_start} value={p.byte_start}>
              第 {i + 1} 段 · {p.preview}
            </option>
          ))}
        </select>
      </label>
      <label>
        逐字原文依据（8 至 300 字，不得提前引用后文）
        <textarea
          maxLength={600}
          value={draft.evidence}
          onChange={(e) => edit({ ...draft, evidence: e.target.value })}
        />
      </label>
      <label>
        画面观察与保护范围（8 至 300 字）
        <textarea
          maxLength={600}
          value={draft.note}
          placeholder="例：檐外湿地接雨，人物和长凳在范围外；不让雨线穿过脸和手。"
          onChange={(e) => edit({ ...draft, note: e.target.value })}
        />
      </label>
      <h4 id={labelId}>标注允许动作的范围</h4>
      <p>
        沿边界依次点选，完成后闭合；人物、灯、道具留在范围外。绿色为允许区，蓝色虚线为接雨湿地，金色为当前标点。可用下面的百分比坐标代替点图。多个范围不可用作挖孔。
      </p>
      <div className="motion-director-actions">
        <button
          type="button"
          disabled={points.length > 0}
          aria-pressed={target === 'area'}
          onClick={() => {
            setTarget('area')
            setPoints([])
          }}
        >
          {draft.effect === 'rain-wet-ground' ? '标雨区' : '标水与水花允许区'}
        </button>
        {draft.effect === 'rain-wet-ground' && (
          <button
            type="button"
            disabled={points.length > 0}
            aria-pressed={target === 'ground'}
            onClick={() => {
              setTarget('ground')
              setPoints([])
            }}
          >
            标接雨湿地（涟漪）
          </button>
        )}
        {draft.effect === 'wave-impact-backwash' && (
          <button
            type="button"
            disabled={points.length > 0}
            aria-pressed={target === 'bank'}
            onClick={() => {
              setTarget('bank')
              setPoints([])
            }}
          >
            从左向右标岸线
          </button>
        )}
      </div>
      <div
        className="motion-director-map"
        style={{ aspectRatio: `${asset.width || 16} / ${asset.height || 9}` }}
      >
        <img
          src={asset.url}
          alt={`${plate.title}，用于标注的原图`}
          onLoad={() => {
            setLoaded(true)
            setImageError(false)
          }}
          onError={() => {
            setLoaded(false)
            setImageError(true)
          }}
        />
        <svg
          viewBox="0 0 1000 1000"
          preserveAspectRatio="none"
          role="img"
          aria-labelledby={labelId}
          onClick={(e) => {
            if (!loaded) return
            const rect = e.currentTarget.getBoundingClientRect()
            if (rect.width && rect.height)
              addPoint([
                Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
                Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)),
              ])
          }}
        >
          {areas.map((polygon, i) => (
            <polygon
              className="motion-mask"
              key={i}
              points={polygon.map(([x, y]) => `${x * 1000},${y * 1000}`).join(' ')}
            />
          ))}
          {draft.effect === 'rain-wet-ground' &&
            draft.ground.map((polygon, i) => (
              <polygon
                className="motion-ground"
                key={`ground-${i}`}
                points={polygon.map(([x, y]) => `${x * 1000},${y * 1000}`).join(' ')}
              />
            ))}
          {draft.effect === 'wave-impact-backwash' && (
            <polyline
              className="motion-bank"
              points={draft.bank.map(([x, y]) => `${x * 1000},${y * 1000}`).join(' ')}
            />
          )}
          <polyline
            className="motion-pending"
            points={points.map(([x, y]) => `${x * 1000},${y * 1000}`).join(' ')}
          />
          {points.map(([x, y], i) => (
            <circle className="motion-vertex" key={i} cx={x * 1000} cy={y * 1000} r="6" />
          ))}
        </svg>
      </div>
      {imageError && <p role="alert">底图未能载入，请先刷新素材；不能据此复核动效。</p>}
      <div className="motion-director-coordinates">
        <label>
          横坐标 %
          <input
            type="number"
            min="0"
            max="100"
            step="0.1"
            value={x}
            onChange={(e) => setX(e.target.value)}
          />
        </label>
        <label>
          纵坐标 %
          <input
            type="number"
            min="0"
            max="100"
            step="0.1"
            value={y}
            onChange={(e) => setY(e.target.value)}
          />
        </label>
        <button
          type="button"
          disabled={
            !loaded ||
            x === '' ||
            y === '' ||
            ![Number(x), Number(y)].every((n) => Number.isFinite(n) && n >= 0 && n <= 100)
          }
          onClick={() => addPoint([Number(x) / 100, Number(y) / 100])}
        >
          添加坐标点
        </button>
        <button
          type="button"
          disabled={!points.length}
          onClick={() => setPoints((v) => v.slice(0, -1))}
        >
          撤回最后一点
        </button>
        <button type="button" disabled={!points.length} onClick={() => setPoints([])}>
          清空当前标点
        </button>
        <button
          type="button"
          disabled={points.length < (target === 'bank' ? 2 : 3)}
          onClick={finish}
        >
          {target === 'bank' ? '完成岸线' : '闭合并加入范围'}
        </button>
      </div>
      <p role="status">
        当前标点 {points.length} 个 · 已完成允许区 {areas.length} 个
        {draft.effect === 'rain-wet-ground' ? ` · 接雨湿地 ${draft.ground.length} 个` : ''}
        {draft.effect === 'wave-impact-backwash' ? ` · 岸线 ${draft.bank.length} 点` : ''}
      </p>
      {areas.map((_, i) => (
        <button
          type="button"
          key={i}
          onClick={() =>
            edit(
              draft.effect === 'rain-wet-ground'
                ? { ...draft, areas: areas.filter((_, j) => j !== i) }
                : { ...draft, water: areas.filter((_, j) => j !== i) },
            )
          }
        >
          移除范围 {i + 1}
        </button>
      ))}
      {draft.effect === 'rain-wet-ground' &&
        draft.ground.map((_, i) => (
          <button
            type="button"
            key={`remove-ground-${i}`}
            onClick={() => edit({ ...draft, ground: draft.ground.filter((_, j) => j !== i) })}
          >
            移除接雨湿地 {i + 1}
          </button>
        ))}
      {draft.effect === 'rain-wet-ground' ? (
        <div className="motion-director-coordinates">
          <label>
            雨线数量
            <input
              type="range"
              min="1"
              max="128"
              value={draft.drops}
              onChange={(e) => edit({ ...draft, drops: Number(e.target.value) })}
            />
            <output>{draft.drops}</output>
          </label>
          <label>
            涟漪数量（无可接雨湿地时设为 0）
            <input
              type="range"
              min="0"
              max="16"
              value={draft.rings}
              onChange={(e) => edit({ ...draft, rings: Number(e.target.value) })}
            />
            <output>{draft.rings}</output>
          </label>
        </div>
      ) : (
        <div className="motion-director-coordinates">
          <label>
            沿岸撞点数
            <select
              value={draft.hits.length || 3}
              disabled={draft.bank.length < 2}
              onChange={(e) =>
                edit({ ...draft, hits: bankHits(draft.bank, Number(e.target.value)) })
              }
            >
              {[1, 2, 3, 4, 5, 6].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label>
            浪势
            <input
              type="range"
              min="0.1"
              max="1.3"
              step="0.05"
              value={draft.hits[0]?.gain || 0.9}
              disabled={!draft.hits.length}
              onChange={(e) =>
                edit({
                  ...draft,
                  hits: draft.hits.map((h) => ({ ...h, gain: Number(e.target.value) })),
                })
              }
            />
          </label>
        </div>
      )}
      <h4>对照原图与动效，再决定是否交付</h4>
      <p>
        {draft.effect === 'rain-wet-ground'
          ? '雨从允许区落下；检查脸、檐下和道具没有穿雨。涟漪只用于确实接雨的区域。'
          : '按「推水 → 碰岸 → 水花落下 → 泡沫回流」看完整一轮；没有水先喷水或岩上白线就退回修改。'}
      </p>
      <button
        type="button"
        disabled={!renderable || !loaded || points.length > 0}
        onClick={() => {
          setShowPreview((v) => !v)
          setReviewSeconds(0)
          setPreviewKey((n) => n + 1)
        }}
      >
        {showPreview ? '收起动效对照' : '打开动效对照'}
      </button>
      {open && showPreview && renderable && (
        <div className="motion-director-comparison">
          <figure>
            <img src={asset.url} alt={`${plate.title}，静态原图`} />
            <figcaption>原图，像素不改动</figcaption>
          </figure>
          <div className="motion-director-preview">
            <ReaderExpandedImage
              key={previewKey}
              viewportRef={viewport}
              src={asset.url}
              alt={`${plate.title}，导演预览`}
              zoomed={false}
              pending={false}
              recipe={candidate}
              onLoad={() => {}}
              onError={() => {
                setPreviewed(false)
                setImageError(true)
              }}
              onMotionCycle={sawCycle}
              onMotionSecond={setReviewSeconds}
            />
            <progress aria-label="可见动效复核进度" max={8} value={previewed ? 8 : reviewSeconds} />
            <p>
              {previewed
                ? '已播放至少 8 秒，可记录你的实际复核。'
                : `已看 ${reviewSeconds} / 8 秒。请开启动效，并让对照图的大部分留在屏幕里；滚走会暂停计时。`}
              减少动效偏好下保持静图。
            </p>
          </div>
        </div>
      )}
      {problem && <p className="motion-director-hint">{problem}</p>}
      <label className="inline-check">
        <input
          type="checkbox"
          checked={draft.reviewed}
          disabled={!!problem || !previewed || points.length > 0 || imageError}
          onChange={(e) => {
            setDraft({ ...draft, reviewed: e.target.checked })
            setDirty(true)
          }}
        />
        我已对照这张底图检查完整动作循环，人物、关键道具和原文时机没有被改变。这不是底图美术的最终认可。
      </label>
      {!previewed && (
        <p className="motion-director-hint">
          新的复核须先在此面板实际播放预览。也可以先以待复核草稿保存，读者只看静图。
        </p>
      )}
      <div className="motion-director-actions">
        <button
          type="button"
          disabled={!!problem || points.length > 0}
          onClick={() => {
            onChange(draft)
            setDirty(false)
            setMessage(
              draft.reviewed
                ? '已纳入章节草稿。请保存章节编排，再从原文位置试读。'
                : '已纳入待复核草稿。保存后读者仍只看静图。',
            )
          }}
        >
          纳入章节草稿{draft.reviewed ? '（已复核）' : '（待复核静图）'}
        </button>
      </div>
      <p role="status">{message}</p>
    </details>
  )
}
