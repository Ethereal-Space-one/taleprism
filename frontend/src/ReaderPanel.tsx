import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Job, type ReviewState } from './api'
import { ArrangementEditor } from './reader/ArrangementEditor'
import type { ReaderConfig, ReaderContent, ReaderState } from './reader-types'

function SceneForm({
  data,
  characters,
  pending,
  onSave,
}: {
  data: ReaderState
  characters: ReviewState['characters']
  pending: boolean
  onSave: (c: ReaderConfig) => void
}) {
  const [scenes, setScenes] = useState(data.config.scenes)
  const sceneAssets = data.assets.filter((a) => a.kind === 'scene' && a.status !== 'rejected')
  return (
    <form
      className="reader-scenes"
      onSubmit={(e) => {
        e.preventDefault()
        const f = new FormData(e.currentTarget)
        onSave({
          ...data.config,
          title: String(f.get('title')),
          subtitle: String(f.get('subtitle')),
          cover_asset_id: String(f.get('cover') || '') || null,
          map_profile: f.get('map') ? 'chibi' : null,
          scenes: [...scenes].sort((a, b) => a.start_byte - b.start_byte),
        })
      }}
    >
      <div className="reader-editor-layout">
        <label>
          章节名称
          <input name="title" maxLength={180} defaultValue={data.config.title} required />
        </label>
        <label>
          副标题
          <input name="subtitle" maxLength={180} defaultValue={data.config.subtitle} />
        </label>
        <label>
          章节封面
          <select name="cover" defaultValue={data.config.cover_asset_id || ''}>
            <option value="">暂不使用封面图</option>
            {data.assets
              .filter((a) => a.kind === 'cover' && a.status !== 'rejected')
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.sample_key || '上传封面'} · {a.status === 'accepted' ? '已接受' : '待确认'}
                </option>
              ))}
          </select>
        </label>
        <label className="inline-check">
          <input
            type="checkbox"
            name="map"
            disabled={!data.chibi_sample}
            defaultChecked={!!data.config.map_profile}
          />
          启用赤壁战区地图（仅适用完整样例）
        </label>
      </div>
      <h3>场景与起始段落</h3>
      <p className="asset-helper">
        背景持续到下一场景。首场景从卷首开始，保存时按原文位置排序；人物须先在人物页确认。
      </p>
      {scenes.map((scene, index) => (
        <section className="reader-scene-row" key={scene.id}>
          <label>
            场景名称
            <input
              required
              maxLength={80}
              value={scene.title}
              onChange={(e) =>
                setScenes((v) =>
                  v.map((s) => (s.id === scene.id ? { ...s, title: e.target.value } : s)),
                )
              }
            />
          </label>
          <label>
            起始段落
            <select
              value={scene.start_byte}
              onChange={(e) =>
                setScenes((v) =>
                  v.map((s) =>
                    s.id === scene.id ? { ...s, start_byte: Number(e.target.value) } : s,
                  ),
                )
              }
            >
              {data.paragraphs.map((p, i) => (
                <option key={p.byte_start} value={p.byte_start}>
                  第 {i + 1} 段 · {p.preview}
                </option>
              ))}
            </select>
          </label>
          <label>
            背景图片
            <select
              required
              value={scene.asset_id}
              onChange={(e) =>
                setScenes((v) =>
                  v.map((s) => (s.id === scene.id ? { ...s, asset_id: e.target.value } : s)),
                )
              }
            >
              {sceneAssets.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.sample_key || '上传背景'} · {a.status === 'accepted' ? '已接受' : '待确认'}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => setScenes((v) => v.filter((s) => s.id !== scene.id))}
          >
            移除场景 {index + 1}
          </button>
          <div className="scene-cast">
            {characters
              .filter((c) => c.status === 'confirmed')
              .map((c) => (
                <label key={c.id}>
                  <input
                    type="checkbox"
                    checked={scene.character_ids.includes(c.id)}
                    disabled={
                      !scene.character_ids.includes(c.id) && scene.character_ids.length >= 3
                    }
                    onChange={(e) =>
                      setScenes((v) =>
                        v.map((s) =>
                          s.id === scene.id
                            ? {
                                ...s,
                                character_ids: e.target.checked
                                  ? [...s.character_ids, c.id]
                                  : s.character_ids.filter((id) => id !== c.id),
                              }
                            : s,
                        ),
                      )
                    }
                  />
                  {c.display_name}
                </label>
              ))}
            {scene.character_ids
              .filter((id) => !characters.some((c) => c.id === id && c.status === 'confirmed'))
              .map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() =>
                    setScenes((v) =>
                      v.map((s) =>
                        s.id === scene.id
                          ? { ...s, character_ids: s.character_ids.filter((c) => c !== id) }
                          : s,
                      ),
                    )
                  }
                >
                  移除失效人物
                </button>
              ))}
          </div>
        </section>
      ))}
      <div className="visual-actions">
        <button
          type="button"
          disabled={!sceneAssets.length || scenes.length >= 64}
          onClick={() => {
            const start = data.paragraphs.find(
              (p) => !scenes.some((s) => s.start_byte === p.byte_start),
            )?.byte_start
            if (start !== undefined)
              setScenes((v) => [
                ...v,
                {
                  id: crypto.randomUUID(),
                  title: '新场景',
                  start_byte: start,
                  asset_id: sceneAssets[0].id,
                  character_ids: [],
                },
              ])
          }}
        >
          添加场景
        </button>
        <button className="primary" disabled={pending}>
          保存阅读器配置
        </button>
      </div>
    </form>
  )
}

