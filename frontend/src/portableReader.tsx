import { createRoot } from 'react-dom/client'
import { ReaderView } from './ReaderApp'
import { normalizeContent } from './reader/model'
import './portable-reader.css'

const root = document.getElementById('root')!
try {
  const data = normalizeContent(
    JSON.parse(document.getElementById('taleprism-story')!.textContent!),
  )
  createRoot(root).render(<ReaderView data={data} standalone />)
} catch {
  root.setAttribute('role', 'alert')
  root.textContent =
    '阅读数据不可用。请重新完整解压可信的阅读包，再用桌面浏览器打开 index.html。' +
    ' Story data unavailable. Extract the complete reader ZIP again and open index.html in a desktop browser.'
}
