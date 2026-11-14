export function ReaderImageDisclosure({
  onReturn,
  onStay,
  onConfirm,
}: {
  onReturn: () => void
  onStay: () => void
  onConfirm: () => void
}) {
  return (
    <section className="reader-image-disclosure" aria-labelledby="reader-image-disclosure-title">
      <h3 id="reader-image-disclosure-title" tabIndex={-1}>
        后面的插图尚未读到
      </h3>
      <p>查看全卷会包含后文画面，仅本次浏览有效，不会改变阅读位置。</p>
      <div>
        <button className="reader-primary" onClick={onReturn}>
          返回正文
        </button>
        <button onClick={onStay}>继续当前画面</button>
        <button onClick={onConfirm}>查看全卷插图</button>
      </div>
    </section>
  )
}
