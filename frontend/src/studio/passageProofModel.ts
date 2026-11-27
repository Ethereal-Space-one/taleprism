import type { ReaderBlock, ReaderContent } from '../reader-types'
import { galleryAtPosition } from '../reader/imageBrowsing'
import { resolvePlatePresentations } from '../reader/platePresentation'

export function publicAudio(block: ReaderBlock, data: ReaderContent) {
  const cues = [
    ...(block.soundscape
      ? [{ id: block.soundscape.id, label: block.soundscape.description, kind: '段落声景' }]
      : []),
    ...(block.narration
      ? [{ id: block.narration.id, label: block.narration.label, kind: '段落朗读' }]
      : []),
    ...block.audio.map((a) => ({
      id: a.take_id,
      label: data.characters[a.speaker_id]?.name || '对白',
      kind: '对白',
    })),
  ]
  return cues.map((cue) => ({ ...cue, media: data.media[cue.id] }))
}

export function proofAt(data: ReaderContent, position: number, moment: 'before' | 'after') {
  const block = data.blocks[position]
  if (!block) return null
  const boundary =
    moment === 'before' ? (data.blocks[position - 1]?.byte_end ?? -1) : block.byte_end
  const plates = data.config.illustrations ?? []
  const presentations = resolvePlatePresentations(data)
  const gallery = galleryAtPosition(plates, presentations, boundary)
  const visibleBlocks = data.blocks.slice(0, position + (moment === 'after' ? 1 : 0))
  return {
    block,
    boundary,
    gallery,
    hiddenCount: plates.length - gallery.length,
    presentations,
    visibleBlocks,
    last: visibleBlocks.at(-1),
    landed: plates.filter((p) => presentations.get(p.id)?.displayAfterByte === block.byte_end),
  }
}

// A literal hit is an editorial cue, never a semantic verdict. Avoid quadratic scans;
// the author provides the sensitive phrase instead of guessing character names or endings.
export function inspectPhrase(
  data: ReaderContent,
  proof: NonNullable<ReturnType<typeof proofAt>>,
  query: string,
) {
  const q = query.trim()
  if (!q) return []
  const hits: string[] = []
  if (data.config.title.includes(q) || data.config.subtitle.includes(q)) hits.push('封面文字')
  if (proof.visibleBlocks.some((b) => b.text.includes(q))) hits.push('已读原文')
  const contains = (s?: string | null) => !!s?.includes(q)
  if (proof.gallery.some((p) => contains(p.title))) hits.push('已解锁画卷标题')
  if (
    proof.gallery.some((p) =>
      contains(proof.presentations.get(p.id)?.visualDescription || p.description),
    )
  )
    hits.push('插图说明或替代文字')
  if (
    proof.visibleBlocks.some((b) =>
      publicAudio(b, data).some((a) => contains(a.label) || contains(a.media?.credit)),
    )
  )
    hits.push('声音标签、说话人或署名')
  return hits
}
