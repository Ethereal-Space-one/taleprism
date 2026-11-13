import type { ReaderState } from './reader-types'
export type SceneObject = {
  id: string
  name: string
  kind: 'fixed' | 'movable'
  appearance: string
  home: string
  origin: 'source' | 'artistic'
  evidence: string
}
export type Scene = {
  id: string
  title: string
  layout: string
  reference_asset_id: string | null
  objects: SceneObject[]
}
export type ObjectState = {
  object_id: string
  visibility: 'visible' | 'offscreen' | 'absent'
  position: string
  reason: string
}
export type Continuity = {
  scene_id: string | null
  method: 'reuse' | 'edit' | 'new_view'
  reuse_asset_id: string | null
  camera: string
  changes: string
  states: ObjectState[]
}
export type Check = {
  fingerprint: string
  reviewer: 'creator' | 'assistant'
  notes: string
  checked_at: string
  status: 'passed' | 'rejected' | 'revoked' | 'stale'
  basis: {
    version: 1
    source_sha256: string
    character_references: {
      character_id: string
      figure_asset_id: string | null
      sha256: string | null
    }[]
    images: { asset_id: string; sha256: string }[]
  } | null
  invalidated_reason: string | null
} | null
export type CheckDecision = 'passed' | 'rejected' | 'revoked'
export type CheckDraft = { notes: string; checks: string[] }
const passed = (shot: SceneShot) =>
  shot.continuity_check?.status === 'passed' && !!shot.continuity_check.basis
