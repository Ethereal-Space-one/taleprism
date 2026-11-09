import { useState } from 'react'
import type { ReaderMapData, ReaderMapEntry } from './reader-types'

export function ReaderMap({
  data,
  at,
  entry,
}: {
  data: ReaderMapData
  at: number
  entry?: ReaderMapEntry | null
}) {
  const available = data.phase_anchors.reduce((best, a, i) => (at >= a ? i : best), 0)
  const [phase, setPhase] = useState(() =>
    entry
      ? Math.max(
          0,
          data.phases.findIndex((p) => p.id === entry.phase_id),
        )
      : available,
  )
  const [detail, setDetail] = useState(() => {
    const initial = data.places.find((p) => p.id === entry?.place_ids[0])
    const inLocalView =
      !initial || (initial.x >= 350 && initial.x <= 650 && initial.y >= 185 && initial.y <= 425)
    return window.innerWidth < 600 && inLocalView
  })
  const [placeId, setPlaceId] = useState(entry?.place_ids[0] || 'chibi')
  const place = data.places.find((p) => p.id === placeId)!
  const shown = phase
  return (
    <div className="reader-map">
      <p className="reader-muted">{data.subtitle}</p>
      <p>
        当前正文：{data.phases[available].title} · 正在查看：{data.phases[shown].title}
      </p>
      <div className="map-phases" role="group" aria-label="战役阶段">
        {data.phases.map((p, i) => (
          <button
            key={p.title}
            aria-pressed={shown === i}
            title={p.description}
            onClick={() => setPhase(i)}
          >
            {p.title}
            {i === available ? ' · 正文' : ''}
          </button>
        ))}
      </div>
      <div className="map-view-controls">
        <button onClick={() => setDetail((v) => !v)}>{detail ? '战区概览' : '两岸局部'}</button>
        <span>北 ↑ · 江道简化</span>
      </div>
      <svg
        className="history-map"
        viewBox={detail ? '350 185 300 240' : data.viewBox}
        role="img"
        aria-label={`赤壁战区地图，${data.phases[shown].title}`}
      >
        <defs>
          <marker id="map-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L7,3 L0,6" className="map-arrowhead" />
          </marker>
          <pattern id="map-camp-pattern" width="10" height="10" patternUnits="userSpaceOnUse">
            <path d="M0 10 L10 0" className="map-hatching" />
          </pattern>
        </defs>
        <rect width="960" height="560" className="map-land" />
        <path
          d="M20 70 Q170 15 320 85 T630 65 T960 90 M0 470 Q180 510 320 455 T600 480 T960 450"
          className="map-contours"
        />
        <path d={data.river} className="map-river-bank" />
        <path d={data.river} className="map-river" />
        <text x="300" y="420" className="map-water-name">
          长江
        </text>
        <ellipse cx="475" cy="220" rx="66" ry="32" className="map-camp map-camp-north" />
        <ellipse cx="555" cy="395" rx="77" ry="31" className="map-camp map-camp-south" />
        <text x="475" y="226" textAnchor="middle" className="map-camp-label">
          曹军营区
        </text>
        <text x="555" y="401" textAnchor="middle" className="map-camp-label">
          孙刘联军
        </text>
        {shown === 0 && (
          <path
            d="M130 170 Q270 210 430 250"
            className="map-route map-march"
            markerEnd="url(#map-arrow)"
          />
        )}
        {shown === 1 && (
          <>
            <path
              d="M530 365 Q535 315 490 254"
              className="map-route map-fire"
              markerEnd="url(#map-arrow)"
            />
            <text x="570" y="320" className="map-route-label">
              火攻方向
            </text>
          </>
        )}
        {shown === 2 && (
          <>
            <path
              d="M455 265 Q350 190 150 165"
              className="map-route map-retreat"
              markerEnd="url(#map-arrow)"
            />
            <text x="265" y="190" className="map-route-label">
              撤军方向（约略）
            </text>
          </>
        )}
        {data.places.map((p) => (
          <g
            key={p.id}
            className={`map-place ${p.id === placeId ? 'selected' : ''}`}
            tabIndex={0}
            role="button"
            aria-label={`查看${p.label}历史位置`}
            onClick={() => setPlaceId(p.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                setPlaceId(p.id)
              }
            }}
          >
            <circle cx={p.x} cy={p.y} r="17" className="map-place-hit" />
            <circle cx={p.x} cy={p.y} r="5" />
            <text x={p.x} y={p.y - 15} textAnchor="middle">
              {p.label}
            </text>
          </g>
        ))}
        <text x="50" y="510" className="map-footnote">
          营区与箭头为区域／方向示意
        </text>
      </svg>
      <p className="map-phase-description">{data.phases[shown].description}</p>
      <div className="map-place-tabs" role="group" aria-label="历史地点">
        {data.places.map((p) => (
          <button key={p.id} aria-pressed={p.id === placeId} onClick={() => setPlaceId(p.id)}>
            {p.label}
          </button>
        ))}
      </div>
      <section className="map-place-detail" aria-live="polite">
        <h3>{place.label}</h3>
        <p>{place.today}</p>
        <p>{place.description}</p>
        <p className="reader-muted">
          资料：
          {place.source_ids.map((id) => data.sources.find((s) => s.id === id)?.title).join('；')}
        </p>
      </section>
      <details className="map-sources">
        <summary>地图依据与定位说明</summary>
        <p>{data.note}</p>
        {data.sources.map((s) => (
          <p key={s.id}>
            {s.url ? (
              <a href={s.url} target="_blank" rel="noreferrer">
                {s.title} ↗
              </a>
            ) : (
              s.title
            )}
            <br />
            <span className="reader-muted">{s.note}</span>
          </p>
        ))}
      </details>
    </div>
  )
}
