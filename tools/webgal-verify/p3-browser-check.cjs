const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');const {chromium}=require('playwright');
const base=process.argv[2]||'http://127.0.0.1:8000';const root=path.resolve(__dirname,'../..');const output=path.join(root,'data/verification/p3');fs.mkdirSync(output,{recursive:true});
const report={checked_at:new Date().toISOString(),passed:false};
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 let engine; const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 async function request(url,method='GET',data){const r=await page.request.fetch(base+url,{method,data});assert.ok(r.ok(),await r.text());return r.json()}
 try{
  const raw=fs.readFileSync(path.join(root,'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'));
  const uploaded=await page.request.post(base+'/api/projects',{multipart:{file:{name:'P3-赤壁视觉验收.txt',mimeType:'text/plain',buffer:raw},rights_status:'public_domain'}});const project=await uploaded.json(),pid=project.id;report.project_id=pid;
  const text=await request(`/api/projects/${pid}/text`);const state=()=>request(`/api/projects/${pid}/visual`);
  async function until(test){for(let i=0;i<120;i++){const s=await state();if(test(s))return s;await page.waitForTimeout(150)}throw Error('visual state timeout')}
  const source=raw.toString();const position=source.indexOf('黃蓋用刀一招');assert.ok(position>0);
  const startChar=source.lastIndexOf('\n',position)+1,endChar=source.indexOf('\n',position);
  const start=Buffer.byteLength(source.slice(0,startChar)),end=Buffer.byteLength(source.slice(0,endChar));
  const ids=text.spans.filter(s=>s.byte_start>=start&&s.byte_end<=end&&s.kind!=='whitespace').map(s=>s.id);
  const anchor=text.units.find(u=>u.byte_end>=end).byte_end;
  const item=await request(`/api/projects/${pid}/visual/items`,'POST',{revision:0,kind:'illustration',title:'火船原文场景',anchor_byte:anchor,evidence_span_ids:ids,graph:null});
  await page.goto(base);await page.evaluate(id=>localStorage.setItem('storygal-project',id),pid);await page.reload();await page.getByRole('button',{name:'视觉与图解',exact:true}).click();
  await page.getByRole('button',{name:'导入 Codex 赤壁火船候选图'}).click();await until(s=>s.items.find(i=>i.id===item.id).asset);
  await page.getByRole('button',{name:'接受并启用',exact:true}).click();await until(s=>s.items.find(i=>i.id===item.id).enabled);
  await page.getByRole('button',{name:'导入赤壁证据图解'}).click();let s=await until(s=>s.items.some(i=>i.kind==='diagram'));const diagram=s.items.find(i=>i.kind==='diagram');
  await page.getByRole('button',{name:'生成图解预览'}).click();await until(s=>s.items.find(i=>i.id===diagram.id).asset);
  await page.getByRole('img',{name:'根据原文生成的示意图预览'}).waitFor();await page.locator('.visual-preview').screenshot({path:path.join(output,'diagram-preview.png')});
  assert.equal(await page.getByRole('button',{name:'接受并启用',exact:true}).isDisabled(),true);
  await page.getByLabel('我已逐项核对节点、连线和方向的原文依据').check();await page.getByRole('button',{name:'接受并启用',exact:true}).click();
  s=await until(s=>s.items.find(i=>i.id===diagram.id).enabled);assert.equal(s.items.filter(i=>i.enabled).length,2);
  for(const width of [320,375,414,768,1440]){await page.setViewportSize({width,height:1000});await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:path.join(output,`visual-${width}.png`),fullPage:true})}
  await page.getByRole('button',{name:'导出 WebGAL'}).click();let job;
  for(let i=0;i<120;i++){job=(await request(`/api/projects/${pid}/jobs`)).find(j=>j.kind==='export');if(job&&job.state!=='running')break;await page.waitForTimeout(500)}assert.equal(job.state,'completed',job.error);
  report.export_url=job.result.play_url;const manifest=await request(report.export_url.replace('index.html','storygal-manifest.json'));assert.equal(manifest.visual_events.length,2);
  const original=await page.request.get(base+`/api/projects/${pid}/source`);assert.ok((await original.body()).equals(raw));
  engine=await browser.newPage({viewport:{width:1440,height:1000}});engine.on('pageerror',e=>errors.push(e.message));const fetched=new Set();engine.on('response',r=>{if(manifest.visual_events.some(e=>r.url().endsWith('/'+e.asset_id+'.png'))&&r.status()===200)fetched.add(r.url())});
  await engine.goto(base+report.export_url);await engine.locator('.html-body__title-enter').click();await engine.locator('.html-body__title-enter').waitFor({state:'hidden'});if(await engine.getByText('简体中文',{exact:true}).isVisible())await engine.getByText('简体中文',{exact:true}).click();await engine.getByText('开始游戏',{exact:true}).first().locator('..').click();await engine.locator('#textBoxMain').waitFor();await engine.waitForTimeout(1800);
  let shown=0;
  for(const unit of manifest.units){ report.last_frame=unit.id;
   await engine.waitForFunction(t=>Array.from(document.querySelectorAll('#textBoxMain span[id]>span')).map(e=>e.firstChild.textContent).join('')===t,unit.text,{timeout:6000});
   if(await engine.locator('#textBoxMain .Textelement_start').count()){await engine.mouse.click(700,300);await engine.waitForFunction(()=>!document.querySelector('#textBoxMain .Textelement_start'))}
   await engine.mouse.click(700,300);
   for(const event of manifest.visual_events.filter(e=>e.after_unit_id===unit.id)){
    await engine.waitForFunction(()=>!document.querySelector('#textBoxMain'));await engine.waitForTimeout(1000);await engine.screenshot({path:path.join(output,`playing-${event.kind}.png`)});shown++;await engine.mouse.click(700,300);
   }
   if(unit.id%50===0)console.log(`P3: ${unit.id+1}/${manifest.units.length} frames`);
  }
  await engine.waitForFunction(()=>!document.querySelector('#textBoxMain'));assert.equal(shown,2);assert.equal(fetched.size,2);assert.deepEqual(errors,[]);
  Object.assign(report,{passed:true,original_bytes_equal:true,text_frames:manifest.units.length,visual_pages:shown,visual_resources:fetched.size,reached_end:true,manual_evidence_gate:true,viewports:[320,375,414,768,1440]});console.log(JSON.stringify(report));
 }catch(e){if(engine){report.current_text=await engine.locator('#textBoxMain span[id]>span').evaluateAll(es=>es.map(e=>e.firstChild.textContent).join(''));await engine.screenshot({path:path.join(output,'failure.png')})}report.error=String(e.stack||e);throw e}finally{fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
