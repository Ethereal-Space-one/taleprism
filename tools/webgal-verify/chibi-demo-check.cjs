// Check the exact standalone showcase, locally or at its public Pages URL.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const {chromium} = require('playwright')
const root = path.resolve(__dirname, '../..')
const target = process.argv[2] || path.join(root, '.release/chibi-demo/site')
const remote = /^https?:\/\//.test(target)
const output = path.resolve(process.argv[3] || path.join(root, 'data/verification/chibi-demo', remote ? 'public' : 'local'))
fs.mkdirSync(output, {recursive:true})

;(async () => {
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true})
  const page = await browser.newPage({viewport:{width:1440,height:1000}})
  const errors = [], apis = [], failed = []
  const report = {passed:false, checked_at:new Date().toISOString(), target}
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => {if(new URL(request.url()).pathname.includes('/api/')) apis.push(request.url())})
  page.on('response', response => {if(response.status()>=400) failed.push([response.status(), response.url()])})
  let server
  try {
    let base = target
    if (!remote) {
      const site = path.resolve(target)
      server = http.createServer((req,res) => {
        const url = decodeURIComponent(req.url.split('?')[0])
        if (!url.startsWith('/taleprism/')) {res.writeHead(404).end();return}
        const file = path.resolve(site, url.slice('/taleprism/'.length) || 'index.html')
        if (!file.startsWith(site+path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {res.writeHead(404).end();return}
        const mime = {'.js':'application/javascript','.css':'text/css','.json':'application/json','.png':'image/png','.txt':'text/plain'}
        res.setHeader('Content-Type', mime[path.extname(file)] || 'text/html')
        fs.createReadStream(file).pipe(res)
      })
      await new Promise(resolve => server.listen(0,'127.0.0.1',resolve))
      base = 'http://127.0.0.1:'+server.address().port+'/taleprism/'
    }
    await page.goto(base)
    await page.getByRole('link',{name:'用 Taleprism 制作 ↗'}).waitFor()
    const data = await (await page.request.get(new URL('reader.json',base).href)).json()
    assert.equal(data.config.title,'赤壁')
    assert.equal(data.config.illustrations.length,12)
    assert.equal(Object.keys(data.characters).length,8)
    assert.equal(data.presentations.length,55)
    assert.equal(Object.values(data.media).filter(m=>m.type==='figure').length,9)
    assert.equal(Object.values(data.media).filter(m=>m.type==='audio').length,0)
    await page.locator('.reader-cover img').evaluateAll(async images=>Promise.all(images.map(i=>i.decode())))
    await page.screenshot({path:path.join(output,'cover-1440.png')})
    await page.getByRole('button',{name:/^开始阅读/}).click()
    assert.equal(await page.locator('.reader-plate').count(),12)
    for (const image of await page.locator('.reader-plate img').all()) {
      await image.scrollIntoViewIfNeeded()
      await image.evaluate(i=>i.decode())
    }
    const raw = fs.readFileSync(path.join(root,'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'),'utf8').split(/\r\n|\r|\n/).map(s=>s.replace(/^[ \t\u3000]+|[ \t\u3000]+$/g,'')).join('')
    assert.equal(await page.locator('.reader-paragraph-text').evaluateAll(es=>es.map(e=>e.textContent).join('')),raw)
    // Load every portrait too, including poses not currently active in illustrated mode.
    for (const medium of Object.values(data.media).filter(m=>m.type==='figure')) {
      await page.evaluate(url=>new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>i.decode().then(resolve,reject);i.onerror=reject;i.src=url}),new URL(medium.url,base).href)
    }
    await page.setViewportSize({width:375,height:950})
    await page.locator('.reader-plate img').nth(1).scrollIntoViewIfNeeded()
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
    await page.screenshot({path:path.join(output,'reader-375.png')})
    await page.getByRole('button',{name:'设置',exact:true}).click()
    await page.getByRole('button',{name:'查看战区地图',exact:true}).click()
    assert.equal(await page.locator('.map-phases>button').count(),3)
    for (const phase of await page.locator('.map-phases>button').all()) {
      await phase.click()
      assert.equal(await phase.getAttribute('aria-pressed'),'true')
    }
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
    await page.screenshot({path:path.join(output,'map-375.png')})
    await page.getByRole('button',{name:'关闭面板',exact:true}).click()
    await page.reload()
    await page.waitForSelector('.reader-root')
    assert.deepEqual(apis,[])
    assert.deepEqual(failed,[])
    assert.deepEqual(errors,[])
    Object.assign(report,{passed:true,source_equal:true,illustrations_decoded:12,portraits_decoded:9,map_phases:3,static_subpath:true,static_without_api:true,desktop_and_mobile:true})
  } catch(error) {
    report.error=String(error.stack||error)
    await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{})
    throw error
  } finally {
    fs.writeFileSync(path.join(output,'browser-report.json'),JSON.stringify(report,null,2))
    if(server) server.close()
    await browser.close()
  }
  console.log(JSON.stringify(report,null,2))
})().catch(error=>{console.error(error);process.exit(1)})
