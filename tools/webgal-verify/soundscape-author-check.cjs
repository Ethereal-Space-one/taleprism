// Real browser / actual renderer / real WAVs / no shared user projects.
// Build the workbench first. CHROME_PATH=/path/to/chromium node this-file.cjs
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net')
const {spawn,spawnSync}=require('node:child_process'),{chromium}=require('playwright')
const root=path.resolve(__dirname,'../..'),python=process.env.BACKEND_PYTHON || path.join(root,'backend/.venv/bin/python')
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'tale-sound-author-'))
let server,browser
function check(s){console.log('PASS '+s)}
const file=(name,buffer,mimeType)=>({name,buffer:Buffer.from(buffer),mimeType})
function tone(){const n=16800,b=Buffer.alloc(44+n*2);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(24000,24);b.writeUInt32LE(48000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(n*2,40);for(let i=0;i<n;i++)b.writeInt16LE(Math.round(800*Math.sin(i*.05)),44+i*2);return b}
async function main(){
 const port=await new Promise(ok=>{const s=net.createServer().listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>ok(p))})}),url='http://127.0.0.1:'+port
 server=spawn(python,['-m','uvicorn','storygal.app:app','--host','127.0.0.1','--port',String(port),'--log-level','warning'],{cwd:root,env:{...process.env,STORYGAL_DATA_DIR:temp,PYTHONPATH:path.join(root,'backend/src')},stdio:['ignore','ignore','inherit']})
 let ready=false;for(let i=0;i<90;i++){try{if((await fetch(url+'/api/health')).ok){ready=true;break}}catch{}await new Promise(r=>setTimeout(r,100))}assert(ready)
 browser=await chromium.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/chromium'})
 const c=await browser.newContext({baseURL:url,viewport:{width:390,height:844}})
 const outside=[],errors=[],q=c.request;c.on('request',r=>{if(/^https?:/.test(r.url()) && new URL(r.url()).origin!==url)outside.push(r.url())})
 const pages=async()=>{const p=await c.newPage();p.setDefaultTimeout(18000);p.on('pageerror',e=>errors.push(e.message));return p}
 const p=await pages();await p.goto('/?studio=new')
 const l=(k,pg=p)=>pg.getByLabel(k,{exact:true}),b=(k,pg=p)=>pg.getByRole('button',{name:k,exact:true}),t=(k,pg=p)=>pg.getByText(k,{exact:true})
 const passage='木窗未合。\n🌧 雨落。巷口有车驶过。雨落。'
 await l('作品标题').fill('一扇木窗');await l('粘贴自己的原文').fill(passage);await p.locator('select[name=rights_status]').selectOption('owned')
 await b('新建项目，先编声景 →').click();await l('声景对应的原文段落').selectOption({index:2})
 const pid=new URL(p.url()).searchParams.get('studio');assert(pid && pid!=='new')
 const pre='/api/projects/'+pid,prefix=pre+'/reader',sc=prefix+'/soundscapes'
 const state=async()=>(await q.get(sc)).json(),content=async()=>(await q.get(prefix+'/content')).json()
 assert.equal((await content()).config.illustrations.length,0);assert(!(await content()).blocks[1].narration)
 assert(await l('持续细雨').isChecked());assert(!(await l('一辆车驶过').isChecked()));assert(await b('生成待审声景').isDisabled())
 const generate=b('生成待审声景'), exp=b('导出独立阅读器')
 await l('原文依据').fill('并无这句话');assert(await generate.isDisabled());assert(await exp.isDisabled())
 await l('原文依据').fill('雨落');assert(await generate.isDisabled());await p.getByLabel('相同引文的位置',{exact:false}).fill('2');assert(await generate.isEnabled())
 // UTF-16 emoji before the repeated quote checks the actual absolute UTF-8 offset.
 await l('声景原文').evaluate(el=>{el.focus();const i=el.value.lastIndexOf('雨落');el.setSelectionRange(i,i+2)})
 await b('使用框选的原文').click()
 await l('一辆车驶过').check();await l('车辆经过的时刻（秒）').fill('8')
 const send=()=>p.waitForResponse(r=>new URL(r.url()).pathname===sc && r.request().method()==='POST')
 const pauseReq=send();await generate.click();assert.equal((await pauseReq).status(),201)
 const candidate=l('试听待审声景'),adopt=b('已对照原文，采用此声景')
 await candidate.waitFor();let snap=await state(),first=snap.takes[0].id
 assert.equal(snap.takes.length,1);assert.equal(snap.takes[0].car_at,8);assert.equal(snap.takes[0].evidence_start,Buffer.byteLength(passage.slice(0,passage.lastIndexOf('雨落'))));assert(!(await content()).blocks[1].soundscape)
 assert(await adopt.isDisabled())
 // Seeking to the last samples must not attest to a whole audition.
 await candidate.evaluate(async a=>{if(a.readyState<1)await new Promise(r=>a.addEventListener('loadedmetadata',r,{once:true}));a.currentTime=a.duration-.15;await a.play()})
 await p.waitForFunction(()=>document.querySelector('audio[aria-label="试听待审声景"]').ended);assert(await adopt.isDisabled())
 await candidate.evaluate(async a=>{a.currentTime=0;await new Promise(r=>a.addEventListener('seeked',r,{once:true}));await a.play()})
 await adopt.click({timeout:20000});await l('已采用的段落声景').waitFor()
 const book=await content();assert.equal(book.blocks[1].soundscape.id,first);assert.equal(book.blocks[1].soundscape.description,'细雨中一辆车驶过')
 assert.deepEqual(Object.keys(book.blocks[1].soundscape).sort(),['id','label','description','duration'].sort())
 check('source-only Studio, genuine 12 s full audition, reject seek-to-end, explicit adopt; private repeated quote resolves to intended UTF-8 location')
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true)
 // Restore the approved sound-only project in another copy, without URL lane hints.
 const bundle=await q.get(pre+'/bundle');assert(bundle.ok())
 const copyRes=await q.post('/api/project-bundles',{multipart:{file:file('hand.zip',await bundle.body(),'application/zip')}});assert(copyRes.ok())
 const copy=(await copyRes.json()).id,restore=await pages();await restore.goto('/?studio='+copy)
 await l('已采用的段落声景',restore).waitFor();assert(await restore.locator('.passage-soundscape').evaluate(el=>el.open))
 assert.equal((await q.get('/api/projects/'+copy+'/reader/soundscapes').then(r=>r.json())).takes[0].evidence,'雨落')
 check('full editable handoff reopens sound-only Studio with its source evidence and adopted take, no dummy image or voice')
 await t('段落朗读（可选）').click();await p.getByLabel('朗读对应的原文段落').selectOption({index:2})
 await l('选择本机录音').setInputFiles(file('private.wav',tone(),'audio/wav'));await l('录音来源与使用许可').fill('制作方私有来源说明')
 assert(await l('原文依据').isDisabled())
 await b('存为待审录音').click();const spoken=l('试听待审段落朗读');await spoken.waitFor();await spoken.evaluate(a=>a.play());await b('已对照原文，采用此朗读').click()
 await l('已采用的段落朗读').waitFor()
 const voice=(await content()).blocks[1].narration.id;assert(voice && voice!==first)
 await l('已采用的段落声景').evaluate(a=>a.play());await l('已采用的段落朗读').evaluate(a=>a.play());assert(await l('已采用的段落声景').evaluate(a=>a.paused))
 await l('原文依据').fill('巷口有车驶过。');await l('一辆车驶过').check();await l('持续细雨').uncheck();await l('车辆经过的时刻（秒）').fill('10')
 // Another session commits a genuine reader revision while this form is open.
 let other=await(await q.get(prefix)).json();assert((await q.patch(prefix,{data:{...other.config,revision:other.revision,subtitle:'另一页的改动'}})).ok())
 const stale=send();await generate.click();assert.equal((await stale).status(),409);await p.getByRole('alert').filter({hasText:'当前输入保留'}).waitFor()
 assert.equal(await l('原文依据').inputValue(),'巷口有车驶过。');assert.equal((await content()).blocks[1].soundscape.id,first)
 const retry=send();await generate.click();assert.equal((await retry).status(),201);await candidate.waitFor()
 const next=(await state()).takes.find(s=>s.status==='pending').id;assert.equal((await content()).blocks[1].soundscape.id,first)
 await candidate.evaluate(a=>{a.playbackRate=2;return a.play()});await adopt.click({timeout:18000});await l('已采用的段落声景').waitFor()
 snap=await state();assert.equal(snap.takes.find(t=>t.id===first).status,'withdrawn');assert.equal(snap.takes.find(t=>t.id===next).rain,false)
 const mixed=await content();assert.equal(mixed.blocks[1].narration.id,voice);assert.equal(mixed.blocks[1].soundscape.id,next)
 await exp.click();const dl=p.getByRole('link',{name:'下载阅读器 ↓'});await dl.waitFor();const zip=await q.get(await dl.getAttribute('href'));assert(zip.ok())
 const seal=spawnSync(python,['-c',`import io,json,sys,zipfile
z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))
r=json.loads(z.read('reader.json'))
b=r['blocks'][1]
assert len([n for n in z.namelist() if n.startswith('media/') and n.endswith('.wav')])==2
assert sorted(b['soundscape'])==sorted(['id','label','description','duration'])
assert b['soundscape']['description']=='一辆车驶过'
assert '制作方私有来源说明' not in z.read('RIGHTS.txt').decode()
assert not any('evidence_start' in v or 'car_at' in v for v in [str(r)])
assert 'credit' not in r['media'][b['narration']['id']]
print(json.dumps([b['narration']['id'],b['soundscape']['id']]))`],{input:await zip.body(),encoding:'utf8'})
 assert.equal(seal.status,0,seal.stderr);assert.deepEqual(JSON.parse(seal.stdout),[voice,next])
 check('mixed paragraph: independent reviewed voice/ambience, solo author audition, stale conflict and retry, replacement, real ZIP with both current WAVs and only public fields')
 // Open the full workbench for the same project, and then verify a genuinely
 // ordinary project also has the tool, with no conversion into Studio.
 const reg=await q.post('/api/projects',{multipart:{rights_status:'owned',file:file('另一份.txt','夜雨。\n车驶过。\n铅笔在纸上划过。','text/plain')}});assert(reg.ok())
 const oid=(await reg.json()).id,ordinary=await pages();await ordinary.goto('/?project='+oid);await b('独立阅读器',ordinary).click()
 assert.equal(await ordinary.locator('.passage-soundscape').evaluate(el=>el.open),false)
 await t('段落声景（可选）',ordinary).click();await l('声景对应的原文段落',ordinary).selectOption({index:1});await l('原文依据',ordinary).fill('夜雨')
 assert(await b('导出独立阅读器',ordinary).isDisabled());ordinary.once('dialog',d=>d.dismiss());await b('原文与预览',ordinary).click();assert.equal(await l('原文依据',ordinary).inputValue(),'夜雨')
 const near='**/bundle/preflight';await ordinary.route(near,r=>r.fulfill({json:{can_export:true,uncompressed_bytes:159000000,limits:{uncompressed_bytes:160000000}}}))
 let dialogMsg='';ordinary.once('dialog',async d=>{dialogMsg=d.message();await d.dismiss()});await b('生成待审声景',ordinary).click()
 await t('已取消生成，当前设置仍保留。',ordinary).waitFor();assert(dialogMsg.includes('容量上限'));assert.equal((await q.get('/api/projects/'+oid+'/reader/soundscapes').then(r=>r.json())).takes.length,0)
 await ordinary.unroute(near);await b('生成待审声景',ordinary).click();await l('试听待审声景',ordinary).evaluate(a=>{a.playbackRate=3;return a.play()})
 await b('已对照原文，采用此声景',ordinary).click({timeout:18000});await l('已采用的段落声景',ordinary).waitFor()
 const oo=await(await q.get('/api/projects/'+oid+'/reader/soundscapes')).json();assert.equal(oo.takes[0].rain,true);assert.equal(oo.takes[0].car_at,null)
 assert(!(await(await q.get('/api/projects/'+oid)).json()).single_plate_studio)
 // The accepted player may mount before the final query refresh unlocks navigation.
 await ordinary.waitForFunction(()=>!document.querySelector('.reader-editor .visual-actions button.primary')?.disabled)
 await b('原文与预览',ordinary).click();await ordinary.locator('.reader-editor').waitFor({state:'detached'})
 const wavPath=path.join(temp,'projects',oid,'soundscape',oo.takes[0].id+'.wav');assert(fs.existsSync(wavPath),wavPath);fs.renameSync(wavPath,wavPath+'.held')
 await b('独立阅读器',ordinary).click();await b('定位段落声景，替换或撤下',ordinary).click();assert(await b('导出独立阅读器',ordinary).isDisabled())
 ordinary.once('dialog',d=>d.accept());await b('撤下当前声景',ordinary).click()
 await ordinary.waitForFunction(()=>!document.querySelector('.reader-editor .visual-actions button.primary')?.disabled)
 assert(!(await(await q.get('/api/projects/'+oid+'/reader/content')).json()).blocks[0].soundscape)
 // Wind is an alternative bed, never an automatic layer behind the rain.
 await l('原文依据',ordinary).fill('夜雨');await l('持续风声',ordinary).check();assert(!(await l('持续细雨',ordinary).isChecked()))
 await l('持续细雨',ordinary).check();assert(!(await l('持续风声',ordinary).isChecked()));await l('持续风声',ordinary).check()
 // Replace the intentionally missing synthetic file before checking a fresh full backup.
 fs.renameSync(wavPath+'.held',wavPath)
 await b('生成待审声景',ordinary).click();await l('试听待审声景',ordinary).evaluate(a=>{a.playbackRate=3;return a.play()})
 await b('已对照原文，采用此声景',ordinary).click({timeout:18000})
 const windData=await q.get('/api/projects/'+oid+'/reader/content').then(r=>r.json());assert.equal(windData.blocks[0].soundscape.description,'风声')
 const winds=await q.get('/api/projects/'+oid+'/reader/soundscapes').then(r=>r.json());const w=winds.takes.find(t=>t.status==='accepted');assert(w.wind && !w.rain && w.car_at===null)
 check('wind-only alternate bed: rain is cleared, explicit full audition, public wind description')

 // A different paragraph: pencil is an opt-in dry carrier, not another bed.
 await l('声景对应的原文段落',ordinary).selectOption({index:3})
 const pencil=l('纸上铅笔，停笔留白',ordinary),rain=l('持续细雨',ordinary),car=l('一辆车驶过',ordinary)
 assert(!(await pencil.isChecked()))
 await car.check();await pencil.check();assert(!(await car.isChecked()) && !(await rain.isChecked()))
 await car.check();assert(!(await pencil.isChecked()));await pencil.check();assert(!(await car.isChecked()))
 await l('原文依据',ordinary).fill('铅笔在纸上划过')
 await b('生成待审声景',ordinary).click()
 await l('试听待审声景',ordinary).waitFor();assert(await b('已对照原文，采用此声景',ordinary).isDisabled())
 const ps=await q.get('/api/projects/'+oid+'/reader/soundscapes').then(r=>r.json())
 assert(ps.takes.some(t=>t.status==='pending' && t.pencil===true && !t.rain && !t.wind && t.car_at===null))
 const pc=await q.get('/api/projects/'+oid+'/reader/content').then(r=>r.json())
 assert(!pc.blocks[2].soundscape);check('pencil: opt-in, exclusive recipe; review gate remains closed and no cue appears on a reader page')

 check('ordinary project: optional closed panel, discard guard, simulated near-capacity cancel preserves inputs, rain-only adopt, actual missing media recovery by explicit withdrawal')
 assert.deepEqual(outside,[]);assert.deepEqual(errors,[]);check('390 px viewport, no external traffic or JS errors')
}
main().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close();if(server){server.kill();await Promise.race([new Promise(r=>server.once('exit',r)),new Promise(r=>setTimeout(r,1800))])}fs.rmSync(temp,{recursive:true,force:true})})
