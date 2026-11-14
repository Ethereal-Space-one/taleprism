import { useRef, useState } from 'react'
import { api } from './api'
import type { ReaderAsset, ReaderState } from './reader-types'
import './shot-exchange.css'

export type ImageTask = {
  id: string
  readiness: 'blocked' | 'draft' | 'ready'
  generation_ready: boolean
  readiness_issues: string[]
  reference_files: {
    asset_id: string
    role: string
    label: string
    sha256: string | null
    available: boolean
    url?: string
  }[]
}
export type ImageTasks = { plan_revision: number; tasks: ImageTask[] }
const roleName = (role: string) =>
  ({
    'environment master': '场景母版',
    'character identity': '人物身份参考',
    'reuse target': '复用成图',
    'previous checked frame': '前序已检查图片',
    'edit target / previous checked frame': '编辑底图 · 前序已检查图片',
  })[role] || role

export function ShotExchange({
  prefix,
  shot,
  task,
  revision,
  reader,
  locked,
  stale,
  pending,
  bind,
  setBusy,
  refresh,
}: {
  prefix: string
  shot: {
    id: string
    title: string
    image_asset_id: string | null
    continuity: { method: string; reuse_asset_id: string | null }
  }
  task?: ImageTask
  revision: number
  reader: ReaderState
  locked: boolean
  stale: boolean
  pending: boolean
  bind: (id: string) => void
  setBusy: (busy: boolean) => boolean
  refresh: () => Promise<void>
}) {
  const inFlight = useRef(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [candidate, setCandidate] = useState<ReaderAsset | null>(null)
  const bound = reader.assets.find((a) => a.id === shot.image_asset_id)
  const validBound = bound && bound.kind === 'scene' && bound.status !== 'rejected'
  const canBind =
    !pending && !(shot.continuity.method === 'reuse' && shot.continuity.reuse_asset_id)

  async function upload(form: HTMLFormElement) {
    if (inFlight.current || pending || stale) return
    const data = new FormData(form)
    const file = data.get('file')
    if (!(file instanceof File) || !file.size) return
    if (file.size > 12_000_000) {
      setError('请选择不超过 12 MB 的图像。')
      return
    }
    const origin = String(data.get('license_text') || '').trim()
    if (!origin) {
      setError('请填写图片来源与使用许可。')
      return
    }
    if (!setBusy(true)) return
    inFlight.current = true
    setError('')
    setMessage('正在上传候选图，尚未绑定镜头…')
    try {
      // Upload adds an asset, never rewrites the reader arrangement. Its own CAS still applies.
      const current = await api<ReaderState>(prefix + '/reader')
      data.set('revision', String(current.revision))
      data.set('kind', 'scene')
      data.set(
        'license_text',
        `镜头「${shot.title}」 · ${file.name.slice(0, 150)}\n来源与许可：${origin}`,
      )
      const result = await api<ReaderAsset>(prefix + '/reader/assets', {
        method: 'POST',
        body: data,
      })
      setCandidate({ ...result, url: `${prefix}/reader/assets/${result.id}` })
      setMessage('候选图已上传。请查看预览，再选择“绑定到此镜头”。尚未接受图片或通过检查。')
      form.reset()
      await refresh()
    } catch (e) {
      setError((e as Error).message)
      setMessage('')
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return (
    <section className="shot-exchange" aria-label={`${shot.title}的素材任务与回填`}>
      <div className="shot-exchange-head">
        <div>
          <p className="shot-exchange-eyebrow">同一镜头 · 素材任务与回填</p>
          <h3>带着依据出发，带回候选图。</h3>
        </div>
        <span
          className={`shot-readiness ${locked || stale ? 'unavailable' : task?.readiness || 'unavailable'}`}
        >
          {locked || stale
            ? '本地修改尚未保存／版本待核对'
            : !task
              ? '任务状态待核对'
              : task.readiness === 'blocked'
                ? '未就绪 · 需补全依据'
                : task.readiness === 'draft'
                  ? '待审草稿 · 不是生成许可'
                  : '任务已就绪 · 尚非成图验收'}
        </span>
      </div>
      {task && !locked && !stale && task.readiness_issues.length > 0 && (
        <ul className="shot-readiness-issues">
          {task.readiness_issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}
      {(locked || stale) && (
        <p className="shot-reference-empty">
          以下缩略图来自已保存版本，不代表当前未保存的选图。保存并核对版本后，任务包才会更新。
        </p>
      )}
      <div className="shot-reference-strip">
        {task?.reference_files.map((ref, i) => (
          <figure key={`${ref.asset_id}-${ref.role}-${i}`}>
            {ref.available && ref.url ? (
              <a href={ref.url} target="_blank" rel="noreferrer">
                <img src={ref.url} alt={`${roleName(ref.role)}：${ref.label}`} loading="lazy" />
              </a>
            ) : (
              <div className="shot-reference-missing">参考不可用</div>
            )}
            <figcaption>
              {roleName(ref.role)}
              <small>{ref.label}</small>
              <small>{ref.sha256?.slice(0, 12) || '未取得图片校验值'}</small>
            </figcaption>
          </figure>
        ))}
        {(!task || task.reference_files.length === 0) && (
          <p className="shot-reference-empty">
            当前没有可携带的参考图。无人物的首图可建立场景；在场人物必须先补齐身份参考。
          </p>
        )}
      </div>
      <div className="shot-exchange-download">
        <a
          href={`${prefix}/production/${shot.id}/kit?revision=${revision}`}
          aria-disabled={locked || stale || pending || !task}
          onClick={(e) => {
            if (locked || stale || pending || !task) e.preventDefault()
          }}
        >
          下载此镜头任务包 ZIP ↓
        </a>
        <p>
          包含现有提示词、原文锚点、实际参考图及逐文件
          SHA-256、图片职责和来源。草稿包会明确标注未就绪，不调用 AI。
        </p>
      </div>
      <details className="shot-upload-details">
        <summary>把外部工具生成的图片带回此镜头</summary>
        <form
          className="shot-upload-form"
          onSubmit={(e) => {
            e.preventDefault()
            void upload(e.currentTarget)
          }}
        >
          <label>
            候选图片
            <input
              name="file"
              type="file"
              required
              accept="image/png,image/jpeg,image/webp"
              disabled={pending || stale}
            />
          </label>
          <label>
            来源与使用许可
            <input
              name="license_text"
              required
              maxLength={700}
              placeholder="例如：使用我的参考图生成，允许用于本作品"
              disabled={pending || stale}
            />
          </label>
          <button type="submit" disabled={pending || stale}>
            上传为候选图
          </button>
        </form>
        <p>
          支持 PNG、JPEG、WebP，最长边 4096 像素，最大 12
          MB。上传后预览，再明确绑定；不会自动接受或通过检查。
        </p>
        {candidate && (
          <figure className="shot-upload-candidate">
            <img src={candidate.url} alt={`新上传候选：${shot.title}`} />
            <figcaption>
              {candidate.license.split('\n')[0]} · 待审 · {candidate.sha256.slice(0, 12)}
            </figcaption>
            <button
              type="button"
              disabled={!canBind || stale || candidate.id === shot.image_asset_id}
              onClick={() => {
                bind(candidate.id)
                setMessage('已绑定为本地镜头草稿，请保存方案，再重新确认与检查。')
              }}
            >
              绑定到此镜头
            </button>
          </figure>
        )}
        {shot.continuity.method === 'reuse' && shot.continuity.reuse_asset_id && (
          <p>当前镜头指定了复用成图。若要使用新候选，请先更改下方复用选择或制作方式。</p>
        )}
      </details>
      {bound && (
        <figure className="shot-bound-preview">
          <img src={bound.url} alt={`${shot.title}当前回填图片`} />
          <figcaption>
            当前回填：{bound.label || bound.license.split('\n')[0] || '镜头图片'} ·{' '}
            {bound.status === 'accepted'
              ? '图片已接受，仍需镜头检查'
              : bound.status === 'rejected'
                ? '已拒绝，请重新选择'
                : '图片待审，绑定不等于接受'}
          </figcaption>
        </figure>
      )}
      {shot.image_asset_id && !validBound && (
        <p className="error" role="alert">
          当前回填图片缺失或已拒绝。请重新选择，不能作为已就绪依据。
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  )
}
