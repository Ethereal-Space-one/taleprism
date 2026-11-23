import { utf16Boundary } from '../reader/model'

export type SoundTake = {
  id: string
  byte_start: number
  byte_end: number
  evidence: string
  evidence_start: number
  pencil?: boolean
  wind?: boolean
  rain: boolean
  car_at: number | null
  status: 'pending' | 'accepted' | 'withdrawn'
  duration: number
  url: string
}
export type Soundscapes = { revision: number; takes: SoundTake[] }
export const soundUrl = (id: string) => '/api/projects/' + id + '/reader/soundscapes'

export function occurrences(source: string, phrase: string) {
  const starts: number[] = []
  if (!phrase.trim() || [...phrase].length > 300 || /[\uD800-\uDFFF]/u.test(phrase)) return starts
  for (let i = source.indexOf(phrase); i >= 0; i = source.indexOf(phrase, i + 1)) starts.push(i)
  return starts
}

export function selectedSoundEvidence(source: string, from: number, to: number) {
  if (to <= from) return null
  const start = utf16Boundary(source, from)
  const text = source.slice(start, utf16Boundary(source, to, 'ceil'))
  const occurrence = occurrences(source, text).indexOf(start) + 1
  return occurrence ? { text, occurrence } : null
}

export function layers(t: Pick<SoundTake, 'rain' | 'wind' | 'pencil' | 'car_at'>) {
  if (t.pencil) return '三次轻重不一的铅笔划痕，随后留白'
  return [
    t.rain ? '持续细雨' : t.wind ? '持续风声' : '',
    t.car_at === null ? '' : '一辆车在第 ' + t.car_at + ' 秒经过',
  ]
    .filter(Boolean)
    .join('；')
}
