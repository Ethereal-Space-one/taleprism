const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http')
const {spawnSync}=require('node:child_process'),{chromium}=require('playwright')
const root=path.resolve(__dirname,'../..'),out=path.join(root,'data/verification/p11'),base=process.argv[2]||'http://127.0.0.1:8000'
;(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true})
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],report={passed:false,checked_at:new Date().toISOString()};let server
 page.on('pageerror',e=>errors.push(e.message))
 async function json(url,method='GET',data){const r=await page.request.fetch(base+url,{method,data});assert.ok(r.ok(),await r.text());return r.json()}
 try {
   const p=await json('/api/content-packs/last-light','POST'),pid=p.id,prefix='/api/projects/'+pid;report.project_id=pid
   await page.goto(base);await page.evaluate(id=>localStorage.setItem('storygal-project',id),pid);await page.reload()
   await page.getByRole('button',{name:'章节制作方案',exact:true}).click()
   const shot=page.locator('.production-shot').nth(1)
   await shot.locator(':scope > summary').click()
   assert.equal(await shot.locator('.continuity-compare img').count(),3)
   const before=await json(prefix+'/production');assert.equal(before.plan.scenes.length,1);assert.ok(before.plan.shots.every(s=>s.continuity_check.reviewer==='assistant'))
   await shot.locator('.continuity-compare').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'continuity-1440.png')})
   const field=shot.getByRole('textbox',{name:'本镜头允许改变什么',exact:true});await field.fill((await field.inputValue())+' 检查时保留物件去向。')
   const saved=page.waitForResponse(r=>r.url().endsWith('/production')&&r.request().method()==='PUT')
   await page.getByRole('button',{name:'保存方案',exact:true}).click();assert.ok((await saved).ok());await page.waitForFunction(()=>!document.querySelectorAll('.production-shot')[1]?.open)
   await page.waitForFunction(()=>document.querySelectorAll('.production-shot > summary')[1]?.textContent.includes('待审方案'))
   const state=await json(prefix+'/production');assert.ok(state.plan.shots[0].continuity_check);assert.equal(state.plan.shots[1].continuity_check,null);assert.equal(state.plan.shots[2].continuity_check,null)
   for(const i of [1,2]){
      const s=page.locator('.production-shot').nth(i);await s.locator(':scope > summary').click()
      await s.getByRole('button',{name:'确认此镜头方案',exact:true}).click()
      await page.waitForFunction(i=>document.querySelectorAll('.production-shot > summary')[i]?.textContent.includes('方案已确认'),i)
      await s.locator(':scope > summary').click()
      for(const box of await s.locator('.continuity-checklist input').all())await box.check()
      await s.getByRole('textbox',{name:'连续性检查说明',exact:true}).fill('浏览器流程测试：已人工对照母版与前序图；此临时项目仅验证表单，不作为最终发布复核。')
      const response=page.waitForResponse(r=>r.url().endsWith('/continuity-check')&&r.request().method()==='POST')
      await s.getByRole('button',{name:'记录连续性检查',exact:true}).click();assert.ok((await response).ok())
      await page.waitForFunction(i=>!document.querySelectorAll('.production-shot')[i]?.open,i)
   }
   const applied=page.waitForResponse(r=>r.url().endsWith('/production/apply')&&r.request().method()==='POST')
   await page.getByRole('button',{name:'应用已确认镜头',exact:true}).click();assert.ok((await applied).ok())
   report.edit_invalidates_following_checks=true
   await page.setViewportSize({width:375,height:950});await shot.locator(':scope > summary').click();await shot.locator('.continuity-compare').scrollIntoViewIfNeeded()
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
   await page.screenshot({path:path.join(out,'continuity-375.png')})
   const raw=fs.readFileSync(path.join(root,'samples/last-light/source.txt'))
   assert.deepEqual(await(await page.request.get(base+prefix+'/source')).body(),raw)
   const bundle=await(await page.request.get(base+prefix+'/bundle')).body()
   const restored=await page.request.post(base+'/api/project-bundles',{multipart:{file:{name:'project.zip',mimeType:'application/zip',buffer:bundle}}});assert.ok(restored.ok(),await restored.text())
   const restoredId=(await restored.json()).id
   assert.deepEqual((await json('/api/projects/'+restoredId+'/production')).plan,(await json(prefix+'/production')).plan)
   report.checks_survive_migration=true
   await page.setViewportSize({width:1440,height:1000});await page.goto(base+'/read/'+pid);await page.getByRole('button',{name:/^开始阅读/}).click()
   assert.equal(await page.locator('.reader-plate').count(),3)
   for(const [i,img] of (await page.locator('.reader-plate img').all()).entries()){await img.scrollIntoViewIfNeeded();await img.evaluate(e=>e.decode());await page.screenshot({path:path.join(out,'reader-'+i+'.png')})}
   const text=raw.toString().split(/\r\n|\r|\n/).map(s=>s.replace(/^[ \t\u3000]+|[ \t\u3000]+$/g,'')).join('')
   assert.equal(await page.locator('.reader-paragraph-text').evaluateAll(es=>es.map(e=>e.textContent).join('')),text)
   await page.setViewportSize({width:375,height:950});await page.locator('.reader-plate img').nth(2).scrollIntoViewIfNeeded();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:path.join(out,'reader-375.png')})
   await page.getByRole('button',{name:'设置',exact:true}).click();await page.getByRole('button',{name:'本章对白',exact:true}).click();await page.locator('.reader-results>button').first().click();await page.waitForFunction(()=>document.querySelector('audio')?.currentTime>0)
   const jid=(await json(prefix+'/reader/exports','POST')).job_id;let job
   for(let i=0;i<150;i++){job=(await json(prefix+'/jobs')).find(j=>j.id===jid);if(['completed','failed'].includes(job.state))break;await page.waitForTimeout(100)}assert.equal(job.state,'completed',JSON.stringify(job))
   const zip=path.join(out,'last-light-continuity-reader.zip');fs.writeFileSync(zip,await(await page.request.get(base+job.result.download_url)).body());const dir=path.join(out,'standalone',jid);fs.mkdirSync(dir,{recursive:true});assert.equal(spawnSync('unzip',['-q','-o',zip,'-d',dir]).status,0)
   const verify=spawnSync('python3',['verify_package.py'],{cwd:dir,encoding:'utf8'});assert.equal(verify.status,0,verify.stdout+verify.stderr)
   server=http.createServer((req,res)=>{const f=path.resolve(dir,'.'+decodeURIComponent(req.url.split('?')[0]==='/'?'/index.html':req.url.split('?')[0]));if(!f.startsWith(dir+path.sep)||!fs.existsSync(f)){res.writeHead(404).end();return}res.setHeader('Content-Type',f.endsWith('.js')?'application/javascript':f.endsWith('.css')?'text/css':f.endsWith('.json')?'application/json':f.endsWith('.png')?'image/png':f.endsWith('.wav')?'audio/wav':'text/html');fs.createReadStream(f).pipe(res)})
   await new Promise(r=>server.listen(0,'127.0.0.1',r));const independent=await browser.newPage(),requests=[];independent.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))requests.push(r.url())});await independent.goto('http://127.0.0.1:'+server.address().port+'/');await independent.getByRole('button',{name:/^开始阅读/}).click();await independent.locator('.reader-plate img').nth(2).scrollIntoViewIfNeeded();await independent.locator('.reader-plate img').nth(2).evaluate(e=>e.decode());assert.deepEqual(requests,[])
   assert.deepEqual(errors,[]);assert.deepEqual((await json(prefix+'/delivery')).records,[])
   Object.assign(report,{passed:true,source_equal:true,real_audio:true,standalone_without_api:true,export:job.result})
 }catch(e){report.error=String(e.stack||e);await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});throw e}
 finally{fs.writeFileSync(path.join(out,'browser-report.json'),JSON.stringify(report,null,2));if(server)server.close();await browser.close()}
 console.log(JSON.stringify(report,null,2))
})().catch(e=>{console.error(e);process.exit(1)})
