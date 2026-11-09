const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), http = require('node:http')
const { spawnSync } = require('node:child_process')
const { chromium } = require('playwright')
const root = path.resolve(__dirname, '../..'), out = path.join(root, 'data/verification/p9')
const fixture = JSON.parse(fs.readFileSync(path.join(out, 'fixture.json')))
const base = process.argv[2] || 'http://127.0.0.1:8000'
;(async () => {
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors = []
  page.on('pageerror', e => errors.push(e.message))
  const report = { passed: false, checked_at: new Date().toISOString(), project_id: fixture.project_id }
  let server
  async function json(url, method='GET', data) {
    const r = await page.request.fetch(base + url, { method, data }); assert.ok(r.ok(), await r.text()); return r.json()
  }
  async function close() { const title=await page.locator('#reader-panel-title').textContent(); await page.getByRole('button', {name:'关闭面板',exact:true}).click(); await page.waitForFunction(old => !document.querySelector('dialog[open]') || document.querySelector('#reader-panel-title')?.textContent !== old,title) }
  async function plate(id, fraction=0.2) {
    const figure = page.locator(`[data-illustration-id="${id}"]`)
    await figure.locator('img').scrollIntoViewIfNeeded()
    await figure.locator('img').evaluate(img => img.decode())
    await page.locator('.reader-scroll').dispatchEvent('wheel')
    await figure.evaluate((e, fraction) => { const r=e.closest('.reader-scroll'), rect=e.getBoundingClientRect(); r.scrollTop += rect.top - r.getBoundingClientRect().top - 24 + rect.height*fraction; }, fraction)
    await page.waitForTimeout(450)
    return figure
  }
  try {
    const prefix = '/api/projects/' + fixture.project_id
    const data = await json(prefix + '/reader/content')
    assert.equal(data.schema_version,3)
    assert.equal(data.config.illustrations.length,12)
    await page.goto(base + fixture.reader_url)
    await page.getByRole('button',{name:/^开始阅读/}).click()
    assert.equal(await page.locator('.reader-root').evaluate(e=>e.classList.contains('is-illustrated')),true)
    assert.equal(await page.locator('.reader-stage').count(),0)
    assert.equal(await page.locator('.reader-plate').count(),12)
    const raw=fs.readFileSync(path.join(root,'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'))
    assert.deepEqual(await (await page.request.get(base+prefix+'/source')).body(),raw)
    const visible=raw.toString().split(/\r\n|\r|\n/).map(s=>s.replace(/^[ \t\u3000]+|[ \t\u3000]+$/g,'')).join('')
    assert.equal(await page.locator('.reader-paragraph-text').evaluateAll(es=>es.map(e=>e.textContent).join('')),visible)
    const imageWidth = await page.locator('.reader-plate').first().evaluate(e=>e.getBoundingClientRect().width)
    const proseWidth = await page.locator('.reader-paragraph:not(.reader-chapter)').first().evaluate(e=>e.getBoundingClientRect().width)
    assert.ok(imageWidth > proseWidth*1.5)
    for (const p of data.config.illustrations) {
      const f=await plate(p.id,0)
      assert.equal(await f.locator('img').evaluate(e=>getComputedStyle(e).objectFit),'contain')
      const previous=await f.evaluate(e=>e.previousElementSibling.dataset.byteStart)
      assert.equal(data.blocks.find(b=>b.byte_end===p.after_byte).byte_start,Number(previous))
      await page.screenshot({path:path.join(out,p.id+'-1440.png')})
    }
    report.full_frame_plates=12
    report.image_to_text_width_ratio=imageWidth/proseWidth
    report.source_equal=true
    await plate('orders-ensemble',0.25)
    assert.equal(await page.locator('.reader-root').getAttribute('data-view-plate'),'orders-ensemble')
    const anchor=await page.locator('.reader-root').getAttribute('data-view-byte')
    await page.reload()
    await page.getByRole('button',{name:/^继续阅读/}).click()
    await page.waitForTimeout(350)
    assert.equal(await page.locator('.reader-root').getAttribute('data-view-plate'),'orders-ensemble')
    for (const width of [320,375,414,768,1440]) {
      await page.setViewportSize({width,height:1000}); await page.waitForTimeout(400)
      assert.equal(await page.locator('.reader-root').getAttribute('data-view-byte'),anchor)
      assert.equal(await page.locator('.reader-root').getAttribute('data-view-plate'),'orders-ensemble')
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
      await page.screenshot({path:path.join(out,'ensemble-resume-'+width+'.png')})
    }
    report.image_resume_and_resize=true
    const resume=await page.locator('.reader-root').getAttribute('data-resume-byte')
    await page.getByRole('button',{name:'设置',exact:true}).click()
    await page.getByRole('button',{name:/^本章画卷/}).click()
    assert.equal(await page.locator('.reader-gallery>div>button').count(),12)
    await page.locator('.reader-gallery>div>button').filter({hasText:'军帐授计'}).click()
    await page.getByRole('button',{name:'放大细节 2×',exact:true}).click()
    assert.ok(await page.locator('.reader-image-viewport').evaluate(e=>e.scrollWidth>e.clientWidth))
    await page.getByRole('button',{name:'恢复完整画面',exact:true}).click()
    report.pan_zoom_detail_view=true
    await page.getByRole('button',{name:'下一幅',exact:true}).click()
    await page.getByRole('button',{name:'上一幅',exact:true}).click()
    assert.equal(await page.locator('.reader-gallery-controls>span').textContent(),'军帐授计')
    assert.equal(await page.locator('.reader-root').getAttribute('data-resume-byte'),resume)
    await close(); await close(); await close()
    await page.getByRole('button',{name:'设置',exact:true}).click()
    await page.getByLabel('画面排布',{exact:true}).selectOption('split')
    await close()
    assert.equal(await page.locator('.reader-stage').count(),1)
    assert.equal(await page.locator('.reader-plate').count(),0)
    assert.equal(await page.locator('.reader-root').getAttribute('data-view-byte'),anchor)
    await page.getByRole('button',{name:'设置',exact:true}).click()
    await page.getByLabel('画面排布',{exact:true}).selectOption('illustrated')
    await close()
    assert.equal(await page.locator('.reader-plate').count(),12)
    report.gallery_and_layout_preserve_reading=true
    await page.getByRole('button',{name:'搜索',exact:true}).click()
    await page.getByLabel('查找原文',{exact:true}).fill('趙雲拈弓搭箭')
    await page.locator('.reader-results>button').first().click()
    assert.equal(await page.locator('.reader-root').getAttribute('data-resume-byte'),resume)
    await page.getByRole('button',{name:'返回阅读处',exact:true}).click()
    await page.waitForTimeout(250)
    assert.equal(await page.locator('.reader-root').getAttribute('data-view-byte'),anchor)
    report.search_return=true
    await page.getByRole('button',{name:'设置',exact:true}).click()
    await page.getByRole('button',{name:'本章对白',exact:true}).click()
    await page.locator('.reader-results>button').first().click()
    await page.waitForFunction(()=>document.querySelector('audio').currentTime>0)
    report.real_existing_audio=true
    const jobId=(await json(prefix+'/reader/exports','POST')).job_id
    let job
    for(let i=0;i<200;i++){job=(await json(prefix+'/jobs')).find(j=>j.id===jobId);if(job.state!=='running')break;await page.waitForTimeout(100)}
    assert.equal(job.state,'completed',JSON.stringify(job))
    const zip=path.join(out,'storygal-reader-p9.zip');fs.writeFileSync(zip,await(await page.request.get(base+job.result.download_url)).body())
    const dir=path.join(out,'standalone',job.id);fs.mkdirSync(dir,{recursive:true})
    assert.equal(spawnSync('unzip',['-q','-o',zip,'-d',dir]).status,0)
    const check=spawnSync('python3',['verify_package.py'],{cwd:dir,encoding:'utf8'});assert.equal(check.status,0,check.stdout+check.stderr)
    assert.ok(fs.existsSync(path.join(dir,'storygal-source/narrative-v1/prompts.json')))
    server=http.createServer((req,res)=>{const f=path.resolve(dir,'.'+decodeURIComponent(req.url.split('?')[0]==='/'?'/index.html':req.url.split('?')[0]));if(!f.startsWith(dir+path.sep)||!fs.existsSync(f)){res.writeHead(404).end();return}res.setHeader('Content-Type',f.endsWith('.js')?'application/javascript':f.endsWith('.css')?'text/css':f.endsWith('.json')?'application/json':f.endsWith('.png')?'image/png':f.endsWith('.wav')?'audio/wav':'text/html');fs.createReadStream(f).pipe(res)})
    await new Promise(r=>server.listen(0,'127.0.0.1',r))
    const independent=await browser.newPage(), requests=[]
    independent.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))requests.push(r.url())})
    await independent.goto('http://127.0.0.1:'+server.address().port+'/')
    await independent.getByRole('button',{name:/^开始阅读/}).click()
    assert.equal(await independent.locator('.reader-plate').count(),12)
    const first=independent.locator('.reader-plate').first().locator('img');await first.evaluate(img=>img.decode())
    assert.deepEqual(requests,[])
    assert.equal((await json(prefix+'/delivery')).records.length,0)
    assert.deepEqual(errors,[])
    Object.assign(report,{passed:true,independent_export:true,files:job.result.file_count,reader_url:fixture.reader_url,export_url:job.result.play_url,download_url:job.result.download_url,export_id:job.id,manual_review:'pending'})
  } catch(e) { report.error=String(e.stack||e);await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});throw e }
  finally { fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));if(server)server.close();await browser.close() }
  console.log(JSON.stringify(report,null,2))
})().catch(e=>{console.error(e);process.exit(1)})
