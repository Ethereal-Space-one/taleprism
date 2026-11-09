import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Job } from './api'

type Take = { id: string; url: string; duration: number }
type Segment = {
  key: string
  original: string
  spoken: string
  candidate: Take | null
  accepted: Take | null
}
type Profile = { voice: string; speed: number; provider?: string; instructions?: string }
type Provider = {
  provider: string
  label: string
  available: boolean
  voices: string[]
  reason?: string
}
type SpeechLine = {
  id: string
  speaker_id: string | null
  speaker_name: string | null
  text: string
  eligible: boolean
  selected: boolean
  profile: Profile | null
  instructions: string
  overrides: Record<string, string>
  segments: Segment[]
}
export type SpeechState = {
  revision: number
  lines: SpeechLine[]
  profiles: Record<string, Profile>
  capabilities: { available: boolean; voices: string[] }
  providers: Provider[]
}

function VoiceProfile({
  name,
  profile,
  providers,
  busy,
  save,
}: {
  name: string
  profile?: Profile
  providers: Provider[]
  busy: boolean
  save: (p: Profile) => void
}) {
  const [provider, setProvider] = useState(profile?.provider || 'macos-say')
  const cap = providers.find((p) => p.provider === provider) || providers[0]
  const remote = provider === 'openai-realtime'
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        const f = new FormData(e.currentTarget)
        save({
          provider,
          voice: String(f.get('voice')),
          speed: Number(f.get('speed')),
          instructions: remote ? String(f.get('instructions') || '') : '',
        })
      }}
    >
      <h3>{name}</h3>
      <label>
        配音方式
        <select
          aria-label={`${name}配音方式`}
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        >
          {providers.map((p) => (
            <option key={p.provider} value={p.provider}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        音色
        <select
          key={provider}
          name="voice"
          required
          defaultValue={
            profile?.provider === provider || (!profile?.provider && !remote)
              ? profile?.voice
              : remote
                ? 'cedar'
                : cap.voices[0]
          }
        >
          {cap.voices.map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      </label>
      <label>
        {remote ? '语速参考（中文每分钟字数，近似）' : '语速（每分钟词数）'}
        <input
          type="number"
          name="speed"
          min={100}
          max={300}
          required
          defaultValue={profile?.speed || 180}
        />
      </label>
      {remote && (
        <label>
          角色声音与表演说明
          <textarea
            name="instructions"
            maxLength={1000}
            rows={3}
            defaultValue={profile?.instructions || ''}
            placeholder="例如：成年男性，沉稳、克制，普通话清晰；自然停顿，避免播音腔。"
          />
        </label>
      )}
      {!cap.available && (
        <p className="notice">{cap.reason || '此配音方式暂不可用。'} 可以先保存选角设置。</p>
      )}
      {remote && (
        <p className="asset-helper">
          仅点击合成时将选中片段及表演说明发送至 OpenAI，产生 API 用量；保存设置不会生成音频。
        </p>
      )}
      <button disabled={busy || !cap.voices.length}>保存音色</button>
    </form>
  )
}

export function SpeechPanel({ projectId }: { projectId: string }) {
  const cache = useQueryClient()
  const state = useQuery({
    queryKey: ['speech', projectId],
    queryFn: () => api<SpeechState>(`/api/projects/${projectId}/speech`),
  })
  const jobs = useQuery({
    queryKey: ['jobs', projectId],
    queryFn: () => api<Job[]>(`/api/projects/${projectId}/jobs`),
    refetchInterval: (q) => (q.state.data?.some((j) => j.state === 'running') ? 700 : false),
  })
  const job = jobs.data?.find((j) => j.kind === 'speech')
  const finished = useRef('')
  useEffect(() => {
    if (job && job.state !== 'running' && job.id !== finished.current) {
      finished.current = job.id
      cache.invalidateQueries({ queryKey: ['speech', projectId] })
    }
  }, [job?.id, job?.state])
  const save = useMutation({
    mutationFn: ({
      path,
      body,
      method = 'PATCH',
    }: {
      path: string
      body: object
      method?: string
    }) =>
      api(`/api/projects/${projectId}/speech${path}`, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision: state.data?.revision, ...body }),
      }),
    onSettled: () => cache.invalidateQueries({ queryKey: ['speech', projectId] }),
  })
  const generate = useMutation({
    mutationFn: (body: object) =>
      api(`/api/projects/${projectId}/speech/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: () => cache.invalidateQueries({ queryKey: ['jobs', projectId] }),
  })
  const busy = save.isPending || generate.isPending || job?.state === 'running'
  const error = state.error || jobs.error || save.error || generate.error
  const data = state.data
  const characters = [
    ...new Map(
      data?.lines
        .filter((l) => l.eligible && l.speaker_id)
        .map((l) => [l.speaker_id!, l.speaker_name!]),
    ).entries(),
  ]
  return (
    <section className="speech-workbench" aria-label="配音制作">
      <div className="panel-head">
        <h2>对白配音</h2>
        <span>本机语音／OpenAI 云端配音</span>
      </div>
      <p className="asset-helper">
        先绑定角色音色，再勾选重要对白。读音修正不改原文，生成的 AI
        音频需试听接受后才能导出。本机语音不发送正文；OpenAI 支持表演说明，本轮不创建专属音色。
      </p>
      {error && (
        <p className="error" role="alert">
          {error.message}
        </p>
      )}
      {job?.state === 'failed' && (
        <p className="error" role="alert">
          {job.error} 可单独重试。
        </p>
      )}
      {busy && <p role="status">正在处理配音…</p>}
      {save.isSuccess && !busy && (
        <p className="saved-note" role="status">
          ✓ 配音设置已保存。
        </p>
      )}
      {job?.state === 'completed' && (
        <p className="analysis-note">
          最近任务：新合成 {job.result?.generated || 0} 段，缓存复用 {job.result?.reused || 0} 段。
        </p>
      )}
      {!characters.length && (
        <p className="notice">先在「人物与审校」确认角色和对白归属。未知说话人不会套用角色音色。</p>
      )}
      <div className="voice-profiles">
        {data &&
          characters.map(([id, name]) => (
            <VoiceProfile
              key={`${id}:${data.revision}`}
              name={name}
              profile={data.profiles[id]}
              providers={data.providers}
              busy={busy}
              save={(p) => save.mutate({ path: `/profiles/${id}`, body: p })}
            />
          ))}
      </div>
      {data?.lines.map((line, index) => (
        <article key={line.id} className="speech-line">
          <div className="speech-line-head">
            <label>
              <input
                aria-label={`为对白 ${index + 1} 配音`}
                type="checkbox"
                checked={line.selected}
                disabled={busy || (!line.eligible && !line.selected)}
                onChange={(e) =>
                  save.mutate({
                    path: `/lines/${line.id}`,
                    body: { selected: e.target.checked, overrides: line.overrides },
                  })
                }
              />
              {line.speaker_name || '未知说话人'} · 第 {index + 1} 句
            </label>
            <span>
              {line.selected
                ? line.segments.every((s) => s.accepted)
                  ? '✓ 已接受，可导出'
                  : '待合成／试听确认'
                : '未选配音'}
            </span>
          </div>
          <blockquote className="dialogue-quote">{line.text}</blockquote>
          {line.selected && (
            <>
              <form
                key={`${line.id}:${data.revision}`}
                onSubmit={(e) => {
                  e.preventDefault()
                  const f = new FormData(e.currentTarget)
                  const overrides: Record<string, string> = {}
                  line.segments.forEach((s) => {
                    const text = String(f.get(s.key) || '')
                    if (text !== s.original) overrides[s.key] = text
                  })
                  save.mutate({
                    path: `/lines/${line.id}`,
                    body: {
                      selected: true,
                      overrides,
                      instructions: String(f.get('delivery') || ''),
                    },
                  })
                }}
              >
                {line.segments.map((s, i) => (
                  <div className="speech-segment" key={s.key}>
                    <p>
                      片段 {i + 1} 原句：{s.original}
                    </p>
                    <label>
                      片段 {i + 1} 读音文本
                      <textarea
                        name={s.key}
                        maxLength={500}
                        required
                        rows={2}
                        defaultValue={s.spoken}
                      />
                    </label>
                    {s.candidate && (
                      <>
                        <audio
                          controls
                          preload="metadata"
                          src={s.candidate.url}
                          aria-label={`试听对白 ${index + 1} 片段 ${i + 1}`}
                        />
                        <small>
                          {s.candidate.duration.toFixed(1)} 秒 ·{' '}
                          {s.accepted?.id === s.candidate.id ? '此版本已接受' : '此版本待接受'}
                          {s.accepted && s.accepted.id !== s.candidate.id
                            ? '（导出保留先前接受版本）'
                            : ''}
                        </small>
                      </>
                    )}
                    <button
                      type="button"
                      disabled={busy || !line.profile}
                      onClick={() =>
                        generate.mutate({ dialogue_id: line.id, segment_key: s.key, force: true })
                      }
                    >
                      重做片段 {i + 1}
                    </button>
                  </div>
                ))}
                {line.profile?.provider === 'openai-realtime' && (
                  <label>
                    本句表演补充
                    <textarea
                      name="delivery"
                      maxLength={1000}
                      rows={2}
                      defaultValue={line.instructions}
                      placeholder="例如：压低声音，带病中疲惫；保持角色声音身份。"
                    />
                  </label>
                )}
                <button disabled={busy}>保存读音与表演</button>
              </form>
              <div className="speech-actions">
                <button
                  disabled={busy || !line.profile}
                  onClick={() => generate.mutate({ dialogue_id: line.id })}
                >
                  合成此句（优先缓存）
                </button>
                <button
                  disabled={
                    busy || !line.segments.length || line.segments.some((s) => !s.candidate)
                  }
                  onClick={() =>
                    save.mutate({
                      path: `/lines/${line.id}/accept`,
                      method: 'POST',
                      body: {
                        take_ids: Object.fromEntries(
                          line.segments.map((s) => [s.key, s.candidate!.id]),
                        ),
                      },
                    })
                  }
                >
                  接受本句音频
                </button>
              </div>
              {!line.profile && <p className="notice">请先保存角色音色。</p>}
            </>
          )}
        </article>
      ))}
    </section>
  )
}
