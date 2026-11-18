// Regression for ordinary editable projects (not the studio entry). Self-hosts
// a disposable loopback backend; never accepts a path to another project's data.
// Requires built frontend, backend venv, Playwright Chromium (CHROME_PATH).
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os')
const path = require('node:path'), net=require('node:net'), {spawn,spawnSync}=require('node:child_process')
const {chromium}=require('playwright')
const root=path.resolve(__dirname,'../..'), python=process.env.BACKEND_PYTHON || path.join(root,'backend/.venv/bin/python')
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'tale-ordinary-author-'))
const serverRoot=path.join(temp,'isolated-data')
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAACAAAAASCAIAAAC1qksFAAAAIUlEQVR4nGNM6algoCVgoqnpoxaMWjBqwagFoxaMWgAFABaYAYyXLNXXAAAAAElFTkSuQmCC','base64')
const file=(name,buffer,mimeType='text/plain')=>({name,buffer:Buffer.from(buffer),mimeType})
const take=seconds=>{const count=Math.round(seconds*24000),b=Buffer.alloc(44+count*2);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(24000,24);b.writeUInt32LE(48000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(count*2,40);for(let i=0;i<count;i++)b.writeInt16LE(Math.round(Math.sin(i*.06)*800),44+i*2); return b}
const check=(id)=>console.log('PASS '+id)
let browser,server
async function run(){
 const reservation=net.createServer()
 await new Promise(ok=>reservation.listen(0,'127.0.0.1',ok))
 const port=reservation.address().port;await new Promise(ok=>reservation.close(ok))
 const baseURL='http://127.0.0.1:'+port
 server=spawn(python,['-m','uvicorn','storygal.app:app','--host','127.0.0.1','--port',String(port),'--log-level','warning'],{cwd:root,env:{...process.env,STORYGAL_DATA_DIR:serverRoot,PYTHONPATH:path.join(root,'backend/src'),PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','ignore','inherit']})
 let ready=false
 for(let i=0;i<100;i++){try{if((await fetch(baseURL+'/api/health')).ok){ready=true;break}}catch{} await new Promise(ok=>setTimeout(ok,100))}
 assert(ready,'loopback backend not ready')
 browser=await chromium.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/chromium',headless:true})
 const c=await browser.newContext({baseURL,viewport:{width:1280,height:900}})
 const q=c.request,p=await c.newPage();p.setDefaultTimeout(12000)
 const errors=[],outside=[]
 p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(/^https?:/.test(r.url())&&new URL(r.url()).origin!==baseURL)outside.push(r.url())})
 await p.goto('/')
 const open=p.getByRole('button',{name:'导入新文本',exact:true}),dlg=p.locator('dialog[open]'),txt=dlg.locator('input[name=file]'),rights=dlg.locator('select[name=rights_status]'),submit=dlg.getByRole('button',{name:/导入并预览/})
 await open.click();await txt.setInputFiles(file('A.txt','一段测试。'));await rights.selectOption('public_domain');await submit.click()
 await p.getByRole('heading',{name:'A',exact:true}).waitFor()
 await open.click();assert.equal(await rights.inputValue(),'');assert.equal(await txt.evaluate(el=>el.files.length),0)
 await txt.setInputFiles(file('different.txt','另一份文件。'));await rights.selectOption('authorized')
 const source='这是作者自己的第一段。\r\n这份朗读来自同一项目中的第二段。'
 await txt.setInputFiles(file('B.txt',source));assert.equal(await rights.inputValue(),'');assert(!(await rights.evaluate(e=>e.checkValidity())))
 await rights.selectOption('owned');await submit.click();await p.getByRole('heading',{name:'B',exact:true}).waitFor()
 const pid=await p.evaluate(()=>localStorage.getItem('storygal-project')),prefix='/api/projects/'+pid,reader=prefix+'/reader'
 assert.equal((await(await q.get(prefix)).json()).rights_status,'owned')
 check('fresh TXT form and explicit rights on every file change')
 const readerTab=p.getByRole('button',{name:'独立阅读器',exact:true})
 const state=async()=>(await q.get(reader)).json()
 const blob=async()=>{const link=p.getByRole('link',{name:'下载阅读器 ↓'});const r=await q.get(await link.getAttribute('href'));assert(r.ok());return await r.body()}
 async function exportBook(){
  const link=p.getByRole('link',{name:'下载阅读器 ↓'}),last=await link.count()?await link.getAttribute('href'):null
  await exportBtn.click()
  await p.waitForFunction(prior=>{const a=[...document.querySelectorAll('.export-result a')].find(l=>l.textContent.includes('下载阅读器'));return a && a.getAttribute('href')!==prior},last)
  const r=spawnSync(python,['-c',"import io,json,sys,zipfile; z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())); print(json.dumps({'reader':json.loads(z.read('reader.json')),'files':z.namelist(),'rights':z.read('RIGHTS.txt').decode(),'source':z.read('storygal-source/original.txt').decode()}))"],{input:await blob(),encoding:'utf8'})
  assert.equal(r.status,0,r.stderr);return JSON.parse(r.stdout)
 }
 await readerTab.click(); await p.getByText('上传自己的封面或背景',{exact:true}).click()
 await p.getByLabel('图片文件',{exact:true}).setInputFiles(file('art.png',png,'image/png'));await p.getByLabel('来源与许可',{exact:true}).fill('自绘测试')
 await p.getByRole('button',{name:'上传为候选图',exact:true}).click();await p.getByRole('button',{name:'接受此图',exact:true}).waitFor()
 await p.getByText('编辑封面、场景与人物',{exact:true}).click()
 const title=p.getByLabel('章节名称',{exact:true}),saveTitle=p.getByRole('button',{name:'保存阅读器配置',exact:true}),exportBtn=p.getByRole('button',{name:'导出独立阅读器',exact:true})
 await title.fill('已编辑的章节名');assert(await exportBtn.isDisabled())
 await p.getByRole('button',{name:'接受此图',exact:true}).click();await p.getByText(/上传背景 · 已接受/).waitFor()
 assert.equal(await title.inputValue(),'已编辑的章节名')
 await saveTitle.click();await p.waitForFunction(()=>!document.querySelector('.reader-editor .visual-actions button.primary')?.disabled)
 assert.equal((await state()).config.title,'已编辑的章节名');check('chapter draft survives independent asset acceptance, export disabled until saved')
 // A racing external edit to the same header is different from an asset review.
 await title.fill('不要丢弃这个本地标题')
 let remote=await state();assert((await q.patch(reader,{data:{...remote.config,revision:remote.revision,title:'另一页保存的标题'}})).ok())
 await saveTitle.click();await p.getByText(/章节设置已在别处更改/).waitFor()
 assert.equal(await title.inputValue(),'不要丢弃这个本地标题');assert.equal((await state()).config.title,'另一页保存的标题')
 const discard=p.getByRole('button',{name:'放弃未保存的章节设置'});p.once('dialog',d=>d.dismiss());await discard.click()
 assert.equal(await title.inputValue(),'不要丢弃这个本地标题');p.once('dialog',d=>d.accept());await discard.click()
 assert.equal(await title.inputValue(),'另一页保存的标题');check('stale header rejected, local draft preserved, explicit reload only')
 await p.getByRole('button',{name:'在当前段落后加插图'}).click();const plateTitle=p.getByLabel('插图名称',{exact:true})
 await plateTitle.fill('要交付的插图');await p.getByLabel('默认阅读排布').selectOption('illustrated')
 assert(await exportBtn.isDisabled())
 p.once('dialog',d=>d.dismiss());await p.getByRole('button',{name:'原文与预览',exact:true}).click();assert.equal(await plateTitle.inputValue(),'要交付的插图')
 p.once('dialog',d=>d.dismiss());await p.getByRole('button',{name:'载入最新配置',exact:true}).click();assert.equal(await plateTitle.inputValue(),'要交付的插图')
 await p.getByRole('button',{name:'保存章节编排',exact:true}).click();await p.waitForFunction(()=>!document.querySelector('.reader-editor .visual-actions button.primary')?.disabled)
 const b1=await exportBook();assert.equal(b1.reader.config.reading_layout,'illustrated');assert.equal(b1.reader.config.illustrations[0].title,'要交付的插图');assert(b1.files.some(s=>s.startsWith('media/')));assert(b1.rights.includes('owned'));assert.equal(b1.source,source)
 check('dirty plate blocks ZIP and accidental navigation; real saved illustrated ZIP matches artwork/layout/rights/source')
 await p.getByText('段落朗读（可选）',{exact:true}).click();await p.getByLabel('朗读对应的原文段落').selectOption({index:2})
 const voiceFile=p.getByLabel('选择本机录音'),voiceCredit=p.getByLabel('录音来源与使用许可',{exact:true}),uploadVoice=p.getByRole('button',{name:'存为待审录音'})
 await voiceFile.setInputFiles(file('take.wav',take(.8),'audio/wav'));await voiceCredit.fill('PRIVATE EDITOR ONLY')
 await uploadVoice.click();const audio=p.getByLabel('试听待审段落朗读',{exact:true});await audio.waitFor()
 await audio.evaluate(el=>el.play());const adopt=p.getByRole('button',{name:'已对照原文，采用此朗读',exact:true})
 await adopt.click();await p.getByLabel('已采用的段落朗读',{exact:true}).waitFor()
 const b2=await exportBook(), aid=b2.reader.blocks[1].narration.id
 assert.equal(b2.reader.media[aid].credit,undefined);assert(b2.files.some(s=>s.startsWith('media/')&&s.endsWith('.wav')));assert(!b2.rights.includes('PRIVATE EDITOR ONLY'))
 // Place a second, healthy voice on another source anchor. The repair control
 // must not withdraw this one when a different accepted recording disappears.
 const anchorSelect=p.getByLabel('朗读对应的原文段落')
 await anchorSelect.selectOption({index:1});await voiceFile.setInputFiles(file('healthy.wav',take(.4),'audio/wav'));await voiceCredit.fill('原文首段的健康朗读')
 await uploadVoice.click();await audio.waitFor();await audio.evaluate(el=>el.play());await adopt.click();await p.getByLabel('已采用的段落朗读',{exact:true}).waitFor()
 const healthy=(await(await q.get(reader+'/content')).json()).blocks[0].narration.id
 const restoreZip=await q.get(prefix+'/bundle');assert(restoreZip.ok())
 await p.getByText('手动导入与原文练习',{exact:true}).click()
 await p.getByLabel('导入可编辑工程',{exact:true}).setInputFiles(file('ordinary.zip',await restoreZip.body(),'application/zip'))
 await p.getByText('已恢复“B.txt”。',{exact:true}).waitFor()
 const copy=await p.evaluate(()=>localStorage.getItem('storygal-project'));assert.notEqual(pid,copy)
 assert(!(await(await q.get('/api/projects/'+copy)).json()).single_plate_studio)
 // Only the generated tmp project's WAV is displaced to exercise real recovery.
 const wavPath=path.join(serverRoot,'projects',copy,'narration',aid+'.wav');assert(fs.existsSync(wavPath));fs.renameSync(wavPath,wavPath+'.held')
 await readerTab.click();await p.getByText('段落朗读（可选）',{exact:true}).click()
 await anchorSelect.selectOption({index:1});await p.getByLabel('已采用的段落朗读',{exact:true}).waitFor()
 assert.equal(await anchorSelect.inputValue(),'0')
 await p.getByRole('button',{name:'定位段落朗读，替换或撤下'}).click();assert(await exportBtn.isDisabled())
 await p.waitForFunction(()=>{const active=document.querySelector('.passage-voice select option:checked');return active?.textContent.includes('第 2 段') && active.textContent.includes('需修复')}).catch(async e=>{throw Error(e.message+'; voice options = '+await anchorSelect.evaluate(el=>[el.value,...Array.from(el.options,o=>o.textContent)].join('|')))})
 const withdraw=p.getByRole('button',{name:'撤下当前朗读'});p.once('dialog',d=>d.accept());await withdraw.click()
 await p.getByText(/无朗读，保留纯文字/).waitFor()
 const b3=await exportBook();assert(!b3.reader.blocks[1].narration);assert.equal(b3.reader.blocks[0].narration.id,healthy);assert.equal(b3.files.filter(s=>s.startsWith('media/')&&s.endsWith('.wav')).length,1)
 fs.renameSync(wavPath+'.held',wavPath);check('ordinary project records, exports and restores without conversion, then locates/repairs the affected voice without changing the healthy one and re-exports')
 await p.getByText('备份可编辑工程',{exact:true}).click()
 await p.getByText(/给自己或下一位制作者，不是给读者的成品/).waitFor()
 await p.getByText(/完整工程 ZIP 按解压后大小计算，上限 160 MB/).waitFor()
 if(process.argv.includes('--capacity')){
   const ep='/api/projects/'+copy+'/reader/narrations',long=take(120)
   let s=await(await q.get(ep)).json()
   for(let i=0;i<27;i++){
     long.writeInt16LE(i,44)
     const r=await q.post(ep,{multipart:{revision:String(s.revision),byte_start:'0',credit:'合成容量测试，不是人声',file:file('fixture.wav',long,'audio/wav')}})
     assert(r.ok());const next=await r.json(),known=new Set(s.takes.map(t=>t.id));const added=next.takes.find(t=>!known.has(t.id))
     s=await(await q.patch(ep+'/'+added.id,{data:{revision:next.revision,status:'withdrawn'}})).json()
   }
   const pre=await(await q.get('/api/projects/'+copy+'/bundle/preflight')).json()
   assert(pre.can_export);assert(pre.limits.uncompressed_bytes-pre.uncompressed_bytes<long.length)
   await p.reload();await readerTab.click();await p.getByText('段落朗读（可选）',{exact:true}).click()
   await p.getByLabel('朗读对应的原文段落').selectOption({index:2});await voiceFile.setInputFiles(file('last.wav',long,'audio/wav'));await voiceCredit.fill('保留输入')
   const ask=p.waitForEvent('dialog').then(async d=>{const msg=d.message();await d.dismiss();return msg})
   await uploadVoice.click();assert((await ask).includes('当前余量'));await p.getByText(/已取消保存，录音输入仍保留/).waitFor();assert.equal(await voiceCredit.inputValue(),'保留输入')
   assert.equal((await(await q.get(ep)).json()).takes.length,s.takes.length);assert((await(await q.get('/api/projects/'+copy+'/bundle/preflight')).json()).can_export)
   check('actual 27 × 120s retained takes: before-overflow warning on 28th, cancel keeps file/credit, history and portable capacity')
 }
 // A genuine pre-coverage manifest is admissible, but cannot attest that
 // the old author had no notes. Only the additive inventory marker is absent.
 const oldZip=spawnSync(python,['-c',`import io,json,sys,zipfile
src=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))
out=io.BytesIO()
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dest:
 for name in src.namelist():
  body=src.read(name)
  if name=='manifest.json':
   manifest=json.loads(body)
   assert manifest.pop('editorial_count')==0
   body=json.dumps(manifest,ensure_ascii=False).encode()
  dest.writestr(name,body)
sys.stdout.buffer.write(out.getvalue())`],{input:await restoreZip.body(),maxBuffer:4e6})
 assert.equal(oldZip.status,0,oldZip.stderr?.toString())
 const fresh=await c.newPage()
 fresh.on('pageerror',e=>errors.push(e.message));fresh.on('request',r=>{if(/^https?:/.test(r.url())&&new URL(r.url()).origin!==baseURL)outside.push(r.url())})
 await fresh.goto('/');await fresh.getByText('手动导入与原文练习',{exact:true}).click()
 await fresh.getByLabel('导入可编辑工程',{exact:true}).setInputFiles(file('before-coverage.zip',oldZip.stdout,'application/zip'))
 await fresh.getByText('恢复说明（不是错误）',{exact:true}).waitFor()
 await fresh.getByText(/此旧工程包未记录制作意见清单/).waitFor()
 assert.equal(await fresh.getByText(/工程仍有待修复内容/).count(),0)
 check('legacy inventory restored in fresh ordinary workbench, distinctly displays coverage notice and no false repair issue')
 assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);check('no page errors or external network traffic')
}
run().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close();if(server){server.kill();await Promise.race([new Promise(ok=>server.once('exit',ok)),new Promise(ok=>setTimeout(ok,2000))])}fs.rmSync(temp,{recursive:true,force:true})})
