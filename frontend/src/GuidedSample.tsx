import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import type { Check } from './ContinuityEditor'
import './guided-sample.css'

export type GuidedProject = { projectId: string; shotId: string; restoreIssues?: string[] }
type SampleStatus = { cached: boolean; requires_api_key: boolean }
type GuideState = {
  plan: {
    shots: {
      id: string
      title: string
      continuity: { scene_id: string | null }
      continuity_check: Check
    }[]
  }
}
export type GuidedStart = { pending: boolean; error: Error | null; start: () => void }

export function GuidedSampleIntro({
  start,
  compact = false,
}: {
  start: GuidedStart
  compact?: boolean
}) {
  const sample = useQuery({
    queryKey: ['guided-last-light'],
    queryFn: () => api<SampleStatus>('/api/samples/last-light/guided'),
    staleTime: 60_000,
  })
  if (compact)
    return (
      <div className="guided-sidebar">
        <span className="guided-kicker">三步 / 一幅练习</span>
        <button disabled={start.pending} onClick={start.start}>
          {start.pending ? '正在准备完整样例…' : '《末班灯》引导练习'}
        </button>
        <small>完整示例，另存一份。无需 API Key。</small>
      </div>
    )
  return (
    <section className="guided-intro" aria-labelledby="guided-title">
      <div className="guided-intro-copy">
        <p className="guided-kicker">FIRST EDIT / 从完整作品学起</p>
        <h1 id="guided-title">
          不用从零，
          <br />
          先修好一幅。
        </h1>
        <p className="guided-deck">
          打开《末班灯》的三幅短篇，试着调整「谁来开灯」。
          <br className="desktop-break" />
          人物、画面和制作依据都已备好，你只需关注这一次修改。
        </p>
        <button className="primary guided-open" disabled={start.pending} onClick={start.start}>
          {start.pending ? '正在准备完整《末班灯》…' : '修一幅《末班灯》'}
          <span aria-hidden="true">→</span>
        </button>
        <p className="guided-assurance">不需要 API Key · 不用手动下载 ZIP · 每次新建副本</p>
        <p className="guided-download" role="status">
          {start.pending
            ? '正在读取并校验固定公开样例。首次下载最多约一分钟，请不要重复点击。'
            : sample.data?.cached
              ? '完整样例已在本机，打开即可开始。'
              : '首次打开会下载约 15 MB 的固定公开样例，并核对 SHA-256；之后使用本机缓存。'}
        </p>
        {(start.error || sample.error) && (
          <p className="error" role="alert">
            {(start.error || sample.error)?.message}
          </p>
        )}
      </div>
      <aside className="guided-preview" aria-label="练习路线">
        <span className="guided-kicker">LAST LIGHT / 末班灯</span>
        <blockquote>
          “放进去以后，
          <br />
          谁来开？”
        </blockquote>
        <p>海边旧站，一次尚未结束的交谈。</p>
        <ol>
          <li>
            <span>01</span>
            <div>
              <b>只改一幅</b>
              <small>从画面、动作或表演意图开始</small>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <b>复核受影响内容</b>
              <small>看清哪些依据需要重新检查</small>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <b>预览，再决定</b>
              <small>原文与原示例始终保留</small>
            </div>
          </li>
        </ol>
      </aside>
    </section>
  )
}

export function GuidedSampleSteps({
  guide,
  mode,
  onEdit,
  onPreview,
  onLeave,
  onNavigate,
}: {
  guide: GuidedProject
  mode: string
  onEdit: (shotId: string) => void
  onPreview: () => void
  onLeave: () => void
  onNavigate: () => void
}) {
  const state = useQuery({
    queryKey: ['production', guide.projectId],
    queryFn: () => api<GuideState>(`/api/projects/${guide.projectId}/production`),
  })
  const shots = state.data?.plan.shots || []
  const target = shots.find((shot) => shot.id === guide.shotId)
  const affected = shots.filter(
    (shot) =>
      !!shot.continuity.scene_id &&
      (shot.continuity_check?.status !== 'passed' || !shot.continuity_check.basis),
  )
  return (
    <section className="guided-steps" aria-labelledby="guided-steps-title">
      <div className="guided-steps-heading">
        <div>
          <p className="guided-kicker">引导练习 / 正在编辑独立副本</p>
          <h2 id="guided-steps-title">这一轮，只关注「{target?.title || '谁来开灯'}」。</h2>
        </div>
        <button className="text-button" onClick={onLeave}>
          收起引导
        </button>
      </div>
      {!!guide.restoreIssues?.length && (
        <p className="guided-restore-note" role="status">
          样例已保留原方案与审核记录；恢复检查提示：{guide.restoreIssues.join('；')}
          。请核对后再正式导出。
        </p>
      )}
      <ol>
        <li>
          <span>01</span>
          <div>
            <b>修改这一幅</b>
            <p>在镜头中改表演意图、动作，或准备新的候选图。先保存草稿，不覆盖原图。</p>
            <button onClick={() => onEdit(guide.shotId)}>
              去修改「{target?.title || '谁来开灯'}」 →
            </button>
          </div>
        </li>
        <li>
          <span>02</span>
          <div>
            <b>只复核受影响的依据</b>
            <p role="status">
              {state.error
                ? '暂时无法读取检查状态，请在制作方案中重试。'
                : !state.data
                  ? '正在读取已保存的检查状态…'
                  : affected.length
                    ? `已保存方案中有 ${affected.length} 幅需要复核。改动可能影响后续同场景镜头，不要沿用旧通过记录。`
                    : '已保存方案暂无失效检查。修改并保存后，按新内容复核；原有制作记录不等于你的最终验收。'}
            </p>
            <button onClick={() => onEdit(affected[0]?.id || guide.shotId)}>
              查看{affected.length ? '待复核镜头' : '检查依据'} →
            </button>
          </div>
        </li>
        <li>
          <span>03</span>
          <div>
            <b>应用后，预览这一版</b>
            <p>确认方案与图片，完成连续性检查，再应用到画卷阅读。预览不会替你完成艺术验收。</p>
            <button aria-pressed={mode === 'reader'} onClick={onPreview}>
              打开阅读器与预览 →
            </button>
            <a href={`/read/${guide.projectId}`} target="_blank" rel="noreferrer">
              新窗口查看当前阅读版 ↗
            </a>
          </div>
        </li>
      </ol>
      <p className="guided-safety">
        这是完整公开示例的编辑副本，不会改动你已有的项目。公开版不含系统演示音频；示例制作检查仅作学习依据。
      </p>
    </section>
  )
}
