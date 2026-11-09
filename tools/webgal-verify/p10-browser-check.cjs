const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), http = require('node:http')
const { spawnSync } = require('node:child_process')
const { chromium } = require('playwright')
const root = path.resolve(__dirname, '../..'), out = path.join(root, 'data/verification/p10')
const base = process.argv[2] || 'http://127.0.0.1:8002'
fs.mkdirSync(out, {recursive:true})
;(async()=>{
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true})
  const page = await browser.newPage({viewport:{width:1440,height:1000}}), errors=[]
  page.on('pageerror',e=>errors.push(e.message))
  const report={passed:false, checked_at:new Date().toISOString()}
  let server
  async function json(url,method='GET',data){const r=await page.request.fetch(base+url,{method,data});assert.ok(r.ok(),await r.text());return r.json()}
  try{
    await page.goto(base)
    await page.getByLabel('本地内容包',{exact:true}).selectOption('last-light')
    await page.getByRole('button',{name:'作为新项目打开',exact:true}).click()
    await page.locator('.production-shot').first().waitFor()
    const pid=await page.evaluate(()=>localStorage.getItem('storygal-project')), prefix='/api/projects/'+pid
    report.project_id=pid
    assert.equal(await page.locator('.production-shot').count(),3)
    const shot=page.locator('.production-shot').nth(1)
    await shot.locator('summary').click()
    await page.screenshot({path:path.join(out,'production-1440.png')})
    const before=await json(prefix+'/production')
    const input=shot.getByRole('textbox',{name:'镜头与视角',exact:true}), value=await input.inputValue()
    await input.fill(value+' 保留两人的等待与距离。')
    assert.equal(await page.getByRole('link',{name:'下载生图提示词',exact:true}).getAttribute('aria-disabled'),'true')
    await page.getByRole('button',{name:'保存方案',exact:true}).click()
    await page.waitForFunction(()=>document.querySelectorAll('.production-shot summary')[1]?.textContent.includes('待审方案'))
    await shot.locator('summary').click()
    await shot.getByRole('button',{name:'确认此镜头方案',exact:true}).click()
    await page.waitForFunction(()=>document.querySelectorAll('.production-shot summary')[1]?.textContent.includes('方案已确认'))
    const applied=page.waitForResponse(r=>r.url().endsWith('/production/apply') && r.request().method()==='POST')
    await page.getByRole('button',{name:'应用已确认镜头',exact:true}).click()
    assert.ok((await applied).ok())
    await page.getByRole('button',{name:'应用已确认镜头',exact:true}).waitFor({state:'visible'})
    const after=await json(prefix+'/production');assert.ok(after.revision>before.revision)
    assert.ok((await json(prefix+'/production/tasks')).tasks[1].prompt.includes('等待与距离'))
    const raw=fs.readFileSync(path.join(root,'samples/last-light/source.txt'))
    assert.deepEqual(await(await page.request.get(base+prefix+'/source')).body(),raw)
    report.edit_confirm_apply=true
    for(const width of [375,768]){
      await page.setViewportSize({width,height:900})
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
      await page.screenshot({path:path.join(out,'production-'+width+'.png')})
    }
    // Download and re-import through the actual upload control.
    const download=page.waitForEvent('download');await page.getByRole('link',{name:/下载可编辑工程/}).click()
    const zip=path.join(out,'roundtrip.storygal.zip');await(await download).saveAs(zip)
    await page.getByLabel('导入可编辑工程',{exact:true}).setInputFiles(zip)
    await page.waitForFunction(old=>localStorage.getItem('storygal-project')!==old,pid)
    const newId=await page.evaluate(()=>localStorage.getItem('storygal-project'))
    assert.deepEqual(await(await page.request.get(base+'/api/projects/'+newId+'/source')).body(),raw)
    report.ui_project_roundtrip=true
    await page.setViewportSize({width:1440,height:1000})
    await page.goto(base+'/read/'+pid)
    await page.getByRole('button',{name:/^开始阅读/}).click()
    assert.equal(await page.locator('.reader-plate').count(),3)
    const visible=raw.toString().split(/\r\n|\r|\n/).map(s=>s.replace(/^[ \t\u3000]+|[ \t\u3000]+$/g,'')).join('')
    assert.equal(await page.locator('.reader-paragraph-text').evaluateAll(es=>es.map(e=>e.textContent).join('')),visible)
    for(const [i,plate] of (await page.locator('.reader-plate').all()).entries()){
      await plate.scrollIntoViewIfNeeded();await plate.locator('img').evaluate(img=>img.decode())
      await page.screenshot({path:path.join(out,'reader-plate-'+i+'.png')})
    }
    for(const width of [320,375,768,1440]){
      await page.setViewportSize({width,height:950})
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
      await page.screenshot({path:path.join(out,'reader-'+width+'.png')})
    }
    await page.getByRole('button',{name:'设置',exact:true}).click()
    await page.getByRole('button',{name:'本章对白',exact:true}).click()
    await page.locator('.reader-results>button').first().click()
    await page.waitForFunction(()=>document.querySelector('audio')?.currentTime>0)
    report.source_images_audio=true
    const jid=(await json(prefix+'/reader/exports','POST')).job_id
    let job
    for(let i=0;i<150;i++){job=(await json(prefix+'/jobs')).find(j=>j.id===jid);if(['completed','failed'].includes(job.state))break;await page.waitForTimeout(100)}
    assert.equal(job.state,'completed',JSON.stringify(job))
    const readerZip=path.join(out,'last-light-reader.zip');fs.writeFileSync(readerZip,await(await page.request.get(base+job.result.download_url)).body())
    const dir=path.join(out,'standalone',jid);fs.mkdirSync(dir,{recursive:true})
    assert.equal(spawnSync('unzip',['-q','-o',readerZip,'-d',dir]).status,0)
    const check=spawnSync('python3',['verify_package.py'],{cwd:dir,encoding:'utf8'});assert.equal(check.status,0,check.stdout+check.stderr)
    server=http.createServer((req,res)=>{const f=path.resolve(dir,'.'+decodeURIComponent(req.url.split('?')[0]==='/'?'/index.html':req.url.split('?')[0]));if(!f.startsWith(dir+path.sep)||!fs.existsSync(f)){res.writeHead(404).end();return}res.setHeader('Content-Type',f.endsWith('.js')?'application/javascript':f.endsWith('.css')?'text/css':f.endsWith('.json')?'application/json':f.endsWith('.png')?'image/png':f.endsWith('.wav')?'audio/wav':'text/html');fs.createReadStream(f).pipe(res)})
    await new Promise(r=>server.listen(0,'127.0.0.1',r))
    const independent=await browser.newPage(),apiRequests=[]
    independent.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))apiRequests.push(r.url())})
    await independent.goto('http://127.0.0.1:'+server.address().port+'/')
    await independent.getByRole('button',{name:/^开始阅读/}).click()
    assert.equal(await independent.locator('.reader-plate').count(),3)
    await independent.locator('.reader-plate img').first().evaluate(img=>img.decode())
    assert.deepEqual(apiRequests,[])
    assert.deepEqual(errors,[])
    assert.deepEqual((await json(prefix+'/delivery')).records,[])
    Object.assign(report,{passed:true,standalone_without_api:true,export_id:jid,export:job.result,manual_review:'pending'})
  }catch(e){report.error=String(e.stack||e);await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});throw e}
  finally{fs.writeFileSync(path.join(out,'browser-report.json'),JSON.stringify(report,null,2));if(server)server.close();await browser.close()}
  console.log(JSON.stringify(report,null,2))
})().catch(e=>{console.error(e);process.exit(1)})
