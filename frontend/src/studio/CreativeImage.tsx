import { useState, type FormEvent } from 'react'
import { api } from '../api'
import type { ReaderAsset, ReaderState } from '../reader-types'
import type { Idea } from './creativeTypes'
import type { Act } from './CreativeDesk'

export function CreativeImage({
  idea,
  projectId,
  data,
  act,
  blocked,
  refresh,
  tell,
}: {
  idea: Idea
  projectId: string
  data: ReaderState
  act: Act
  blocked: boolean
  refresh: () => Promise<void>
  tell: (s: string) => void
}) {
  const [choice, setChoice] = useState(''),
    [seen, setSeen] = useState(''),
    [title, setTitle] = useState(''),
    [alt, setAlt] = useState(''),
    [broken, setBroken] = useState(false)
  const asset = data.assets.find(
    (a) => a.id === choice && a.kind === 'scene' && a.status !== 'rejected',
  )
  const paragraph = data.paragraphs[(idea.later?.paragraph || 1) - 1],
    at = paragraph?.byte_end
  const occupied = data.config.illustrations?.find((p) => p.after_byte === at),
    prefix = '/api/projects/' + projectId + '/reader'
  const key = asset ? asset.id + ':' + asset.sha256 : ''
  function select(id: string) {
    setSeen('')
    setBroken(false)
    setChoice(id)
  }
  function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget,
      fields = new FormData(form),
      file = fields.get('file')
    void act(async () => {
      if (!(file instanceof File) || !file.size || file.size > 12_000_000)
        throw Error('请选择不超过 12 MB 的非空 PNG、JPEG 或 WebP 图。')
      fields.set('revision', String(data.revision))
      fields.set('kind', 'scene')
      const newAsset = await api<ReaderAsset>(prefix + '/assets', { method: 'POST', body: fields })
      await refresh()
      select(newAsset.id)
      form.reset()
      tell('候选图已保存，尚未接受。请先看实际画面。')
    })
  }
  async function accept() {
    if (!asset || seen !== key || broken) return
    await act(async () => {
      await api(prefix + '/assets/' + asset.id, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision: data.revision, status: 'accepted' }),
      })
      await refresh()
      tell('底图已接受，但尚未放入正文。')
    })
  }
  async function place() {
    if (
      !asset ||
      seen !== key ||
      broken ||
      asset.status !== 'accepted' ||
      !title.trim() ||
      !alt.trim() ||
      occupied ||
      !paragraph
    )
      return
    await act(async () => {
      const plate = {
        id: crypto.randomUUID(),
        after_byte: at,
        image_asset_id: asset.id,
        title: title.trim(),
        description: alt.trim(),
        motion: null,
      }
      await api(prefix, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...data.config,
          revision: data.revision,
          reading_layout: 'illustrated',
          illustrations: [...(data.config.illustrations || []), plate].sort(
            (a, b) => a.after_byte - b.after_byte,
          ),
        }),
      })
      await refresh()
      tell(
        '插图已放在选定原文段后，仍是静图。请到「逐幅动静审图」记录判断；只有另行导演、复核的动效才会播放。',
      )
    })
  }
  return (
    <div className="creative-image">
      <h4>用实际底图试构图</h4>
      {idea.image !== 'still' && (
        <p>
          这只是动效思路，没有底图不能判断范围。先放静图；要让雨或浪动起来，须到章节编排的动效导演里划区、预览并复核。
        </p>
      )}
      {occupied ? (
        <p>
          第 {idea.later?.paragraph} 段后已有「{occupied.title}
          」。不会覆盖它；可到章节编排检查或调整。
        </p>
      ) : (
        <fieldset disabled={blocked}>
          <label>
            选择工程中的图
            <select value={choice} onChange={(e) => select(e.target.value)}>
              <option value="">选择一张实际底图</option>
              {data.assets
                .filter((a) => a.kind === 'scene' && a.status !== 'rejected')
                .map((a, i) => (
                  <option key={a.id} value={a.id}>
                    图 {i + 1} · {a.width}×{a.height} · {a.license.slice(0, 40)}（
                    {a.status === 'accepted' ? '已接受' : '待审'}）
                  </option>
                ))}
            </select>
          </label>
          <details className="creative-import">
            <summary>上传有权使用的候选图</summary>
            <form onSubmit={upload}>
              <label>
                候选图文件
                <input type="file" name="file" accept="image/png,image/jpeg,image/webp" required />
              </label>
              <label>
                来源与许可
                <input name="license_text" required maxLength={1000} />
              </label>
              <button type="submit">保存候选图，不放置</button>
            </form>
          </details>
          {asset && (
            <>
              <img
                className="creative-art-preview"
                key={key}
                src={asset.url}
                alt="供作者核对的实际底图"
                onLoad={() => {
                  setSeen(key)
                  setBroken(false)
                }}
                onError={() => {
                  setSeen('')
                  setBroken(true)
                }}
              />
              {broken && <p role="alert">底图无法显示，不能接受或放置。请重选或重新上传。</p>}
              {asset.status === 'pending' ? (
                <button
                  disabled={seen !== key || broken}
                  type="button"
                  onClick={() => void accept()}
                >
                  已看过这张图，接受底图
                </button>
              ) : (
                <>
                  <label>
                    读者看见的图名
                    <input
                      maxLength={80}
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
                  </label>
                  <label>
                    画面替代文字
                    <textarea
                      rows={2}
                      maxLength={300}
                      value={alt}
                      onChange={(e) => setAlt(e.target.value)}
                      placeholder="只描述实际画面，不写尚未发生的事。"
                    />
                  </label>
                  <small>采用后将使用画卷排布；其余插图和原文不动。</small>
                  <button
                    type="button"
                    disabled={seen !== key || broken || !title.trim() || !alt.trim()}
                    onClick={() => void place()}
                  >
                    采用静图，放在第 {idea.later?.paragraph} 段后
                  </button>
                </>
              )}
            </>
          )}
        </fieldset>
      )}
    </div>
  )
}