export const emptyContinuity = (): Continuity => ({
  scene_id: null,
  method: 'edit',
  reuse_asset_id: null,
  camera: '',
  changes: '',
  states: [],
})
type Assets = ReaderState['assets']
type SceneShot = {
  id: string
  title: string
  after_byte: number
  image_asset_id: string | null
  status: string
  continuity: Continuity
  continuity_check: Check
}
function assetOptions(assets: Assets) {
  return assets
    .filter((a) => a.kind === 'scene' && a.status !== 'rejected')
    .map((a) => (
      <option key={a.id} value={a.id}>
        {a.label || a.license.slice(0, 45)}
      </option>
    ))
}
export function SceneLibrary({
  scenes,
  shots,
  assets,
  change,
}: {
  scenes: Scene[]
  shots: SceneShot[]
  assets: Assets
  change: (s: Scene[]) => void
}) {
  const update = (id: string, patch: Partial<Scene>) =>
    change(scenes.map((s) => (s.id === id ? { ...s, ...patch } : s)))
  return (
    <section className="scene-library" aria-label="场景与物件设定">
      <h3>场景与物件设定</h3>
      <p>先固定空间和物件，再安排连续镜头。更改设定会撤销相关镜头的方案确认与连续性检查。</p>
      {scenes.map((scene) => (
        <details className="scene-definition" key={scene.id}>
          <summary>
            {scene.title} · {scene.objects.length}件物品
          </summary>
          <div className="production-fields">
            <label>
              场景名称
              <input
                value={scene.title}
                onChange={(e) => update(scene.id, { title: e.target.value })}
              />
            </label>
            <label>
              场景母版
              <select
                value={scene.reference_asset_id || ''}
                onChange={(e) => update(scene.id, { reference_asset_id: e.target.value || null })}
              >
                <option value="">稍后选择</option>
                {assetOptions(assets)}
              </select>
            </label>
          </div>
          <label>
            固定空间关系与歧义处理
            <textarea
              value={scene.layout}
              onChange={(e) => update(scene.id, { layout: e.target.value })}
            />
          </label>
          {scene.objects.map((obj) => {
            const edit = (patch: Partial<SceneObject>) =>
              update(scene.id, {
                objects: scene.objects.map((o) => (o.id === obj.id ? { ...o, ...patch } : o)),
              })
            return (
              <fieldset key={obj.id}>
                <legend>{obj.name || '新物件'}</legend>
                <div className="production-fields">
                  <label>
                    物件名称
                    <input value={obj.name} onChange={(e) => edit({ name: e.target.value })} />
                  </label>
                  <label>
                    物件类型
                    <select
                      value={obj.kind}
                      onChange={(e) => edit({ kind: e.target.value as SceneObject['kind'] })}
                    >
                      <option value="fixed">固定物件</option>
                      <option value="movable">可移动道具</option>
                    </select>
                  </label>
                  <label>
                    外观、数量与结构
                    <textarea
                      value={obj.appearance}
                      onChange={(e) => edit({ appearance: e.target.value })}
                    />
                  </label>
                  <label>
                    固定位置／初始位置
                    <textarea value={obj.home} onChange={(e) => edit({ home: e.target.value })} />
                  </label>
                  <label>
                    设定来源
                    <select
                      value={obj.origin}
                      onChange={(e) => edit({ origin: e.target.value as SceneObject['origin'] })}
                    >
                      <option value="source">原文依据</option>
                      <option value="artistic">艺术设计／解释</option>
                    </select>
                  </label>
                  <label>
                    原文引句／美术说明
                    <textarea
                      value={obj.evidence}
                      onChange={(e) => edit({ evidence: e.target.value })}
                    />
                  </label>
                </div>
                <button
                  onClick={() =>
                    update(scene.id, { objects: scene.objects.filter((o) => o.id !== obj.id) })
                  }
                >
                  删除此物件
                </button>
              </fieldset>
            )
          })}
          <div className="production-toolbar">
            <button
              disabled={scene.objects.length >= 32}
              onClick={() =>
                update(scene.id, {
                  objects: [
                    ...scene.objects,
                    {
                      id: crypto.randomUUID(),
                      name: '新物件',
                      kind: 'movable',
                      appearance: '',
                      home: '',
                      origin: 'artistic',
                      evidence: '',
                    },
                  ],
                })
              }
            >
              添加物件
            </button>
            <button
              disabled={shots.some((s) => s.continuity.scene_id === scene.id)}
              onClick={() => change(scenes.filter((s) => s.id !== scene.id))}
            >
              删除场景
            </button>
            <small>删除场景前，先解除镜头的场景关联。</small>
          </div>
        </details>
      ))}
      <button
        disabled={scenes.length >= 32}
        onClick={() =>
          change([
            ...scenes,
            {
              id: crypto.randomUUID(),
              title: '新场景',
              layout: '',
              reference_asset_id: null,
              objects: [],
            },
          ])
        }
      >
        添加场景设定
      </button>
    </section>
  )
}
export function ShotContinuity({
  shot,
  shots,
  scenes,
  assets,
  update,
  locked,
  check,
  draft,
  changeDraft,
  references,
}: {
  shot: SceneShot
  shots: SceneShot[]
  scenes: Scene[]
  assets: Assets
  update: (c: Continuity) => void
  locked: boolean
  check: (notes: string, decision: CheckDecision) => void
  draft: CheckDraft
  changeDraft: (draft: CheckDraft) => void
  references: { name: string; selection: string; valid: boolean; url?: string; sha256?: string }[]
}) {
  const c = shot.continuity,
    scene = scenes.find((s) => s.id === c.scene_id)
  const previous = shots
    .filter((s) => s.continuity.scene_id === c.scene_id && s.after_byte < shot.after_byte)
    .sort((a, b) => b.after_byte - a.after_byte)[0]
  const { notes, checks } = draft
  const states =
    scene?.objects.map(
      (o) =>
        c.states.find((s) => s.object_id === o.id) || {
          object_id: o.id,
          visibility: 'visible' as const,
          position: o.home,
          reason: '',
        },
    ) || []
  const picture = (id: string | null | undefined, caption: string) => {
    const asset = assets.find((a) => a.id === id)
    return (
      <figure>
        <figcaption>{caption}</figcaption>
        {asset ? (
          <a href={asset.url} target="_blank" rel="noreferrer" aria-label={'放大' + caption}>
            <img src={asset.url} alt={caption} />
          </a>
        ) : (
          <p>尚未回填图片</p>
        )}
      </figure>
    )
  }
  return (
    <section className="shot-continuity" aria-label="镜头连续性">
      <h4>场景连续性</h4>
      <label>
        所属场景
        <select
          value={c.scene_id || ''}
          onChange={(e) => {
            const next = scenes.find((s) => s.id === e.target.value)
            update({
              ...emptyContinuity(),
              scene_id: next?.id || null,
              states:
                next?.objects.map((o) => ({
                  object_id: o.id,
                  visibility: 'visible',
                  position: o.home,
                  reason: '',
                })) || [],
            })
          }}
        >
          <option value="">未纳入连续性检查（兼容旧方案）</option>
          {scenes.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title}
            </option>
          ))}
        </select>
      </label>
      <label>
        制作方式
        <select
          value={c.method}
          onChange={(e) =>
            update({ ...c, method: e.target.value as Continuity['method'], reuse_asset_id: null })
          }
        >
          <option value="reuse">复用已有成图</option>
          <option value="edit">编辑上一幅画面</option>
          <option value="new_view">新机位／新视角</option>
        </select>
      </label>
      {c.method === 'reuse' && (
        <>
          <label>
            实际复用的成图
            <select
              value={c.reuse_asset_id || ''}
              onChange={(e) => update({ ...c, reuse_asset_id: e.target.value || null })}
            >
              <option value="">沿用本镜头已回填的图片</option>
              {c.reuse_asset_id &&
                !assets.some(
                  (a) => a.id === c.reuse_asset_id && a.kind === 'scene' && a.status !== 'rejected',
                ) && <option value={c.reuse_asset_id}>原选成图已失效，请重新选择</option>}
              {assetOptions(assets)}
            </select>
          </label>
          <div className="continuity-compare">
            {picture(c.reuse_asset_id || shot.image_asset_id, '实际复用成图')}
          </div>
          <p className="notice">
            {c.reuse_asset_id || shot.image_asset_id
              ? '直接使用这张成图；明确选择后会同步回填，不调用生图或编辑工具。'
              : '尚无复用目标，任务将暂停。请先选择成图或回填图片。'}
            场景母版仅供核对，不会自动成为复用成图。
          </p>
        </>
      )}
      {!scene ? (
        <p className="notice">此镜头尚未建立场景和道具状态，不能视为连续性已验证。</p>
      ) : (
        <>
          <div className="production-fields">
            <label>
              机位与画外范围
              <textarea
                value={c.camera}
                onChange={(e) => update({ ...c, camera: e.target.value })}
              />
            </label>
          </div>
          <label>
            本镜头允许改变什么
            <textarea
              value={c.changes}
              onChange={(e) => update({ ...c, changes: e.target.value })}
            />
          </label>
          <p>固定布局：{scene.layout}</p>
          {scene.objects.map((o, i) => {
            const state = states[i],
              prev = previous?.continuity.states.find((s) => s.object_id === o.id)
            const edit = (patch: Partial<ObjectState>) =>
              update({
                ...c,
                states: states.map((s) => (s.object_id === o.id ? { ...s, ...patch } : s)),
              })
            return (
              <details className="object-state" key={o.id}>
                <summary>
                  {o.name} ·{' '}
                  {state.visibility === 'visible'
                    ? '入画'
                    : state.visibility === 'offscreen'
                      ? '画外／遮挡'
                      : '尚未出现／已离开'}
                </summary>
                <p>
                  上一镜头：
                  {prev
                    ? `${prev.visibility === 'visible' ? '入画' : prev.visibility === 'offscreen' ? '画外／遮挡' : '未出现／离开'} · ${prev.position}`
                    : '本场景首次出现'}
                </p>
                <label>
                  可见状态
                  <select
                    value={state.visibility}
                    onChange={(e) =>
                      edit({ visibility: e.target.value as ObjectState['visibility'] })
                    }
                  >
                    <option value="visible">入画</option>
                    <option value="offscreen">画外／被遮挡，仍然存在</option>
                    {o.kind !== 'fixed' && <option value="absent">尚未出现／已离开</option>}
                  </select>
                </label>
                <label>
                  所在位置与当前形态
                  <textarea
                    value={state.position}
                    readOnly={o.kind === 'fixed'}
                    onChange={(e) => edit({ position: e.target.value })}
                  />
                </label>
                <label>
                  变化原因／移出画面依据
                  <textarea
                    value={state.reason}
                    onChange={(e) => edit({ reason: e.target.value })}
                  />
                </label>
              </details>
            )
          })}
          <div className="continuity-compare">
            {picture(scene.reference_asset_id, '场景母版')}
            {previous && picture(previous.image_asset_id, '前一镜头：' + previous.title)}
            {picture(shot.image_asset_id, '当前镜头：' + shot.title)}
          </div>
          {references.length > 0 && (
            <div className="continuity-compare" aria-label="本镜头使用的人物参考">
              {references.map((ref, index) => (
                <figure key={index}>
                  <figcaption>
                    {ref.name} · {ref.selection}
                  </figcaption>
                  {ref.url ? (
                    <a
                      href={ref.url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={'放大人物参考：' + ref.name}
                    >
                      <img src={ref.url} alt={ref.name + '的生图参考'} />
                    </a>
                  ) : (
                    <p>尚未选择参考</p>
                  )}
                  {!ref.valid && ref.url && (
                    <p className="notice">参考或人物尚未确认，请重新选择。</p>
                  )}
                  {ref.sha256 && (
                    <small title={ref.sha256}>图片校验值：{ref.sha256.slice(0, 12)}…</small>
                  )}
                </figure>
              ))}
            </div>
          )}
          <p>点击图片查看完整画面。检查记录只代表署名者看过这组图，不替代最终作品复核。</p>
          {shot.continuity_check ? (
            <p className="continuity-record" data-status={shot.continuity_check.status}>
              {{ passed: '已通过', rejected: '不通过', revoked: '已撤销', stale: '需复核' }[
                shot.continuity_check.status
              ] || '需复核'}{' '}
              · {shot.continuity_check.reviewer === 'assistant' ? '助手制作检查' : '创作者检查'} ·{' '}
              {shot.continuity_check.notes}
              {shot.continuity_check.invalidated_reason && (
                <> · {shot.continuity_check.invalidated_reason}</>
              )}
            </p>
          ) : (
            <p className="notice">
              待连续性检查{previous && !passed(previous) ? '；请先检查前一镜头。' : '。'}
            </p>
          )}
          <div className="continuity-checklist">
            {['固定空间与物件结构', '道具去向与出入画理由', '人物动作与光线衔接'].map((key) => (
              <label key={key}>
                <input
                  type="checkbox"
                  checked={checks.includes(key)}
                  onChange={(e) =>
                    changeDraft({
                      notes,
                      checks: e.target.checked ? [...checks, key] : checks.filter((k) => k !== key),
                    })
                  }
                />
                已核对{key}
              </label>
            ))}
          </div>
          <label>
            连续性检查说明／不通过或撤销原因
            <textarea
              value={notes}
              onChange={(e) => changeDraft({ checks, notes: e.target.value })}
              placeholder="记录检查结论或撤销原因，至少8个字；请明确选择下方结论"
            />
          </label>
          <button
            disabled={
              locked ||
              shot.status !== 'approved' ||
              !shot.image_asset_id ||
              !scene.reference_asset_id ||
              (!!previous && !passed(previous)) ||
              checks.length !== 3 ||
              notes.trim().length < 8
            }
            onClick={() => check(notes.trim(), 'passed')}
          >
            检查通过
          </button>
          <button
            disabled={locked || notes.trim().length < 8}
            onClick={() => check(notes.trim(), 'rejected')}
          >
            不通过
          </button>
          <button
            disabled={locked || !shot.continuity_check || notes.trim().length < 8}
            onClick={() => check(notes.trim(), 'revoked')}
          >
            撤销检查
          </button>
          <p>不通过或撤销会保存原因，并撤销同场景后续检查；再次通过后仍须逐幅复核。</p>
        </>
      )}
    </section>
  )
}
