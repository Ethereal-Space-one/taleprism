// Test the real UI across an in-place edition replacement at the identical local URL.
// Uses an isolated browser profile. No authored data, user records, or storage injection.
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const [oldDir, next, book, chrome] = process.argv.slice(2)
const data = dir => JSON.parse(fs.readFileSync(path.join(dir, 'reader.json')))
const before = data(oldDir), after = data(next)
assert.equal(before.project.id, after.project.id)
assert.equal(before.project.canonical_sha256, after.project.canonical_sha256)
const plate = before.config.illustrations[book === 'chibi' ? 6 : 1]
assert.deepEqual(after.config.illustrations.find(p => p.id === plate.id), plate)
let current = oldDir
const prefix = '/taleprism/'
const mime = {'.js':'text/javascript','.css':'text/css','.png':'image/png','.json':'application/json','.wav':'audio/wav','.html':'text/html; charset=utf-8'}
const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://localhost')
  if (!u.pathname.startsWith(prefix)) return res.writeHead(404).end()
  const file = path.resolve(current, decodeURIComponent(u.pathname.slice(prefix.length)) || 'index.html')
  if (!file.startsWith(current + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return res.writeHead(404).end()
  res.writeHead(200, {'Cache-Control':'no-store','Content-Type':mime[path.extname(file)] || 'application/octet-stream'})
  fs.createReadStream(file).pipe(res)
})
;(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r))
  const browser = await chromium.launch({executablePath:chrome,headless:true})
  try {
    const main = 'http://127.0.0.1:'+server.address().port+prefix
    const page = await browser.newPage({viewport:{width:375,height:950}})
    const errors=[]; page.on('pageerror', e => errors.push(e.message))
    const key='storygal-reader:'+before.project.id+':'+before.project.canonical_sha256
    const read = () => page.evaluate(k=>JSON.parse(localStorage.getItem(k)),key)
    await page.goto(main)
    await page.getByRole('button',{name:/^开始阅读/}).click()
    const picture = page.locator('figure[data-illustration-id="'+plate.id+'"] img')
    await page.locator('.reader-scroll').waitFor()
    await page.waitForFunction(() => document.querySelector('.reader-root')?.dataset.resumeByte !== undefined)
    const scroll=page.locator('.reader-scroll'), bounds=await scroll.boundingBox()
    await page.mouse.move(bounds.x+bounds.width*0.5,bounds.y+bounds.height*0.52)
    // A real wheel gesture releases the restore/layout lock. scrollTop injection
    // immediately after cover exit can move pixels without representing a read.
    await page.mouse.wheel(0,5)
    for(let step=0;step<3;step++) {
      const delta=await picture.evaluate(im=>{
        const a=im.getBoundingClientRect(), b=im.closest('.reader-scroll').getBoundingClientRect()
        return a.top+a.height*0.4-b.top-24
      })
      await page.mouse.wheel(0,Math.round(delta))
      await page.waitForTimeout(300)
    }
    await page.waitForFunction(([k,id])=>JSON.parse(localStorage.getItem(k))?.resume?.plate===id,[key,plate.id],{timeout:6000}).catch(async e=>{
      console.error('Previous reader did not create a real plate bookmark', await read(),
        await page.locator('.reader-root').evaluate(el=>({...el.dataset})))
      throw e
    })
    await page.getByRole('button',{name:'收藏',exact:true}).click()
    await page.getByRole('button',{name:'在当前阅读处加书签'}).click()
    await page.getByLabel('关闭面板').click()
    await page.getByRole('button',{name:'设置',exact:true}).click()
    const size=page.getByLabel('正文字号')
    await size.focus(); await size.press('ArrowRight'); await size.press('ArrowRight')
    const font=await size.inputValue()
    await page.getByLabel('关闭面板').click()
    await page.waitForFunction(([k,size])=>{const r=JSON.parse(localStorage.getItem(k));return r.preferences.size===+size&&r.marks.length===1},[key,font])
    const old=await read()
    assert.equal(old.resume.plate,plate.id);assert.equal(old.resume.imageAsset,plate.image_asset_id)
    current=next
    await page.reload(); await page.getByRole('button',{name:/^继续阅读/}).click()
    await page.waitForFunction(([id,byte])=>{const el=document.querySelector('.reader-root');return el?.dataset.viewPlate===id&&+el.dataset.resumeByte===byte},[plate.id,old.resume.byte])
    const restored=await read()
    assert.equal(restored.resume.imageAsset,old.resume.imageAsset)
    assert.equal(restored.resume.plate,old.resume.plate)
    assert.ok(Math.abs(restored.resume.imageOffset-old.resume.imageOffset)<0.01)
    assert.equal(restored.furthest,old.furthest);assert.deepEqual(restored.marks,old.marks)
    assert.equal(restored.preferences.size,+font)
    await page.getByRole('button',{name:'收藏',exact:true}).click()
    assert.ok((await page.getByRole('dialog').innerText()).includes(old.marks[0].text))
    assert.equal(page.url(),main);assert.deepEqual(errors,[])
    console.log(book+': same-origin v0.9.0 → candidate resume/bookmark/font OK; plate '+plate.id+' at byte '+old.resume.byte)
  } finally {await browser.close(); await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e);process.exit(1)})
