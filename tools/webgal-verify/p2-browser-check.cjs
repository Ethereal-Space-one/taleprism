const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');
const base=process.argv[2]||'http://127.0.0.1:8000';
const out=path.resolve(__dirname,'../../data/verification/p2');fs.mkdirSync(out,{recursive:true});
const report={passed:false,checked_at:new Date().toISOString()};
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--autoplay-policy=no-user-gesture-required']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 async function json(url,method='GET',data){const r=await page.request.fetch(base+url,{method,data});assert.ok(r.ok(),await r.text());return r.json()}
 try{
  const story='孔明曰：「此都督病源也。」\n周瑜曰：「願先生賜教。」\n孔明笑曰：「亮有一方。」';
  const r=await page.request.post(base+'/api/projects',{multipart:{file:{name:'P2-有声验收.txt',mimeType:'text/plain',buffer:Buffer.from(story)},rights_status:'public_domain'}});
  const project=await r.json(),pid=project.id;report.project_id=pid;
  let review=await json(`/api/projects/${pid}/review`);
  for(const c of review.characters){await json(`/api/projects/${pid}/characters/${c.id}`,'PATCH',{revision:review.revision,display_name:c.display_name,aliases:[],status:'confirmed'});review=await json(`/api/projects/${pid}/review`)}
  for(const d of review.dialogues){await json(`/api/projects/${pid}/dialogues`,'PATCH',{revision:review.revision,dialogue_ids:[d.id],speaker_id:d.suggested_speaker_id});review=await json(`/api/projects/${pid}/review`)}
  const state=()=>json(`/api/projects/${pid}/speech`);
  async function until(fn){for(let i=0;i<120;i++){const s=await state();if(fn(s))return s;await page.waitForTimeout(150)}throw Error('state timeout')}
  async function job(kind,previous){for(let i=0;i<140;i++){const jobs=await json(`/api/projects/${pid}/jobs`);const j=jobs.find(j=>j.kind===kind);if(j&&j.id!==previous&&j.state!=='running'){assert.equal(j.state,'completed',j.error);return j}await page.waitForTimeout(500)}throw Error('job timeout')}
  await page.goto(base);await page.evaluate(id=>localStorage.setItem('storygal-project',id),pid);await page.reload();
  await page.getByRole('button',{name:'对白配音',exact:true}).click();
  for(const [name,voice] of [['孔明','Eddy (中文（中国大陆）)'],['周瑜','Tingting']]){
   const form=page.locator('.voice-profiles form').filter({has:page.getByRole('heading',{name,exact:true})});await form.locator('select').selectOption((await state()).capabilities.voices.find(v=>v.startsWith(voice)) || voice);await form.getByRole('button',{name:'保存音色'}).click();await until(s=>Object.values(s.profiles).some(p=>p.voice.startsWith(voice)));
  }
  const generated=[];
  for(let i=0;i<3;i++){
   await page.getByLabel(`为对白 ${i+1} 配音`,{exact:true}).click();await until(s=>s.lines[i].selected);
   const line=page.locator('.speech-line').nth(i);
   await line.getByRole('button',{name:'合成此句（优先缓存）',exact:true}).click();const j=await job('speech',generated.at(-1));generated.push(j.id);
   await line.locator('audio').waitFor();await line.locator('audio').evaluate(async a=>{await a.play()});await page.waitForTimeout(250);
   assert.ok(await line.locator('audio').evaluate(a=>a.duration>0&&a.currentTime>0));await line.locator('audio').evaluate(a=>a.pause());
   await line.getByRole('button',{name:'接受本句音频'}).click();await until(s=>!!s.lines[i].segments[0].accepted);
  }
  const before=await state();const stable=before.lines[1].segments[0].accepted.id;
  const first=page.locator('.speech-line').first();await first.getByRole('button',{name:'合成此句（优先缓存）'}).click();const cached=await job('speech',generated.at(-1));assert.equal(cached.result.generated,0);assert.equal(cached.result.reused,1);
  await first.getByLabel('片段 1 读音文本').fill('此都督病原也。');await first.getByRole('button',{name:'保存读音修正'}).click();await until(s=>!s.lines[0].segments[0].accepted);
  await first.getByRole('button',{name:'合成此句（优先缓存）'}).click();const changed=await job('speech',cached.id);assert.equal(changed.result.generated,1);
  await first.getByRole('button',{name:'接受本句音频'}).click();await until(s=>!!s.lines[0].segments[0].accepted);
  assert.equal((await state()).lines[1].segments[0].accepted.id,stable);
  for(const width of [320,375,414,768,1440]){await page.setViewportSize({width,height:1000});await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:path.join(out,`speech-${width}.png`),fullPage:true})}
  await page.getByRole('button', { name: '交付检查', exact: true }).click();
  await page.getByText('其他格式 · WebGAL 兼容导出', { exact: true }).click();
  await page.getByRole('button', { name: '检查 WebGAL 兼容性', exact: true }).click();
  await page.getByRole('dialog', { name: 'WebGAL 兼容导出' }).getByRole('button', { name: '导出 WebGAL 兼容版', exact: true }).click();const exported=await job('export');report.export_url=exported.result.play_url;
  const manifest=await json(report.export_url.replace('index.html','storygal-manifest.json'));assert.equal(manifest.units.filter(u=>u.vocal_id).length,3);
  const source=await page.request.get(base+`/api/projects/${pid}/source`);assert.equal((await source.body()).toString(),story);
  const engine=await browser.newPage({viewport:{width:1440,height:1000}});engine.on('pageerror',e=>errors.push(e.message));
  await engine.addInitScript(()=>{window.__speechPlays=[];document.addEventListener('playing',e=>{if(e.target instanceof HTMLMediaElement)window.__speechPlays.push({src:e.target.currentSrc,duration:e.target.duration})},true);const original=AudioBufferSourceNode.prototype.start;AudioBufferSourceNode.prototype.start=function(...args){window.__speechPlays.push({duration:this.buffer?.duration,buffer:true});return original.apply(this,args)}});
  const fetched=new Set();engine.on('response',r=>{if(r.url().includes('/game/vocal/')&&r.status()===200)fetched.add(r.url())});
  await engine.goto(base+report.export_url);await engine.locator('.html-body__title-enter').click();await engine.locator('.html-body__title-enter').waitFor({state:'hidden'});if(await engine.getByText('简体中文',{exact:true}).isVisible())await engine.getByText('简体中文',{exact:true}).click();await engine.getByText('开始游戏',{exact:true}).first().locator('..').click();await engine.locator('#textBoxMain').waitFor();await engine.waitForTimeout(1800);
  for(const u of manifest.units){await engine.waitForFunction(t=>Array.from(document.querySelectorAll('#textBoxMain span[id]>span')).map(e=>e.firstChild.textContent).join('')===t,u.text);if(await engine.locator('#textBoxMain .Textelement_start').count()){await engine.mouse.click(700,300);await engine.waitForFunction(()=>!document.querySelector('#textBoxMain .Textelement_start'))}await engine.waitForTimeout(350);await engine.mouse.click(700,300)}
  await engine.waitForFunction(()=>!document.querySelector('#textBoxMain'));const plays=await engine.evaluate(()=>window.__speechPlays);assert.equal(fetched.size,3);assert.ok(plays.filter(p=>p.src?.includes('/game/vocal/')||p.buffer&&p.duration>0&&p.duration<10).length>=3,JSON.stringify(plays));assert.deepEqual(errors,[]);
  Object.assign(report,{passed:true,voices:Object.values((await state()).profiles).map(p=>p.voice),preview_played:3,exported_audio:3,engine_audio_started:true,cache_hit:true,only_changed_segment_regenerated:true,source_unchanged:true,viewports:[320,375,414,768,1440]});console.log(JSON.stringify(report));
 }catch(e){report.error=String(e.stack||e);throw e}finally{fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
