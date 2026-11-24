import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useState } from 'react'
import { useUnsavedWarning } from './studio/leave'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Job, type ReviewState } from './api'
import { CreativeDesk } from './studio/CreativeDesk'
import { PassageSoundscape } from './studio/PassageSoundscape'
import { PassageVoice } from './studio/PassageVoice'
import { BundleBackup } from './BundleBackup'
import { PlateScreening } from './PlateScreening'
import { ArrangementEditor } from './reader/ArrangementEditor'
import type { ReaderConfig, ReaderContent, ReaderState } from './reader-types'

function sceneFields(config: ReaderConfig) {
  const { title, subtitle, cover_asset_id, map_profile, scenes } = config
  return { title, subtitle, cover_asset_id, map_profile, scenes }
}

function SceneForm({
  data,
  characters,
  pending,
  onSave,
  onDirty,
}: {
  data: ReaderState
  characters: ReviewState['characters']
  pending: boolean
  onSave: (c: ReaderConfig, revision: number) => Promise<unknown>
  onDirty: (value: boolean) => void
}) {
  const [base, setBase] = useState(() => sceneFields(data.config))
  const [draft, setDraft] = useState(base)
  const same = (a: typeof base, b: typeof base) => JSON.stringify(a) === JSON.stringify(b)
  const dirty = !same(draft, base)
  const conflict = !same(sceneFields(data.config), base)
  useLayoutEffect(() => onDirty(dirty), [dirty, onDirty])
  useEffect(() => {
    if (!dirty && conflict) {
      const next = sceneFields(data.config)
      setDraft(next)
      setBase(next)
    }
  }, [data.config, dirty, conflict])
  const scenes = draft.scenes
  const setScenes = (update: (scenes: ReaderConfig['scenes']) => ReaderConfig['scenes']) =>
    setDraft((v) => ({ ...v, scenes: update(v.scenes) }))
  async function save() {
    if (!dirty || conflict || pending) return
    const snapshot = {
      ...draft,
      scenes: [...draft.scenes].sort((a, b) => a.start_byte - b.start_byte),
    }
    try {
      await onSave({ ...data.config, ...snapshot }, data.revision)
      setBase(snapshot)
      setDraft(snapshot)
    } catch {
      /* Mutation error is shown by ReaderPanel. Preserve every input for retry. */
    }
  }
  function reload() {
    if (dirty && !window.confirm('放弃尚未保存的章节设置，载入已保存的版本？')) return
    const next = sceneFields(data.config)
    setBase(next)
    setDraft(next)
  }
  const sceneAssets = data.assets.filter((a) => a.kind === 'scene' && a.status !== 'rejected')
  return (
    <form
      className="reader-scenes"
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <div className="reader-editor-layout">
        <label>
          章节名称
          <input
            name="title"
            maxLength={180}
            value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            required
          />
        </label>
        <label>
          副标题
          <input
            name="subtitle"
            maxLength={180}
            value={draft.subtitle}
            onChange={(e) => setDraft({ ...draft, subtitle: e.target.value })}
          />
        </label>
        <label>
          章节封面
          <select
            name="cover"
            value={draft.cover_asset_id || ''}
            onChange={(e) => setDraft({ ...draft, cover_asset_id: e.target.value || null })}
          >
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
            checked={!!draft.map_profile}
            onChange={(e) => setDraft({ ...draft, map_profile: e.target.checked ? 'chibi' : null })}
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
        <button className="primary" disabled={pending || !dirty || conflict}>
          保存阅读器配置
        </button>
        {dirty && (
          <button type="button" disabled={pending} onClick={reload}>
            放弃未保存的章节设置
          </button>
        )}
        {dirty && conflict && (
          <p role="alert">
            章节设置已在别处更改。你的输入保留在这里；请复制需要的内容，再载入已保存版本，不能覆盖他人的修改。
          </p>
        )}
      </div>
    </form>
  )
}

