/** These controls affect the reading performance, not the underlying manuscript. */
export function ReaderCueTransport({
  active,
  muted,
  sound,
  blocked,
  onRunning,
  onMute,
  onEnable,
}: {
  active: boolean
  muted: boolean
  sound: boolean
  blocked: boolean
  onRunning: () => void
  onMute: () => void
  onEnable: () => void
}) {
  return (
    <div className="reader-cue-transport" role="group" aria-label="随读演绎控制">
      <button
        type="button"
        aria-label={active ? '暂停自动演绎' : '继续自动演绎'}
        title={active ? '暂停自动演绎' : '从后续到达处继续自动演绎'}
        aria-pressed={active}
        onClick={onRunning}
      >
        <svg viewBox="0 0 18 18" aria-hidden="true">
          {active ? <path d="M6 4v10M12 4v10" /> : <path d="m6 3 8 6-8 6z" />}
        </svg>
        <span>{active ? '暂停' : '续演'}</span>
      </button>
      {sound && (
        <button
          type="button"
          aria-label={muted ? '取消静音' : '全部静音'}
          title={muted ? '取消静音（不补播）' : '全部静音'}
          aria-pressed={muted}
          onClick={onMute}
        >
          <svg viewBox="0 0 22 18" aria-hidden="true">
            <path d="m10 3-5 4H2v4h3l5 4z" />
            {muted ? <path d="m14 6 6 6m0-6-6 6" /> : <path d="M14 5q4 4 0 8m3-11q6 7 0 14" />}
          </svg>
          <span>{muted ? '已静音' : '静音'}</span>
        </button>
      )}
      {sound && blocked && !muted && (
        <button
          title="允许播放此处及后续声景"
          className="reader-cue-permission"
          type="button"
          onClick={onEnable}
        >
          开启声音
        </button>
      )}
    </div>
  )
}
