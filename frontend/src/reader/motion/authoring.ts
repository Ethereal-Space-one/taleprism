import type {
  IllustrationMotion,
  MotionPoint,
  ReaderAsset,
  ReaderIllustration,
  ReaderState,
} from '../../reader-types'
import {
  directionRecipe,
  maskContainsPoint,
  masksOverlap,
  validIllustrationMotion,
  validMotionRecipe,
} from './recipes'

export type DirectionDraft = IllustrationMotion
export function newDirection(
  effect: IllustrationMotion['effect'],
  asset: ReaderAsset,
  sourceHash: string,
  afterByte: number,
): DirectionDraft {
  const base = {
    version: 1 as const,
    source_sha256: sourceHash,
    image_sha256: asset.sha256,
    after_byte: afterByte,
    width: asset.width || 0,
    height: asset.height || 0,
    evidence: '',
    note: '',
    reviewed: false,
  }
  return effect === 'rain-wet-ground'
    ? { ...base, effect, areas: [], ground: [], drops: 98, rings: 0 }
    : { ...base, effect, water: [], bank: [], hits: [] }
}
export function bankHits(bank: readonly MotionPoint[], count: number) {
  if (bank.length < 2) return []
  const n = Number.isFinite(count) ? Math.max(1, Math.min(6, Math.trunc(count))) : 3
  const left = bank[0][0],
    span = bank.at(-1)![0] - left
  return Array.from({ length: n }, (_, i) => ({
    x: left + (span * (i + 0.5)) / n,
    phase: i * 0.61,
    length: 7.1,
    gain: 0.9,
  }))
}
export function directionProblem(
  motion: DirectionDraft,
  plate: ReaderIllustration,
  asset: ReaderAsset,
  sourceHash: string,
  paragraphs: ReaderState['paragraphs'],
): string | null {
  if (
    !asset.width ||
    !asset.height ||
    motion.width !== asset.width ||
    motion.height !== asset.height ||
    motion.image_sha256 !== asset.sha256 ||
    motion.source_sha256 !== sourceHash ||
    motion.after_byte !== plate.after_byte
  )
    return '底图或原文位置已改变，请重新建立导演设置。'
  if (!validMotionRecipe(directionRecipe(motion, plate.id)))
    return motion.effect === 'rain-wet-ground'
      ? '先完成至少一个不交叉的雨区，雨区至少三个点。'
      : '先完成水与水花允许区，再从左向右标至少两个岸线点。'
  if (
    [...motion.evidence.replace(/[\s\u001c-\u001f\u0085]/gu, '')].length < 8 ||
    [...motion.evidence].length > 300 ||
    !paragraphs.some((p) => p.byte_end <= plate.after_byte && p.text.includes(motion.evidence))
  )
    return '请选择此插图位置以前已出现的逐字原文依据（8 至 300 字）。'
  if (motion.effect === 'rain-wet-ground' && motion.rings > 0 && !motion.ground.length)
    return '涟漪需要单独标注接雨湿地区域；没有湿地时请设为 0。'
  if (
    motion.effect === 'rain-wet-ground' &&
    motion.rings > 0 &&
    !masksOverlap(motion.areas, motion.ground)
  )
    return '接雨湿地须与雨区重叠，涟漪只在两者重叠处出现。'
  if (
    motion.effect === 'wave-impact-backwash' &&
    motion.hits.some((hit) => {
      const index = motion.bank.findIndex((p, i) => i > 0 && hit.x <= p[0])
      const left = motion.bank[index - 1],
        right = motion.bank[index]
      if (!left || !right) return true
      const y = left[1] + ((right[1] - left[1]) * (hit.x - left[0])) / (right[0] - left[0])
      return !motion.water.some((p) => maskContainsPoint([hit.x, y], p))
    })
  )
    return '岸线撞点须在水与水花允许区内或边界上，不会把岸线吸附到别处。'
  if (!validIllustrationMotion(motion))
    return '请写至少 8 个非空白字的实际画面观察（最多 300 字）。'
  return null
}
