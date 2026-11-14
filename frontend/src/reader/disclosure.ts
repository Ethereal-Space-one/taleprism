import type { ReaderContent, ReaderMapData } from '../reader-types'

const boundary = (at: number) => (Number.isSafeInteger(at) && at >= 0 ? at : -1)

/** These are display labels only. The underlying source text and jump anchors stay intact. */
export function directoryEntries(
  data: ReaderContent,
  at: number,
  protectFuture: boolean,
  full = false,
) {
  const reached = (start: number) => !protectFuture || full || start <= boundary(at)
  return {
    chapters: data.blocks
      .filter((block) => block.heading)
      .map((block, index) => ({
        id: block.id,
        byte: block.byte_start,
        title: reached(block.byte_start)
          ? block.text
          : `${block.text.trim().match(/^第[〇零一二三四五六七八九十百千万萬两兩0-9]+[回章节節卷部篇]/)?.[0] || `章节 ${index + 1}`} · 后文标题暂隐`,
      })),
    scenes: data.config.scenes.map((scene, index) => ({
      id: scene.id,
      byte: scene.start_byte,
      title: reached(scene.start_byte) ? scene.title : `场景 ${index + 1} · 后文标题暂隐`,
    })),
  }
}

export type MapDisclosure = {
  placePhases: Record<string, string>
  sourcePhases: Record<string, string>
}

/** Return only display-safe data, including labels used by tooltips and the SVG. */
export function mapAtPosition(
  data: ReaderMapData,
  at: number,
  disclosure: MapDisclosure | null,
  full = false,
) {
  const available = data.phase_anchors.reduce(
    (best, anchor, index) => (anchor <= boundary(at) ? index : best),
    -1,
  )
  const visible = (index: number) => !disclosure || full || index <= available
  const hasPhase = (id: string | undefined) => {
    if (!id) return true
    const index = data.phases.findIndex((phase) => phase.id === id)
    return index >= 0 && visible(index)
  }
  return {
    ...data,
    available,
    phases: data.phases.map((phase, index) => ({
      id: phase.id,
      title: visible(index) ? phase.title : `阶段 ${index + 1} · 后文暂隐`,
      description: visible(index)
        ? phase.description
        : '读到这一阶段后展开名称、说明与行动方向，也可选择「查看完整战役」。',
      revealed: visible(index),
    })),
    places: data.places.map((place) => ({
      ...place,
      description: hasPhase(disclosure?.placePhases[place.id])
        ? place.description
        : '此地的后续行动说明暂隐；古今位置仍可查看，也可选择「查看完整战役」。',
    })),
    sources: data.sources.map((source) => ({
      ...source,
      note: hasPhase(disclosure?.sourcePhases[source.id])
        ? source.note
        : '此资料包含后续战役经过；相关说明随正文进度展开。',
    })),
  }
}
