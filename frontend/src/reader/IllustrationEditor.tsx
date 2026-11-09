import type { ReaderConfig, ReaderState } from '../reader-types'

export function IllustrationEditor({
  draft,
  state,
  anchor,
  update,
}: {
  draft: ReaderConfig
  state: ReaderState
  anchor: number
  update: (c: Partial<ReaderConfig>) => void
}) {
  const plates = draft.illustrations || []
  const assets = state.assets.filter((a) => a.kind === 'scene' && a.status !== 'rejected')
  const patch = (id: string, value: Partial<(typeof plates)[number]>) =>
    update({
      illustrations: plates
        .map((p) => (p.id === id ? { ...p, ...value } : p))
        .sort((a, b) => a.after_byte - b.after_byte),
    })
  return (
    <section className="reader-illustration-editor" aria-label="章节插图编排">
      <h3>章节插图</h3>
      <p>
        插图位于完整原文段落之后。选择画卷阅读时显示完整构图，图文并读仍使用场景编排；两种阅读方式均可自由切换。
      </p>
      <label>
        默认阅读排布
        <select
          value={draft.reading_layout || 'split'}
          onChange={(e) =>
            update({ reading_layout: e.target.value as ReaderConfig['reading_layout'] })
          }
        >
          <option value="illustrated">画卷阅读</option>
          <option value="split">图文并读</option>
        </select>
      </label>
      <button
        type="button"
        disabled={!assets.length || plates.length >= 64}
        onClick={() => {
          const block = state.paragraphs.find((p) => p.byte_start <= anchor && p.byte_end > anchor)
          if (!block || plates.some((p) => p.after_byte === block.byte_end)) return
          update({
            illustrations: [
              ...plates,
              {
                id: crypto.randomUUID(),
                after_byte: block.byte_end,
                image_asset_id: assets[0].id,
                title: '新插图',
                description: '',
              },
            ].sort((a, b) => a.after_byte - b.after_byte),
          })
        }}
      >
        在当前段落后加插图
      </button>
      {plates.map((p) => (
        <article key={p.id} className="reader-illustration-edit">
          <img
            src={assets.find((a) => a.id === p.image_asset_id)?.url}
            alt={p.title}
            loading="lazy"
          />
          <label>
            插图名称
            <input
              maxLength={80}
              value={p.title}
              onChange={(e) => patch(p.id, { title: e.target.value })}
            />
          </label>
          <label>
            图片说明
            <input
              maxLength={300}
              value={p.description}
              onChange={(e) => patch(p.id, { description: e.target.value })}
            />
          </label>
          <label>
            放在此段之后
            <select
              value={p.after_byte}
              onChange={(e) => patch(p.id, { after_byte: Number(e.target.value) })}
            >
              {state.paragraphs.map((b, i) => (
                <option
                  key={b.byte_start}
                  value={b.byte_end}
                  disabled={plates.some(
                    (other) => other.id !== p.id && other.after_byte === b.byte_end,
                  )}
                >
                  第 {i + 1} 段 · {b.preview}
                </option>
              ))}
            </select>
          </label>
          <label>
            插图素材
            <select
              value={p.image_asset_id}
              onChange={(e) => patch(p.id, { image_asset_id: e.target.value })}
            >
              {assets.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label || a.sample_key || '上传图片'} ·{' '}
                  {a.status === 'accepted' ? '已接受' : '待确认'}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => update({ illustrations: plates.filter((i) => i.id !== p.id) })}
          >
            移除此处插图
          </button>
        </article>
      ))}
    </section>
  )
}
