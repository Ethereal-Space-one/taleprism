import { useState } from 'react'
import { api } from '../api'
export default function EditorialPreview({
  projectId,
  anchor,
}: {
  projectId: string
  anchor: number
}) {
  const [open, setOpen] = useState(false),
    [note, setNote] = useState(''),
    [category, setCategory] = useState('visual'),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false)
  async function save() {
    setBusy(true)
    setMessage('')
    try {
      const state = await api<{ revision: number }>(`/api/projects/${projectId}/reader/editorial`)
      await api(`/api/projects/${projectId}/reader/editorial`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          revision: state.revision,
          anchor,
          category,
          note,
          state: 'open',
          reason: '',
        }),
      })
      setNote('')
      setMessage('意见已记录，可回制作台定位处理。')
    } catch (e) {
      setMessage((e as Error).message + '，草稿已保留。')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="reader-editorial-preview">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        {open ? '收起审校' : '记录此处意见'}
      </button>
      <a
        href="/"
        onClick={() => {
          try {
            localStorage.setItem('storygal-project', projectId)
          } catch {}
        }}
      >
        回制作台
      </a>
      {open && (
        <div>
          <label>
            问题类型
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="visual">画面</option>
              <option value="cast">人物出场</option>
              <option value="audio">声音</option>
              <option value="map">地图</option>
              <option value="reading">阅读操作</option>
            </select>
          </label>
          <label>
            此处意见
            <textarea maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <button disabled={!note.trim() || busy} onClick={save}>
            {busy ? '正在记录…' : '保存此处意见'}
          </button>
          <p role="status">{message}</p>
        </div>
      )}
    </div>
  )
}
