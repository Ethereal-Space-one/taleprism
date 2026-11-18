// Author-side import only. No microphone, network decoder or metadata upload.
export const maxVoiceBytes = 24_000_000
export const maxVoiceSeconds = 120
const rate = 24000

function assertDuration(seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0 || seconds > maxVoiceSeconds)
    throw Error('录音需有可读取的时长，最长 120 秒。请先剪出这一段再试。')
}

async function checkMetadata(file: File, signal: AbortSignal) {
  const media = document.createElement('audio')
  const url = URL.createObjectURL(file)
  let timer: number | undefined
  let abort: (() => void) | undefined
  try {
    return await new Promise<void>((resolve, reject) => {
      abort = () => reject(new DOMException('已取消读取', 'AbortError'))
      signal.addEventListener('abort', abort, { once: true })
      if (signal.aborted) return abort()
      timer = window.setTimeout(() => reject(Error('未能读取录音时长，请改用短 PCM WAV。')), 10000)
      media.onloadedmetadata = () => {
        try {
          assertDuration(media.duration)
          resolve()
        } catch (error) {
          reject(error)
        }
      }
      media.onerror = () =>
        reject(Error('此浏览器无法读取该录音。可先另存为 PCM WAV，再选取文件。'))
      media.preload = 'metadata'
      media.src = url
    })
  } finally {
    window.clearTimeout(timer)
    if (abort) signal.removeEventListener('abort', abort)
    media.onloadedmetadata = null
    media.onerror = null
    media.removeAttribute('src')
    media.load()
    URL.revokeObjectURL(url)
  }
}

export function encodeMonoPcm(
  audio: Pick<AudioBuffer, 'sampleRate' | 'length' | 'numberOfChannels' | 'getChannelData'>,
): Blob {
  assertDuration(audio.length / rate)
  if (
    audio.sampleRate !== rate ||
    !Number.isInteger(audio.length) ||
    audio.numberOfChannels < 1 ||
    audio.numberOfChannels > 8
  )
    throw Error('声道或采样参数不受支持，建议先转换为单声道 WAV。')
  const channels = Array.from({ length: audio.numberOfChannels }, (_, i) => audio.getChannelData(i))
  const buffer = new ArrayBuffer(44 + audio.length * 2)
  const view = new DataView(buffer)
  const text = (start: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(start + i, value.charCodeAt(i))
  }
  text(0, 'RIFF')
  view.setUint32(4, buffer.byteLength - 8, true)
  text(8, 'WAVE')
  text(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, rate, true)
  view.setUint32(28, rate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  text(36, 'data')
  view.setUint32(40, buffer.byteLength - 44, true)
  let signal = false
  for (let i = 0; i < audio.length; i++) {
    let total = 0
    for (const channel of channels) total += channel[i]
    const v = Math.max(-1, Math.min(1, total / channels.length))
    const pcm = Number.isFinite(v) ? Math.round(v * (v < 0 ? 32768 : 32767)) : 0
    view.setInt16(44 + i * 2, pcm, true)
    if (pcm) signal = true
  }
  if (!signal) throw Error('转换后的录音为静音。请检查音量或先导出单声道 WAV。')
  return new Blob([buffer], { type: 'audio/wav' })
}

export async function prepareNarration(file: File, signal: AbortSignal) {
  if (!file.size || file.size > maxVoiceBytes || !/\.(wav|mp3|m4a)$/i.test(file.name))
    throw Error('请选择非空 WAV、MP3 或 M4A 文件，最多 24 MB。')
  if (!window.OfflineAudioContext)
    throw Error('此浏览器不支持本地音频解码，请在桌面版现代浏览器打开制作台。')
  await checkMetadata(file, signal)
  signal.throwIfAborted()
  const bytes = await file.arrayBuffer()
  signal.throwIfAborted()
  let audio: AudioBuffer
  try {
    audio = await new OfflineAudioContext(1, 1, rate).decodeAudioData(bytes)
  } catch {
    throw Error('录音解码失败，原版本未变。请改用本机导出的短 PCM WAV。')
  }
  signal.throwIfAborted()
  return encodeMonoPcm(audio)
}

// Looking at the seek bar's end is not evidence that the candidate played.
// Allow only tiny browser timestamp rounding gaps, not a seek-to-end shortcut.
export function heardEntireTake(played: TimeRanges, duration: number) {
  if (!Number.isFinite(duration) || duration <= 0 || !played.length) return false
  let covered = 0
  const tolerance = Math.min(0.05, duration * 0.02)
  for (let i = 0; i < played.length; i++) {
    if (played.start(i) > covered + tolerance) return false
    covered = Math.max(covered, played.end(i))
  }
  return covered >= duration - tolerance
}
