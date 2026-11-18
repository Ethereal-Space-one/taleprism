export type VoiceTake = {
  id: string
  byte_start: number
  byte_end: number
  status: 'pending' | 'accepted' | 'withdrawn'
  duration: number
  credit: string
  publish_credit: boolean
  url: string
}
export type Narrations = { revision: number; takes: VoiceTake[] }
export const voiceUrl = (id: string) => '/api/projects/' + id + '/reader/narrations'
