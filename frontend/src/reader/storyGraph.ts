import type { ReaderContent } from '../reader-types'
import { chibiGraphRecipe } from './graphs/chibi'

export type Evidence = { quote: string; start: number; end: number }
export type GraphPhase = { id: string; title: string; summary: string; evidence: Evidence }
export type GraphFaction = {
  id: string
  name: string
  evidence: Evidence
  members: { id: string; name: string; role: string; evidence: Evidence }[]
}
export type GraphRelation = {
  id: string
  from: string
  to: string
  label: string
  detail: string
  kind: 'alliance' | 'tension' | 'belief' | 'choice' | 'unknown'
  evidence: Evidence
  previousEvidence?: Evidence
  until?: Evidence
}
export type GraphThread = {
  id: string
  title: string
  nodes: {
    id: string
    title: string
    note: string
    kind: 'plan' | 'event' | 'belief'
    dependsOn: string[]
    evidence: Evidence
  }[]
}
type GraphChapter = { label: string; start: number; threads: GraphThread[] }
export type StoryGraph = {
  phases: GraphPhase[]
  factions: GraphFaction[]
  relations: GraphRelation[]
  chapters: GraphChapter[]
}
export type StoryGraphSlice = Omit<StoryGraph, 'chapters'> & {
  threads: GraphThread[]
  chapter: { label: string } | null
}

type Quoted<T extends { evidence: Evidence }> = Omit<T, 'evidence'> & { evidence: string }
export type GraphRecipe = {
  canonicalHash: string
  phases: Quoted<GraphPhase>[]
  factions: (Omit<Quoted<GraphFaction>, 'members'> & {
    members: Quoted<GraphFaction['members'][number]>[]
  })[]
  relations: (Omit<Quoted<GraphRelation>, 'previousEvidence' | 'until'> & {
    previousEvidence?: string
    until?: string
  })[]
  chapters: {
    label: string
    heading: string
    threads: (Omit<GraphThread, 'nodes'> & { nodes: Quoted<GraphThread['nodes'][number]>[] })[]
  }[]
}

const publicRecipes: readonly GraphRecipe[] = [chibiGraphRecipe]
const utf8 = new TextEncoder()
/** Project bytes are the version boundary; the quoted anchors must also resolve uniquely. */
export function resolveStoryGraph(data: ReaderContent, recipes = publicRecipes): StoryGraph | null {
  const recipe = recipes.find((item) => item.canonicalHash === data.project.canonical_sha256)
  if (!recipe) return null
  const index = new Map<string, Evidence>()
  function locate(quote: string): Evidence {
    const cached = index.get(quote)
    if (cached) return cached
    if (!quote.trim()) throw Error('Empty evidence')
    let found: Evidence | null = null
    for (const block of data.blocks) {
      const offset = block.text.indexOf(quote)
      if (offset === -1) continue
      if (found || block.text.indexOf(quote, offset + 1) !== -1) throw Error('Ambiguous evidence')
      const start = block.byte_start + utf8.encode(block.text.slice(0, offset)).length
      const end = start + utf8.encode(quote).length
      if (start < block.byte_start || end > block.byte_end) throw Error('Invalid evidence position')
      found = { quote, start, end }
    }
    if (!found) throw Error('Missing evidence')
    index.set(quote, found)
    return found
  }
  function anchor<T extends { evidence: string }>(
    item: T,
  ): Omit<T, 'evidence'> & { evidence: Evidence } {
    const { evidence, ...info } = item
    return { ...info, evidence: locate(evidence) }
  }
  try {
    const phases = recipe.phases.map(anchor)
    if (phases.some((item, i) => i > 0 && item.evidence.end <= phases[i - 1].evidence.end))
      throw Error('Chronology out of order')
    const factions = recipe.factions.map(({ members, ...faction }) => ({
      ...anchor(faction),
      members: members.map(anchor),
    }))
    const relations = recipe.relations.map(({ previousEvidence, until, ...r }) => {
      const relation = anchor(r)
      const previous = previousEvidence ? locate(previousEvidence) : undefined
      const last = until ? locate(until) : undefined
      if (last && last.end <= relation.evidence.end) throw Error('Nonmonotonic relationship')
      return { ...relation, previousEvidence: previous, until: last }
    })
    const chapters = recipe.chapters.map(({ label, heading, threads }) => ({
      label,
      start: locate(heading).end,
      threads: threads.map(({ nodes, ...thread }) => {
        const resolved = nodes.map(anchor)
        const earlier = new Map<string, number>()
        for (const node of resolved) {
          if (
            earlier.has(node.id) ||
            node.dependsOn.some((id) => !earlier.has(id) || earlier.get(id)! > node.evidence.end)
          ) {
            throw Error('Invalid causal link')
          }
          earlier.set(node.id, node.evidence.end)
        }
        return { ...thread, nodes: resolved }
      }),
    }))
    if (chapters.some((item, i) => i > 0 && item.start <= chapters[i - 1].start))
      throw Error('Chapter order')
    return { phases, factions, relations, chapters }
  } catch {
    // Partial or outdated recipes must not guess at position or leak future nodes.
    return null
  }
}

/** Do not pass the full graph to a visible rendering subtree. Pull back when navigating back. */
export function sliceStoryGraph(graph: StoryGraph, at: number): StoryGraphSlice {
  const boundary = Number.isSafeInteger(at) && at >= 0 ? at : -1
  const seen = ({ end }: Evidence) => end <= boundary
  const activeChapter = graph.chapters.filter((c) => c.start <= boundary).at(-1)
  return {
    chapter: activeChapter ? { label: activeChapter.label } : null,
    phases: graph.phases.filter((p) => seen(p.evidence)),
    factions: graph.factions
      .filter((p) => seen(p.evidence))
      .map((f) => ({
        ...f,
        members: f.members.filter((m) => seen(m.evidence)),
      })),
    relations: graph.relations
      .filter(
        (r) =>
          seen(r.evidence) &&
          (!r.previousEvidence || seen(r.previousEvidence)) &&
          (!r.until || !seen(r.until)),
      )
      .map(({ until: _until, ...r }) => r),
    threads: (activeChapter?.threads || []).flatMap((t) => {
      const ids = new Set<string>()
      const nodes = t.nodes.filter((n) => {
        if (!seen(n.evidence) || !n.dependsOn.every((id) => ids.has(id))) return false
        ids.add(n.id)
        return true
      })
      return nodes.length ? [{ ...t, nodes }] : []
    }),
  }
}
