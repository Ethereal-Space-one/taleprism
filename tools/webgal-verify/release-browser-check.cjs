const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const {chromium} = require('playwright')
const root = path.resolve(__dirname, '../..')
const base = process.argv[2] || 'http://127.0.0.1:8002'
const output = path.join(root, 'data/verification/release-v0.1.0')
const release = path.join(root, '.release/v0.1.0')
fs.mkdirSync(output, {recursive:true})
;(async () => {
 const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true})
 const page = await browser.newPage({viewport:{width:1440,height:1000}})
 const errors = [], report = {passed:false,checked_at:new Date().toISOString()}
 page.on('pageerror', e => errors.push(e.message))
 let server
 try {
  await page.goto(base)
  await page.getByRole('link',{name:'Taleprism 首页'}).waitFor()
  await page.getByLabel('本地内容包').selectOption('last-light')
  assert.equal(await page.getByRole('button',{name:'下载后导入工程',exact:true}).isDisabled(),true)
  assert.match(await page.getByRole('link',{name:'下载示例工程 ↗'}).getAttribute('href'), /v0\.1\.0/)
  await page.setViewportSize({width:375,height:950})
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
  await page.screenshot({path:path.join(output,'workbench-375.png'),fullPage:true})
  await page.setViewportSize({width:1440,height:1000})
  await page.getByLabel('导入可编辑工程').setInputFiles(path.join(release,'taleprism-v0.1.0-last-light-project.zip'))
  await page.getByRole('button',{name:'保存方案',exact:true}).waitFor()
  const project = await page.evaluate(()=>localStorage.getItem('storygal-project'))
  report.project_id = project
  const response = await page.request.get(base+'/api/projects/'+project+'/production')
  const state = await response.json()
  assert.equal(state.plan.shots.length,3)
  assert.ok(state.plan.shots.every(s=>s.continuity_check.reviewer==='assistant'))
  await page.screenshot({path:path.join(output,'workbench-1440.png'),fullPage:true})
  await page.goto(base+'/read/'+project)
  await page.getByRole('button',{name:/^开始阅读/}).click()
  assert.equal(await page.locator('.reader-plate').count(),3)
  for (const image of await page.locator('.reader-plate img').all()) {await image.scrollIntoViewIfNeeded();await image.evaluate(i=>i.decode())}
  const raw = fs.readFileSync(path.join(root,'samples/last-light/source.txt'),'utf8').split(/\r\n|\r|\n/).map(s=>s.replace(/^[ \t\u3000]+|[ \t\u3000]+$/g,'')).join('')
  assert.equal(await page.locator('.reader-paragraph-text').evaluateAll(es=>es.map(e=>e.textContent).join('')),raw)
  report.workbench_import = true
  const site = path.join(release,'site')
  server = http.createServer((req,res)=>{
    const url = decodeURIComponent(req.url.split('?')[0]); if(!url.startsWith('/taleprism/')) {res.writeHead(404).end();return}
    const relative = url.slice('/taleprism/'.length) || 'index.html'
    const file = path.resolve(site,relative)
    if(!file.startsWith(site+path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {res.writeHead(404).end();return}
    res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.json')?'application/json':file.endsWith('.png')?'image/png':'text/html')
    fs.createReadStream(file).pipe(res)
  })
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
  const offline = await browser.newPage({viewport:{width:1440,height:1000}}), apis=[]
  offline.on('pageerror',e=>errors.push(e.message))
  offline.on('request',r=>{if(new URL(r.url()).pathname.includes('/api/'))apis.push(r.url())})
  await offline.goto('http://127.0.0.1:'+server.address().port+'/taleprism/')
  await offline.getByRole('link',{name:'用 Taleprism 制作 ↗'}).waitFor()
  await offline.screenshot({path:path.join(output,'cover-1440.png')})
  await offline.getByRole('button',{name:/^开始阅读/}).click()
  for(const [i,img] of (await offline.locator('.reader-plate img').all()).entries()) {await img.scrollIntoViewIfNeeded();await img.evaluate(e=>e.decode());await offline.screenshot({path:path.join(output,'reader-'+i+'.png')})}
  await offline.setViewportSize({width:375,height:950})
  await offline.locator('.reader-plate img').nth(1).scrollIntoViewIfNeeded()
  assert.equal(await offline.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
  await offline.screenshot({path:path.join(output,'reader-375.png')})
  await offline.reload()
  await offline.waitForSelector('.reader-root')
  assert.deepEqual(apis,[])
  assert.deepEqual(errors,[])
  Object.assign(report,{passed:true,source_equal:true,static_subpath:true,static_without_api:true,desktop_and_mobile:true,system_audio_included:false})
 } catch(e) {report.error=String(e.stack||e);await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});throw e}
 finally {fs.writeFileSync(path.join(output,'browser-report.json'),JSON.stringify(report,null,2));if(server)server.close();await browser.close()}
 console.log(JSON.stringify(report,null,2))
})().catch(e=>{console.error(e);process.exit(1)})