export function ReaderPanel({ projectId, review }: { projectId: string; review?: ReviewState }) {
  const cache = useQueryClient()
  const state = useQuery({
    queryKey: ['reader', projectId],
    queryFn: () => api<ReaderState>(`/api/projects/${projectId}/reader`),
  })
  const content = useQuery({
    queryKey: ['reader-content', projectId],
    queryFn: () => api<ReaderContent>(`/api/projects/${projectId}/reader/content`),
  })
  const jobs = useQuery({
    queryKey: ['jobs', projectId],
    queryFn: () => api<Job[]>(`/api/projects/${projectId}/jobs`),
    refetchInterval: (q) => (q.state.data?.some((j) => j.state === 'running') ? 900 : false),
  })
  const change = useMutation({
    mutationFn: ({
      path,
      method = 'POST',
      body = {},
    }: {
      path: string
      method?: string
      body?: object | FormData
    }) =>
      api(`/api/projects/${projectId}/reader${path}`, {
        method,
        ...(body instanceof FormData
          ? { body }
          : {
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ revision: state.data?.revision, ...body }),
            }),
      }),
    onSuccess: async () => {
      await Promise.all([
        cache.invalidateQueries({ queryKey: ['reader', projectId] }),
        cache.invalidateQueries({ queryKey: ['reader-content', projectId] }),
        cache.invalidateQueries({ queryKey: ['jobs', projectId] }),
        cache.invalidateQueries({ queryKey: ['delivery', projectId] }),
      ])
    },
    onError: () => cache.invalidateQueries({ queryKey: ['reader', projectId] }),
  })
  const latest = jobs.data?.find((j) => j.kind === 'reader_export')
  const exported = jobs.data?.find((j) => j.kind === 'reader_export' && j.state === 'completed')
  const busy = change.isPending || latest?.state === 'running'
  const error = state.error || content.error || jobs.error || change.error
  const data = state.data
  const used = new Set([
    data?.config.cover_asset_id,
    ...(data?.config.scenes.map((s) => s.asset_id) || []),
  ])
  const pendingAssets =
    data?.assets.filter((a) => used.has(a.id) && a.status !== 'accepted').length || 0
  const stale =
    exported &&
    content.data &&
    Object.entries(content.data.versions).some(
      ([key, value]) => exported.result?.[key as keyof NonNullable<Job['result']>] !== value,
    )
  return (
    <section className="reader-editor" aria-label="阅读器制作">
      <div className="panel-head">
        <h2>阅读器与场景</h2>
        <a href={`/read/${projectId}`} target="_blank" rel="noreferrer">
          打开阅读预览 ↗
        </a>
      </div>
      <p className="asset-helper">
        按原段落连续阅读，封面与场景图持续展示，人物语音复用已接受片段。先预览，再接受图像并导出。
      </p>
      {error && (
        <p className="error" role="alert">
          {error.message}
        </p>
      )}
      {busy && <p role="status">正在保存或打包阅读器…</p>}
      {latest?.state === 'failed' && (
        <p className="error">上次导出未完成：{latest.error} 修复后可重新导出。</p>
      )}
      {data && (
        <>
          <div className="visual-actions">
            <button
              disabled={busy || !data.chibi_sample}
              onClick={() => change.mutate({ path: '/sample' })}
            >
              导入赤壁封面与场景候选
            </button>
            <button
              disabled={
                busy ||
                content.isPending ||
                !!content.error ||
                pendingAssets > 0 ||
                !!content.data?.issues.length
              }
              className="primary"
              onClick={() => change.mutate({ path: '/exports' })}
            >
              导出独立阅读器
            </button>
          </div>
          {!!pendingAssets && (
            <p className="asset-helper">
              当前使用的 {pendingAssets} 张图片仍需接受；阅读预览可以查看待确认素材。
            </p>
          )}
          {content.data?.issues.map((issue, i) => (
            <p className="error" key={i}>
              {issue}
            </p>
          ))}
          {exported?.result && (
            <div className="export-result">
              <span>
                {stale
                  ? '制作状态已变，下方为旧版阅读器。'
                  : '✓ 阅读器已导出，原文与资源检查通过。'}
              </span>
              <div>
                <a href={exported.result.play_url} target="_blank" rel="noreferrer">
                  打开成品 ↗
                </a>
                <a href={exported.result.download_url}>下载阅读器 ↓</a>
              </div>
            </div>
          )}
          <details className="visual-edit-details">
            <summary>编辑封面、场景与人物</summary>
            <SceneForm
              key={data.revision}
              data={data}
              characters={review?.characters || []}
              pending={busy}
              onSave={(body) => change.mutate({ path: '', method: 'PATCH', body })}
            />
          </details>
          <details className="visual-edit-details">
            <summary>上传自己的封面或背景</summary>
            <form
              className="visual-upload"
              onSubmit={(e) => {
                e.preventDefault()
                const form = new FormData(e.currentTarget)
                form.set('revision', String(data.revision))
                change.mutate({ path: '/assets', body: form })
              }}
            >
              <label>
                素材类型
                <select name="kind">
                  <option value="scene">场景背景</option>
                  <option value="cover">章节封面</option>
                </select>
              </label>
              <label>
                图片文件
                <input type="file" name="file" required accept="image/png,image/jpeg,image/webp" />
              </label>
              <label>
                来源与许可
                <input name="license_text" maxLength={1000} required />
              </label>
              <button disabled={busy}>上传为候选图</button>
            </form>
          </details>
          {content.data && (
            <ArrangementEditor
              projectId={projectId}
              state={data}
              review={review}
              content={content.data}
            />
          )}
          <h3>素材审查</h3>
          <div className="reader-asset-grid">
            {data.assets.map((a) => (
              <figure key={a.id}>
                <img
                  src={a.url}
                  loading="lazy"
                  alt={`${a.kind === 'cover' ? '章节封面' : '场景背景'} ${a.sample_key || ''}`}
                />
                <figcaption>
                  {a.sample_key || (a.kind === 'cover' ? '上传封面' : '上传背景')} ·{' '}
                  {a.status === 'accepted'
                    ? '已接受'
                    : a.status === 'rejected'
                      ? '已拒绝'
                      : '待确认'}
                </figcaption>
                <div className="visual-actions">
                  <button
                    disabled={busy || a.status === 'accepted'}
                    onClick={() =>
                      change.mutate({
                        path: `/assets/${a.id}`,
                        method: 'PATCH',
                        body: { status: 'accepted' },
                      })
                    }
                  >
                    接受此图
                  </button>
                  <button
                    disabled={busy || a.status === 'rejected'}
                    onClick={() =>
                      change.mutate({
                        path: `/assets/${a.id}`,
                        method: 'PATCH',
                        body: { status: 'rejected' },
                      })
                    }
                  >
                    拒绝
                  </button>
                </div>
              </figure>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