export function ReaderPanel({
  projectId,
  review,
  studioPlateId,
  voiceOnly = false,
  soundFirst = false,
  finishOnly = false,
  studioActive = true,
  onVoiceWriting,
  onGuardChange,
}: {
  projectId: string
  review?: ReviewState
  studioPlateId?: string
  voiceOnly?: boolean
  soundFirst?: boolean
  finishOnly?: boolean
  studioActive?: boolean
  onVoiceWriting?: (v: boolean) => void
  onGuardChange?: (guard: { dirty: boolean; writing: boolean }) => void
}) {
  const [screenDirty, setScreenDirty] = useState(false),
    [screenWriting, setScreenWriting] = useState(false)
  const screenGuard = useCallback((dirty: boolean, writing: boolean) => {
    setScreenDirty(dirty)
    setScreenWriting(writing)
  }, [])
  const [creativeWriting, setCreativeWriting] = useState(false)
  const [creativeSoundTarget, setCreativeSoundTarget] = useState<{ anchor: number; seq: number }>()
  const [voiceAnchor, setVoiceAnchor] = useState<number>()
  const studio = !!studioPlateId || voiceOnly
  const [voiceWriting, setVoiceWriting] = useState(false)
  const [arrangementDirty, setArrangementDirty] = useState(false)
  const [arrangementWriting, setArrangementWriting] = useState(false)
  const [sceneDirty, setSceneDirty] = useState(false),
    [voiceDirty, setVoiceDirty] = useState(false)
  const [soundWriting, setSoundWriting] = useState(false),
    [soundDirty, setSoundDirty] = useState(false)
  const soundSectionId = useId(),
    [soundRepairRequest, setSoundRepairRequest] = useState(0)
  const voiceSectionId = useId()
  const [voiceRepairRequest, setVoiceRepairRequest] = useState(0)
  const arrangementState = useCallback((dirty: boolean, writing: boolean) => {
    setArrangementDirty(dirty)
    setArrangementWriting(writing)
  }, [])

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
        cache.invalidateQueries({ queryKey: ['narrations', projectId] }),
        cache.invalidateQueries({ queryKey: ['soundscapes', projectId] }),
      ])
    },
    onError: () => cache.invalidateQueries({ queryKey: ['reader', projectId] }),
  })
  const voiceIssue = !!content.data?.issues.some((issue) => issue.includes('朗读'))
  const blocks = voiceIssue ? content.data?.blocks : undefined
  const publishedVoiceIds = useMemo(
    () => blocks && new Set(blocks.flatMap((b) => (b.narration ? [b.narration.id] : []))),
    [blocks],
  )
  const soundIssue = !!content.data?.issues.some((i) => i.includes('声景'))
  const soundBlocks = soundIssue ? content.data?.blocks : undefined
  const publishedSounds = useMemo(
    () =>
      soundBlocks && new Set(soundBlocks.flatMap((b) => (b.soundscape ? [b.soundscape.id] : []))),
    [soundBlocks],
  )
  const latest = jobs.data?.find((j) => j.kind === 'reader_export')
  const exported = jobs.data?.find((j) => j.kind === 'reader_export' && j.state === 'completed')
  const writing =
    screenWriting ||
    creativeWriting ||
    soundWriting ||
    voiceWriting ||
    arrangementWriting ||
    change.isPending
  const dirty = screenDirty || soundDirty || arrangementDirty || sceneDirty || voiceDirty
  const busy = dirty || writing || latest?.state === 'running'
  useUnsavedWarning(dirty || writing)
  useLayoutEffect(
    () =>
      onVoiceWriting?.(
        voiceWriting || soundWriting || creativeWriting || screenWriting || screenDirty,
      ),
    [voiceWriting, soundWriting, creativeWriting, screenWriting, screenDirty, onVoiceWriting],
  )
  useLayoutEffect(() => {
    onGuardChange?.({ dirty, writing })
    return () => onGuardChange?.({ dirty: false, writing: false })
  }, [dirty, writing, onGuardChange])
  const error = state.error || content.error || jobs.error || change.error
  const data = state.data
  const used = new Set([
    data?.config.cover_asset_id,
    ...(data?.config.scenes.map((s) => s.asset_id) || []),
    ...(data?.config.presentations?.map((p) => p.image_asset_id) || []),
    ...(data?.config.illustrations?.map((p) => p.image_asset_id) || []),
  ])
  const pendingAssets =
    data?.assets.filter((a) => used.has(a.id) && a.status !== 'accepted').length || 0
  const stale =
    exported &&
    content.data &&
    Object.entries(content.data.versions).some(
      ([key, value]) => exported.result?.[key as keyof NonNullable<Job['result']>] !== value,
    )
  const studioPlate = data?.config.illustrations?.find((p) => p.id === studioPlateId)
  const studioAnchor = voiceOnly
    ? voiceAnchor
    : studioPlate && data?.paragraphs.find((p) => p.byte_end === studioPlate.after_byte)?.byte_start
  return (
    <section
      className="reader-editor"
      aria-label="阅读器制作"
      onPlayCapture={(e) => {
        e.currentTarget.querySelectorAll('audio').forEach((a) => {
          if (a !== e.target) a.pause()
        })
      }}
    >
      {data && (
        <PlateScreening
          projectId={projectId}
          readerRevision={data.revision}
          onGuard={screenGuard}
          locked={
            soundDirty ||
            arrangementDirty ||
            sceneDirty ||
            voiceDirty ||
            (writing && !screenWriting) ||
            latest?.state === 'running'
          }
        />
      )}
      {studioPlateId && data && content.data && (
        <fieldset disabled={soundWriting || soundDirty || voiceWriting || voiceDirty}>
          <ArrangementEditor
            projectId={projectId}
            state={data}
            content={content.data}
            studioPlateId={studioPlateId}
            onDraftState={arrangementState}
          />
        </fieldset>
      )}
      {data && (
        <div id={voiceSectionId}>
          <PassageVoice
            projectId={projectId}
            paragraphs={data.paragraphs}
            initiallyOpen={voiceOnly && !soundFirst && !finishOnly}
            repairRequest={voiceRepairRequest}
            published={publishedVoiceIds}
            visible={studioActive}
            locked={
              creativeWriting ||
              soundDirty ||
              soundWriting ||
              arrangementDirty ||
              arrangementWriting ||
              sceneDirty ||
              change.isPending ||
              latest?.state === 'running'
            }
            onDraftDirty={setVoiceDirty}
            onAnchor={setVoiceAnchor}
            onWriting={setVoiceWriting}
          />
        </div>
      )}
      {data && (
        <div id={soundSectionId}>
          <PassageSoundscape
            projectId={projectId}
            paragraphs={data.paragraphs}
            initiallyOpen={voiceOnly && soundFirst}
            visible={studioActive}
            locked={
              creativeWriting ||
              voiceDirty ||
              voiceWriting ||
              arrangementDirty ||
              arrangementWriting ||
              sceneDirty ||
              change.isPending ||
              latest?.state === 'running'
            }
            onDirty={setSoundDirty}
            onWriting={setSoundWriting}
            onAnchor={setVoiceAnchor}
            published={publishedSounds}
            repairRequest={soundRepairRequest}
            creativeTarget={creativeSoundTarget}
          />
        </div>
      )}
      <div className="panel-head">
        <h2>{studio ? '试读与交付' : '独立阅读器'}</h2>
        <a
          href={`/read/${projectId}${studioAnchor === undefined ? '' : `?at=${studioAnchor}`}`}
          target="_blank"
          rel="noreferrer"
        >
          打开阅读预览 ↗
        </a>
      </div>
      <p className="asset-helper">
        {studio
          ? voiceOnly
            ? '不需要插图也能试读和交付。阅读包只含已采用的朗读或声景；待审素材和私有依据不公开。'
            : '预览与导出使用已保存的版本。静图保持静止；只有已复核的动效才随阅读呈现。读者可暂停自动演绎或选择安静阅读。'
          : '阅读包给读者：只包含已保存的编排、应交付的素材和已采用的声音。可编辑工程给继续制作的人，保留草稿和历史，不是同一份 ZIP。'}
      </p>
      {dirty && (
        <p className="notice" role="status">
          有未保存的
          {screenDirty
            ? '逐幅审图输入'
            : soundDirty
              ? '声景设置'
              : sceneDirty
                ? '章节设置'
                : arrangementDirty
                  ? '章节编排、动效或位置意见'
                  : '本机录音输入'}
          。预览只反映已保存版本；请先保存或明确放弃，再导出或切换。
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error.message}
        </p>
      )}
      {(change.isPending || latest?.state === 'running') && (
        <p role="status">正在保存或打包阅读器…</p>
      )}
      {latest?.state === 'failed' && (
        <p className="error">上次导出未完成：{latest.error} 修复后可重新导出。</p>
      )}
      {data && (
        <>
          <div className="visual-actions">
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
            {!studio && data.chibi_sample && (
              <button disabled={busy} onClick={() => change.mutate({ path: '/sample' })}>
                导入赤壁封面与场景候选
              </button>
            )}
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
          {voiceIssue && (
            <button
              type="button"
              disabled={writing || dirty}
              onClick={() => {
                setVoiceRepairRequest((n) => n + 1)
                const details = document.getElementById(voiceSectionId)?.querySelector('details')
                if (details) {
                  details.open = true
                  details.querySelector('summary')?.focus()
                  details.scrollIntoView({ block: 'start' })
                }
              }}
            >
              定位段落朗读，替换或撤下
            </button>
          )}
          {soundIssue && (
            <button
              type="button"
              disabled={writing || dirty}
              onClick={() => {
                setSoundRepairRequest((n) => n + 1)
                const d = document.getElementById(soundSectionId)?.querySelector('details')
                if (d) {
                  d.open = true
                  d.querySelector('summary')?.focus()
                  d.scrollIntoView({ block: 'start' })
                }
              }}
            >
              定位段落声景，替换或撤下
            </button>
          )}
          {exported?.result && (
            <div className="export-result">
              <span>
                {dirty && !stale
                  ? '这是上次保存版本的阅读包，不包含当前草稿。'
                  : stale
                    ? '制作状态已变，下方为旧版阅读器。'
                    : '✓ 阅读器已导出，原文与资源检查通过。'}
              </span>
              <div>
                <a href={exported.result.play_url} target="_blank" rel="noreferrer">
                  打开导出版 ↗
                </a>
                <a href={exported.result.download_url}>下载阅读器 ↓</a>
              </div>
            </div>
          )}
          <BundleBackup projectId={projectId} disabled={busy} />
          {!studio && (
            <>
              <details className="visual-edit-details">
                <summary>编辑封面、场景与人物</summary>
                <fieldset
                  className="reader-form-guard"
                  disabled={arrangementDirty || soundDirty || voiceDirty || writing}
                >
                  <SceneForm
                    data={data}
                    characters={review?.characters || []}
                    pending={writing}
                    onDirty={setSceneDirty}
                    onSave={(body, revision) =>
                      change.mutateAsync({ path: '', method: 'PATCH', body: { ...body, revision } })
                    }
                  />
                </fieldset>
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
                    <input
                      type="file"
                      name="file"
                      required
                      accept="image/png,image/jpeg,image/webp"
                    />
                  </label>
                  <label>
                    来源与许可
                    <input name="license_text" maxLength={1000} required />
                  </label>
                  <button disabled={busy}>上传为候选图</button>
                </form>
              </details>
              {content.data && (
                <fieldset
                  className="reader-form-guard"
                  disabled={
                    soundWriting ||
                    soundDirty ||
                    voiceWriting ||
                    voiceDirty ||
                    sceneDirty ||
                    change.isPending
                  }
                >
                  <ArrangementEditor
                    projectId={projectId}
                    state={data}
                    review={review}
                    content={content.data}
                    onDraftState={arrangementState}
                  />
                </fieldset>
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
                        disabled={
                          writing ||
                          arrangementDirty ||
                          soundDirty ||
                          voiceDirty ||
                          latest?.state === 'running' ||
                          a.status === 'accepted'
                        }
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
                        disabled={
                          writing ||
                          arrangementDirty ||
                          soundDirty ||
                          voiceDirty ||
                          latest?.state === 'running' ||
                          a.status === 'rejected'
                        }
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
        </>
      )}
      {data && (
        <CreativeDesk
          projectId={projectId}
          data={data}
          locked={
            soundWriting ||
            voiceWriting ||
            arrangementWriting ||
            change.isPending ||
            dirty ||
            latest?.state === 'running'
          }
          onWriting={setCreativeWriting}
          onSoundReview={(anchor) => {
            setCreativeSoundTarget((old) => ({ anchor, seq: (old?.seq ?? 0) + 1 }))
            const d = document.getElementById(soundSectionId)?.querySelector('details')
            if (d) {
              d.open = true
              d.querySelector('summary')?.focus()
              d.scrollIntoView({ block: 'start' })
            }
          }}
        />
      )}
    </section>
  )
}
