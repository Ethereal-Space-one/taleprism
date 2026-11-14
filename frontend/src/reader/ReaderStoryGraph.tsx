import { useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { sliceStoryGraph, type StoryGraph } from './storyGraph'
import './story-graph.css'

type Slice = ReturnType<typeof sliceStoryGraph>
type Evidence = Slice['phases'][number]['evidence']
type Faction = Slice['factions'][number]
type Relation = Slice['relations'][number]
type Thread = Slice['threads'][number]
type ThreadNode = Thread['nodes'][number]
type GraphTab = 'factions' | 'mindmap'

const relationKinds: Record<Relation['kind'], string> = {
  alliance: '协作',
  tension: '对立',
  belief: '人物判断',
  choice: '选择',
  unknown: '关系未明',
}
const nodeKinds: Record<ThreadNode['kind'], string> = {
  plan: '计划',
  event: '已发生',
  belief: '人物判断',
}

function SourceEvidence({
  evidence,
  onVisit,
}: {
  evidence: Evidence
  onVisit: (byte: number) => void
}) {
  return (
    <details className="story-graph-evidence">
      <summary>原文依据</summary>
      <div>
        <blockquote>{evidence.quote}</blockquote>
        <button onClick={() => onVisit(evidence.start)}>回到这段原文 →</button>
      </div>
    </details>
  )
}

function FactionBoard({
  factions,
  relations,
  onVisit,
}: {
  factions: Faction[]
  relations: Relation[]
  onVisit: (byte: number) => void
}) {
  const board = useRef<HTMLDivElement>(null)
  const cards = useRef(new Map<string, HTMLElement>())
  const [ties, setTies] = useState<string[]>([])
  const connections = useMemo(() => {
    const owners = new Map<string, string>()
    for (const faction of factions) {
      owners.set(faction.name, faction.id)
      for (const member of faction.members) owners.set(member.name, faction.id)
    }
    const pairs = new Map<string, [string, string]>()
    for (const relation of relations) {
      const from = owners.get(relation.from),
        to = owners.get(relation.to)
      if (from && to && from !== to) {
        const pair = [from, to].sort() as [string, string]
        pairs.set(pair.join(':'), pair)
      }
    }
    return [...pairs.values()]
  }, [factions, relations])

  useLayoutEffect(() => {
    const root = board.current
    if (!root) return
    function measure() {
      const area = root!.getBoundingClientRect()
      const paths: string[] = []
      if (area.width >= 700) {
        connections.forEach(([from, to], index) => {
          const a = cards.current.get(from)?.getBoundingClientRect(),
            b = cards.current.get(to)?.getBoundingClientRect()
          if (!a || !b) return
          const x1 = a.left - area.left + a.width / 2,
            x2 = b.left - area.left + b.width / 2,
            y1 = a.top - area.top,
            y2 = b.top - area.top,
            rail = Math.max(6, Math.min(y1, y2) - 15 - index * 8)
          paths.push(
            `M ${x1} ${y1} V ${rail + 6} Q ${x1} ${rail} ${x1 + (x2 > x1 ? 6 : -6)} ${rail} H ${x2 + (x2 > x1 ? -6 : 6)} Q ${x2} ${rail} ${x2} ${rail + 6} V ${y2}`,
          )
        })
      }
      setTies((previous) => (previous.join('|') === paths.join('|') ? previous : paths))
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(root)
    for (const card of cards.current.values()) observer.observe(card)
    return () => observer.disconnect()
  }, [connections])

  return (
    <div className="story-graph-board" ref={board}>
      <svg className="story-graph-ties" aria-hidden="true" focusable="false">
        {ties.map((path, index) => (
          <path key={index} d={path} />
        ))}
      </svg>
      <div className="story-graph-factions">
        {factions.map((faction, index) => (
          <section
            className="story-graph-faction"
            key={faction.id}
            ref={(element) => {
              if (element) cards.current.set(faction.id, element)
              else cards.current.delete(faction.id)
            }}
          >
            <header>
              <span className="story-graph-index" aria-hidden="true">
                {String(index + 1).padStart(2, '0')}
              </span>
              <h4>{faction.name}</h4>
            </header>
            <ul className="story-graph-members">
              {faction.members.map((member) => (
                <li key={member.id}>
                  <strong>{member.name}</strong>
                  <p>{member.role}</p>
                  <SourceEvidence evidence={member.evidence} onVisit={onVisit} />
                </li>
              ))}
            </ul>
            <SourceEvidence evidence={faction.evidence} onVisit={onVisit} />
          </section>
        ))}
      </div>
    </div>
  )
}

function ThreadBranch({
  node,
  nodes,
  children,
  onVisit,
}: {
  node: ThreadNode
  nodes: Map<string, ThreadNode>
  children: Map<string, ThreadNode[]>
  onVisit: (byte: number) => void
}) {
  const next = children.get(node.id) || []
  return (
    <li>
      <article className={`story-graph-node story-graph-node-${node.kind}`}>
        <span className="story-graph-kind">{nodeKinds[node.kind]}</span>
        <h5>{node.title}</h5>
        <p>{node.note}</p>
        {node.dependsOn.length > 0 && (
          <p className="story-graph-dependency">
            承接：
            {node.dependsOn
              .map((id) => nodes.get(id)?.title)
              .filter(Boolean)
              .join('、')}
          </p>
        )}
        <SourceEvidence evidence={node.evidence} onVisit={onVisit} />
      </article>
      {next.length > 0 && (
        <ol>
          {next.map((child) => (
            <ThreadBranch
              key={child.id}
              node={child}
              nodes={nodes}
              children={children}
              onVisit={onVisit}
            />
          ))}
        </ol>
      )}
    </li>
  )
}

function ThreadTree({ thread, onVisit }: { thread: Thread; onVisit: (byte: number) => void }) {
  const nodes = new Map(thread.nodes.map((node) => [node.id, node])),
    children = new Map<string, ThreadNode[]>(),
    roots: ThreadNode[] = [],
    seen = new Set<string>()
  // Use the first earlier cause as a visual parent; retain every cause in the
  // visible node label. Earlier-only parents also prevent recursive cycles.
  for (const node of thread.nodes) {
    const parent = node.dependsOn.find((id) => seen.has(id))
    if (parent) children.set(parent, [...(children.get(parent) || []), node])
    else roots.push(node)
    seen.add(node.id)
  }
  return (
    <section className="story-graph-thread">
      <h4>{thread.title}</h4>
      <ol className="story-graph-tree">
        {roots.map((node) => (
          <ThreadBranch
            key={node.id}
            node={node}
            nodes={nodes}
            children={children}
            onVisit={onVisit}
          />
        ))}
      </ol>
    </section>
  )
}

export function ReaderStoryGraph({
  graph,
  at,
  onVisit,
}: {
  graph: StoryGraph
  at: number
  onVisit: (byte: number) => void
}) {
  const [tab, setTab] = useState<GraphTab>('factions')
  const id = useId(),
    tabButtons = useRef<(HTMLButtonElement | null)[]>([]),
    slice = useMemo(() => sliceStoryGraph(graph, at), [graph, at]),
    currentPhase = slice.phases.at(-1)
  const tabs: { id: GraphTab; label: string }[] = [
    { id: 'factions', label: '阵营图' },
    { id: 'mindmap', label: '思维导图' },
  ]
  const hasFacts =
    slice.factions.length > 0 || slice.relations.length > 0 || slice.threads.length > 0

  return (
    <div className="reader-story-graph" data-story-graph-at={at}>
      <header className="story-graph-intro">
        <div>
          <p className="story-graph-kicker">随文展开 · 不超前揭示</p>
          <h3>{currentPhase?.title || '故事正要展开'}</h3>
          <p>{currentPhase?.summary || '读到相关段落后，人物关系与事件脉络会在这里逐步出现。'}</p>
        </div>
        <span className="story-graph-position">{slice.chapter?.label || '当前阅读处'}</span>
      </header>
      <p className="story-graph-safety">
        只整理当前正文位置之前的信息。人物的判断不等于事实；回看前文时，图也随之退回。
      </p>
      {slice.phases.length > 1 && (
        <ol className="story-graph-milestones" aria-label="已读阶段">
          {slice.phases.map((phase, index) => (
            <li
              key={phase.id}
              aria-current={index === slice.phases.length - 1 ? 'step' : undefined}
            >
              <span aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
              {phase.title}
            </li>
          ))}
        </ol>
      )}
      <div className="story-graph-tabs" role="tablist" aria-label="脉络视图">
        {tabs.map((item, index) => (
          <button
            key={item.id}
            ref={(element) => {
              tabButtons.current[index] = element
            }}
            id={`${id}-${item.id}-tab`}
            role="tab"
            aria-selected={tab === item.id}
            aria-controls={`${id}-${item.id}-panel`}
            tabIndex={tab === item.id ? 0 : -1}
            onClick={() => setTab(item.id)}
            onKeyDown={(event) => {
              let next: number | undefined
              if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
              if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length
              if (event.key === 'Home') next = 0
              if (event.key === 'End') next = tabs.length - 1
              if (next !== undefined) {
                event.preventDefault()
                setTab(tabs[next].id)
                tabButtons.current[next]?.focus()
              }
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      {tabs.map((item) => (
        <section
          key={item.id}
          id={`${id}-${item.id}-panel`}
          role="tabpanel"
          aria-labelledby={`${id}-${item.id}-tab`}
          tabIndex={0}
          hidden={tab !== item.id}
          className="story-graph-tabpanel"
        >
          {tab === item.id && !hasFacts && (
            <div className="story-graph-empty">
              <p>这一页，先留给故事。</p>
              <span>继续阅读，已读信息会自然汇入脉络。</span>
            </div>
          )}
          {tab === 'factions' && item.id === 'factions' && hasFacts && (
            <>
              <div className="story-graph-section-heading">
                <h3>人物与阵营</h3>
                <span>以已读原文为据</span>
              </div>
              {slice.factions.length ? (
                <FactionBoard
                  factions={slice.factions}
                  relations={slice.relations}
                  onVisit={onVisit}
                />
              ) : (
                <p className="story-graph-empty-note">此处尚无足够依据划分阵营。</p>
              )}
              {slice.relations.length > 0 && (
                <section className="story-graph-relations" aria-label="已知人物关系">
                  <div className="story-graph-section-heading">
                    <h3>关系与分歧</h3>
                    <span>线索有据，判断有别</span>
                  </div>
                  <ul>
                    {slice.relations.map((relation) => (
                      <li
                        key={relation.id}
                        className={`story-graph-relation story-graph-relation-${relation.kind}`}
                      >
                        <div className="story-graph-relation-pair">
                          <strong>{relation.from}</strong>
                          <span aria-hidden="true">→</span>
                          <strong>{relation.to}</strong>
                        </div>
                        <div>
                          <span className="story-graph-kind">{relationKinds[relation.kind]}</span>
                          <h4>{relation.label}</h4>
                          <p>{relation.detail}</p>
                          <SourceEvidence evidence={relation.evidence} onVisit={onVisit} />
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}
          {tab === 'mindmap' && item.id === 'mindmap' && hasFacts && (
            <>
              <div className="story-graph-section-heading">
                <h3>从缘由到变化</h3>
                <span>沿分支向下阅读</span>
              </div>
              <p className="story-graph-tree-note">
                分支表示原文已交代的承接，不补写人物未说出的动机。
              </p>
              {slice.threads.length ? (
                <div className="story-graph-threads">
                  {slice.threads.map((thread) => (
                    <ThreadTree key={thread.id} thread={thread} onVisit={onVisit} />
                  ))}
                </div>
              ) : (
                <p className="story-graph-empty-note">读到相关段落后，事件的承接会在这里展开。</p>
              )}
            </>
          )}
        </section>
      ))}
      <footer className="story-graph-footer">
        <span>脉络是阅读辅助，不替代原文。</span>
        <span>展开「原文依据」可临时回看，续读位置保留。</span>
      </footer>
    </div>
  )
}
