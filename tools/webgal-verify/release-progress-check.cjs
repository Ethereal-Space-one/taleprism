// Verify saved 0.1 Chibi progress/preferences/bookmarks against the new public reader.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const {chromium} = require('playwright')
const root = path.resolve(__dirname, '../..')
const oldSite = path.resolve(process.argv[2] || path.join(root, '.release/chibi-demo/site'))
const target = process.argv[3] || path.join(root, '.release/v0.2.0/site-chibi')
const out = path.resolve(process.argv[4] || path.join(root, '.release/v0.2.0/browser/progress'))

async function serve(site) {
  const server = http.createServer((req, res) => {
    const prefix = '/taleprism/'
    const pathname = new URL(req.url, 'http://localhost').pathname
    if (!pathname.startsWith(prefix)) { res.writeHead(404).end(); return }
    const file = path.resolve(site, decodeURIComponent(pathname.slice(prefix.length)) || 'index.html')
    if (!file.startsWith(site + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404).end(); return
    }
    const mime = {'.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png'}
    res.setHeader('Content-Type', mime[path.extname(file)] || 'text/html')
    fs.createReadStream(file).pipe(res)
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  return server
}

;(async () => {
  fs.mkdirSync(out, {recursive:true})
  const old = JSON.parse(fs.readFileSync(path.join(oldSite, 'reader.json')))
  const plate = old.config.illustrations[6]
  const block = old.blocks.find(b=>b.byte_end===plate.after_byte)
  const key = `storygal-reader:${old.project.id}:${old.project.canonical_sha256}`
  const position = {byte:block.byte_start, offset:0, plate:plate.id, imageOffset:0.4}
  const record = {
    version:2, resume:position, furthest:block.byte_start, completed:false, updated:Date.now(),
    preferences:{size:23,leading:1.9,width:680,stage:true,layout:'illustrated'},
    marks:[{id:'old-record',position,text:'跨版本保留的原文书签'}],
  }
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true})
  const page = await browser.newPage({viewport:{width:375,height:950}}), errors=[]
  const report={passed:false,checked_at:new Date().toISOString(),target}
  let server
  page.on('pageerror',e=>errors.push(e.message))
  try {
    let base = target
    if (!/^https?:\/\//.test(target)) {
      server = await serve(path.resolve(target))
      base = `http://127.0.0.1:${server.address().port}/taleprism/`
    }
    const response = await page.request.get(new URL('reader.json', base).href)
    assert.ok(response.ok(), `Reading data returned HTTP ${response.status()}`)
    const current = await response.json()
    assert.equal(current.project.id, old.project.id, 'Public work identity must remain stable')
    assert.equal(current.project.canonical_sha256, old.project.canonical_sha256)
    assert.deepEqual(current.config.illustrations.map(p=>[p.id,p.after_byte]), old.config.illustrations.map(p=>[p.id,p.after_byte]))
    // Load the previous release's record before the new app can initialize storage.
    await page.addInitScript(({key,record})=>localStorage.setItem(key,JSON.stringify(record)),{key,record})
    await page.goto(base)
    await page.getByRole('button',{name:/^继续阅读/}).click()
    await page.waitForFunction(({byte,plate})=>{
      const r=document.querySelector('.reader-root')
      return Number(r.dataset.resumeByte)===byte && r.dataset.viewPlate===plate
    },position)
    const image = page.locator('.reader-plate img').nth(6)
    await image.evaluate(e=>e.decode())
    const rect = await image.boundingBox()
    assert.ok(rect && rect.y<950 && rect.y+rect.height>50)
    await page.screenshot({path:path.join(out,'resumed-image-mobile.png')})
    await page.getByRole('button',{name:'收藏',exact:true}).click()
    await page.getByRole('button',{name:/跨版本保留的原文书签/}).waitFor()
    const saved = await page.evaluate(key=>JSON.parse(localStorage.getItem(key)),key)
    assert.equal(saved.preferences.size,23)
    assert.equal(saved.marks.length,1)
    assert.equal(saved.marks[0].position.plate,plate.id)
    assert.deepEqual(errors,[])
    Object.assign(report,{passed:true,stable_public_identity:true,unchanged_source:true,old_image_resume:true,old_bookmark:true,preferences_preserved:true})
  } catch(e) {
    report.error=String(e.stack||e);await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});throw e
  } finally {
    fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2)+'\n')
    await browser.close()
    if (server) server.close()
  }
  console.log(JSON.stringify(report,null,2))
})().catch(e=>{console.error(e);process.exit(1)})
