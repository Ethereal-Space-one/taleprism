// Run against a disposable loopback workbench. Synthetic tones exercise actual
// decode/playback, never a claim of speech recognition or human listening.
const assert=require('node:assert/strict')
const {execFileSync}=require('node:child_process')
const {mkdtempSync,readFileSync,rmSync}=require('node:fs')
const os=require('node:os'), path=require('node:path')
const {chromium}=require('playwright')
const base=new URL(process.argv[2]);assert.equal(base.hostname,'127.0.0.1')
const temp=mkdtempSync(path.join(os.tmpdir(),'tale-studio-voice-'))
function make(ext,hz,opts=[]){
  const dest=path.join(temp,'private-original-'+hz+'.'+ext)
  execFileSync('ffmpeg',['-hide_banner','-loglevel','error','-f','lavfi','-i',`sine=frequency=${hz}:sample_rate=44100:duration=1.4`,'-ac','2','-metadata','title=PRIVATE_TAG_NEVER_UPLOAD',...opts,dest])
  return {name:path.basename(dest),mimeType:ext==='wav'?'audio/wav':ext==='mp3'?'audio/mpeg':'audio/mp4',buffer:readFileSync(dest)}
}
;(async()=>{
  const browser=await chromium.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/chromium',headless:true})
  try {
    const context=await browser.newContext({baseURL:base.href,viewport:{width:390,height:844}})
    const page=await context.newPage();page.setDefaultTimeout(10000)
    const outside=[],errors=[],forms=[]
    page.on('request',r=>{
      if(/^https?:/.test(r.url())&&new URL(r.url()).origin!==base.origin) outside.push(r.url())
    })
    page.on('pageerror',e=>errors.push(e.message))
    // CDP omits streamed multipart bodies. Inspect the actual FormData passed
    // to fetch (do not substitute its response or alter the real request).
    await page.exposeFunction('recordFixtureForm', data => forms.push(data))
    await page.addInitScript(()=>{
      const nativeFetch=window.fetch
      window.fetch=async (...args)=>{
        const [url,options]=args
        if(String(url).endsWith('/reader/narrations') && options?.method==='POST' && options.body instanceof FormData) {
          const audio=options.body.get('file'), raw=new TextDecoder('latin1').decode(await audio.arrayBuffer())
          await window.recordFixtureForm({name:audio.name,tagged:raw.includes('PRIVATE_TAG_NEVER_UPLOAD'),named:raw.includes('private-original-')})
        }
        return nativeFetch.apply(window,args)
      }
    })
    const wav=make('wav',340),mp3=make('mp3',600),m4a=make('m4a',780,['-c:a','aac'])
    await page.goto('/?studio=new')
    await page.getByLabel('作品标题').fill('原创朗读试走')
    const source='第一段在开头。\n第二段只配自己的朗读。\n最后一段保持安静。'
    await page.getByLabel('粘贴自己的原文').fill(source)
    await page.getByLabel('原文权利状态').selectOption('owned')
    await page.getByRole('checkbox',{name:'朗读',exact:true}).check()
    await page.getByRole('button',{name:'新建项目，开始制作 →'}).click()
    const choose=page.getByLabel('朗读对应的原文段落')
    await choose.selectOption({index:2})
    const pid=new URL(page.url()).searchParams.get('studio')
    const api='/api/projects/'+pid+'/reader'
    async function state(){return (await context.request.get(api+'/narrations')).json()}
    async function content(){return (await context.request.get(api+'/content')).json()}
    const file=page.getByLabel('选择本机录音'),credit=page.getByLabel('录音来源与使用许可',{exact:true})
    const upload=page.getByRole('button',{name:'存为待审录音'})
    const adopt=page.getByRole('button',{name:'已对照原文，采用此朗读'})
    const candidate=page.getByLabel('试听待审段落朗读',{exact:true})
    assert.equal((await content()).config.illustrations.length,0)
    assert.equal(await page.locator('.passage-voice').getAttribute('open'),'')
    assert.equal(await page.locator('[aria-label="朗读原文"]').textContent(),'第二段只配自己的朗读。')
    await file.setInputFiles(wav); await credit.fill('第一条不公开说明')
    await page.getByRole('button',{name:'添加插图或返回底图制作 →'}).click()
    await page.getByRole('button',{name:'先配一段朗读，不加插图 →'}).click()
    assert.equal(await credit.inputValue(),'第一条不公开说明')
    assert.equal(await file.evaluate(el=>el.files[0].name),wav.name)
    await upload.click();await candidate.waitFor()
    assert.equal(await adopt.isEnabled(),false)
    await page.waitForFunction(()=>document.querySelector('audio[aria-label="试听待审段落朗读"]')?.readyState>=1)
    async function play(from) {
      await candidate.evaluate(async(el,from)=>{
        el.pause()
        if(Math.abs(el.currentTime-from)>.001) {
          await new Promise(ok=>{el.addEventListener('seeked',ok,{once:true});el.currentTime=from})
        }
        await el.play()
      },from)
      await page.waitForFunction(()=>document.querySelector('audio[aria-label="试听待审段落朗读"]')?.ended)
    }
    await play(1.23);assert.equal(await adopt.isEnabled(),false)
    assert(!((await content()).blocks[1].narration))
    await play(0);await adopt.click()
    await page.getByLabel('已采用的段落朗读',{exact:true}).waitFor()
    let book=await content()
    const first=book.blocks[1].narration.id
    assert.equal(book.media[first].credit,undefined)
    assert.equal(await page.getByRole('link',{name:'打开阅读预览 ↗'}).getAttribute('href'),'/read/'+pid+'?at='+book.blocks[1].byte_start)
    const bytes=await (await context.request.get(book.media[first].url)).body()
    assert.equal(bytes.toString('ascii',0,4),'RIFF');assert.equal(bytes.readUInt16LE(22),1);assert.equal(bytes.readUint32LE(24),24000)
    assert.equal(bytes.indexOf('PRIVATE_TAG_NEVER_UPLOAD'),-1)
    await file.setInputFiles({name:'broken.mp3',mimeType:'audio/mpeg',buffer:Buffer.from('not a sound')})
    await credit.fill('失败时保留');await upload.click();await page.getByRole('alert').waitFor()
    assert.equal(await credit.inputValue(),'失败时保留');assert.equal((await content()).blocks[1].narration.id,first)
    async function codec(fixture,label) {
      const start=(await state()).takes.length
      await file.setInputFiles(fixture);await credit.fill(label);await upload.click()
      await page.waitForFunction(()=>!document.querySelector('.passage-voice form fieldset')?.disabled)
      const next=await state()
      return next.takes.length===start+1
    }
    const mp3Ok=await codec(mp3,'MP3 候选'),m4aOk=await codec(m4a,'M4A 候选')
    if(!mp3Ok && !m4aOk){await file.setInputFiles(wav);await credit.fill('WAV 替代');await upload.click();await candidate.waitFor()}
    assert.equal((await content()).blocks[1].narration.id,first)
    // A write in a second tab makes this candidate submission stale; no new
    // file is silently committed at the later revision.
    await file.setInputFiles(wav);await credit.fill('公开署名示例')
    await page.getByRole('checkbox',{name:/公开上面整条来源/}).check()
    const prior=(await state()).takes.length
    const reader=await (await context.request.get(api)).json()
    assert((await context.request.patch(api,{data:{...reader.config,revision:reader.revision,subtitle:'另一标签页已保存'}})).ok())
    await upload.click();await page.getByRole('alert').filter({hasText:'配置已更新'}).waitFor()
    assert.equal((await state()).takes.length,prior);assert.equal(await credit.inputValue(),'公开署名示例')
    await upload.click();await page.getByText(/已存为待审录音/).waitFor()
    assert.equal((await content()).blocks[1].narration.id,first)
    await play(0);await adopt.click()
    await page.getByText(/新预览和下一份阅读包将使用这条录音/).waitFor()
    book=await content()
    const second=book.blocks[1].narration.id
    assert.notEqual(second,first);assert.equal(book.media[second].credit,'公开署名示例');assert(!(first in book.media))
    assert.equal((await state()).takes.find(t=>t.id===first).status,'withdrawn')
    await page.goto('/?studio='+pid)
    await page.getByLabel('已采用的段落朗读',{exact:true}).waitFor()
    assert.equal(await page.getByLabel('朗读对应的原文段落').inputValue(),String(book.blocks[1].byte_start))
    const archive=await context.request.get('/api/projects/'+pid+'/bundle');assert(archive.ok())
    const restored=await context.request.post('/api/project-bundles',{multipart:{file:{name:'editable.zip',mimeType:'application/zip',buffer:await archive.body()}}})
    assert(restored.ok());const rid=(await restored.json()).id
    await page.goto('/?studio='+rid)
    await page.getByLabel('已采用的段落朗读',{exact:true}).waitFor()
    await page.getByRole('button',{name:'撤下当前朗读'}).click({trial:true})
    page.once('dialog',d=>d.accept()); await page.getByRole('button',{name:'撤下当前朗读'}).click()
    await page.getByText(/无朗读，保留纯文字/).waitFor()
    assert(!((await (await context.request.get('/api/projects/'+rid+'/reader/content')).json()).blocks[1].narration))
    assert.equal((await content()).blocks[1].narration.id,second)
    // A voice-first project can add art later. Existing motion and audio do not
    // compete for the same revision; saves wait for the other form's draft.
    await page.getByRole('button',{name:'添加插图或返回底图制作 →'}).click()
    const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAACAAAAASCAIAAAC1qksFAAAAIUlEQVR4nGNM6algoCVgoqnpoxaMWjBqwagFoxaMWgAFABaYAYyXLNXXAAAAAElFTkSuQmCC','base64')
    await page.getByLabel('插图文件').setInputFiles({name:'fixture.png',mimeType:'image/png',buffer:png})
    await page.getByLabel('图片来源与许可').fill('自画的色块')
    await page.getByRole('button',{name:'上传为候选图'}).click()
    await page.getByRole('button',{name:'接受这张底图'}).click()
    await page.getByText(/✓ 底图已接受/).waitFor()
    await page.getByLabel('插图替代文字（可选）').fill('灰绿色的矩形')
    await page.getByLabel('放在此段之后').selectOption({index:2})
    await page.getByRole('button',{name:'放置静图，进入动效导演 →'}).click()
    await page.locator('.motion-director[open]').waitFor()
    await page.reload()
    const director=page.locator('.motion-director[open]')
    await director.waitFor()
    assert.equal(await page.locator('.passage-voice').getAttribute('open'),null)
    await director.getByRole('button',{name:'只用静图'}).click()
    await page.getByText('段落朗读（可选）',{exact:true}).click()
    await choose.selectOption({index:2})
    assert.equal(await file.isEnabled(),false)
    await page.getByRole('button',{name:'保存章节编排',exact:true}).click()
    await page.waitForFunction(()=>!document.querySelector('.passage-voice form fieldset')?.disabled)
    await file.setInputFiles(wav);await credit.fill('图文工程中的待审录音');await upload.click()
    await page.getByText(/已存为待审录音/).waitFor()
    const withArt=await (await context.request.get('/api/projects/'+rid+'/reader/content')).json()
    assert.equal(withArt.config.illustrations[0].description,'灰绿色的矩形')
    assert.equal(withArt.config.illustrations[0].motion,null)
    assert.equal(withArt.blocks[1].narration,undefined)
    assert.equal(await page.getByRole('button',{name:'重新载入此项目'}).count(),0)
    assert(forms.length>=3); for(const form of forms) assert.deepEqual(form,{name:'paragraph.wav',tagged:false,named:false})
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false)
    assert.deepEqual(errors,[]);assert.deepEqual(outside,[])
    console.log(JSON.stringify({passed:true,sourceOnly:true,wav:true,mp3:mp3Ok,m4a:m4aOk,staleProtected:true,seekShortcutBlocked:true,explicitAdoption:true,replacement:true,oldFileTagsStripped:true,reopened:true,restored:true,withdrawal:true,laterAddedArtAlt:true,dirtyMotionProtected:true,mobileViewport390:true,thirdPartyRequests:0}))
  } finally {await browser.close();rmSync(temp,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1})
