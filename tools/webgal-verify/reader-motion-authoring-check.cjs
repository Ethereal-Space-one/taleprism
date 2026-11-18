// Real pure modules, independent from the renderer/lifecycle test. No browser or network.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const root = path.resolve(__dirname, '../..')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'tale-motion-author-'))
try {
  const compile = spawnSync(path.join(root, 'frontend/node_modules/.bin/tsc'), ['--module', 'commonjs', '--target', 'ES2022', '--strict', '--skipLibCheck', '--outDir', temp,
    path.join(root, 'frontend/src/reader/motion/authoring.ts'), path.join(root, 'frontend/src/reader/motion/runtime.ts')], { encoding: 'utf8' })
  assert.equal(compile.status, 0, compile.stdout + compile.stderr)
  const { validIllustrationMotion, validMotionRecipe, resolveEnvironmentMotion, resolveReadingMotion, simplePolygon, directionRecipe, environmentMotionRecipes } = require(path.join(temp, 'reader/motion/recipes.js'))
  const { newDirection, bankHits, directionProblem } = require(path.join(temp, 'reader/motion/authoring.js'))
  const sha = 'a'.repeat(64), source = 'b'.repeat(64), square = [[.1,.1],[.4,.1],[.4,.4],[.1,.4]]
  const asset = { id: 'own-image', sha256: sha, width: 1000, height: 700, kind: 'scene', status: 'accepted' }
  const plate = { id: 'own-plate', image_asset_id: asset.id, after_byte: 96, title: 'Title does not select an effect', description: '' }
  const paragraphs = [{ byte_start:0, byte_end:96, text:'雨点落在门外的潮湿地面。', preview:'雨点落在门外' }]
  const initial = newDirection('rain-wet-ground', asset, source, plate.after_byte)
  assert.equal(initial.reviewed, false); assert.equal(initial.rings, 0); assert.deepEqual(initial.ground, [])
  assert.ok(directionProblem(initial, plate, asset, source, paragraphs))
  const rain = { ...initial, areas:[square], evidence:paragraphs[0].text, note:'门外湿地接雨，人脸和道具在范围外。', reviewed:true }
  assert.equal(validIllustrationMotion(rain), true)
  assert.equal(directionProblem(rain, plate, asset, source, paragraphs), null)
  assert.equal(validIllustrationMotion({ ...rain, rings:1 }), false, 'no inferred sky/ground ripple')
  assert.equal(validIllustrationMotion({ ...rain, rings:1, ground:[square] }), true)
  const bank = [[.6,.5],[.8,.4],[.9,.6]], shore = { ...newDirection('wave-impact-backwash', asset, source, plate.after_byte), water:[square], bank, hits:bankHits(bank, 3), evidence:paragraphs[0].text, note:rain.note, reviewed:true }
  assert.ok(validIllustrationMotion(shore))
  assert.match(directionProblem(shore,plate,asset,source,paragraphs), /岸线撞点/)
  assert.equal(directionProblem({...shore,water:[[[.5,.2],[.95,.2],[.95,.8],[.5,.8]]]},plate,asset,source,paragraphs), null)
  assert.match(directionProblem({...rain,rings:1,ground:[[[.7,.7],[.9,.7],[.9,.9],[.7,.9]]]},plate,asset,source,paragraphs), /重叠/)
  for (const count of [-100, 0, 1, 3, 6, 1000, Infinity, NaN]) {
    const hits = bankHits(bank, count)
    assert.ok(hits.length >=1 && hits.length <=6)
    assert.ok(hits.every((h) => Number.isFinite(h.x) && h.x>=.6 && h.x<=.9))
  }
  for (const mutation of [
    (m)=>{m.version=2},(m)=>{m.reviewed=1},(m)=>{m.after_byte=96.5},(m)=>{m.image_sha256='bad'},
    (m)=>{m.width=1000.1},(m)=>{m.width=8193},(m)=>{m.height=NaN},(m)=>{m.areas=null},(m)=>{m.areas=[[[0,0],[1,1],[1,0],[0,1]]]},
    (m)=>{m.areas=[[[0,0],[.5,0],[1,0]]]},(m)=>{m.drops=129},(m)=>{m.rings=-1},(m)=>{m.note='😀😀😀😀'},
    (m)=>{m.evidence='a\u001c\u001d\u001e\u001f\u0085\ufeff b'},(m)=>{m.extra_url='https://not-allowed.invalid'},
    (m)=>{delete m.ground},(m)=>{m.ground=Array(9).fill(square)},(m)=>{m.ground=[[[0,0],[.5,0],[0,0]]]},
  ]) { const m=structuredClone(rain);mutation(m);assert.equal(validIllustrationMotion(m),false,JSON.stringify(m)) }
  assert.equal(validIllustrationMotion({...rain,note:'😀'.repeat(8)}),true,'Unicode scalar min length')
  assert.equal(validIllustrationMotion({...rain,note:'😀'.repeat(301)}),false,'Unicode scalar maximum')
  assert.equal(validIllustrationMotion({...shore,hits:[{...shore.hits[0],script:'ignored?'}]}),false,'nested unknown keys fail closed')
  for (const p of [[], [[0,0],[1,0],[0,0]], [[0,0],[1,0],[.5,0],[1,1]], [[0,0],[1,1],[0,1],[1,0]]]) assert.equal(simplePolygon(p),false)
  assert.ok(simplePolygon(square)); assert.ok(simplePolygon([...square].reverse()))
  const data={project:{canonical_sha256:source},config:{illustrations:[{...plate,motion:rain}]},media:{[asset.id]:{...asset,type:'image'}}}
  const before=JSON.stringify(data), resolved=resolveEnvironmentMotion(data,data.config.illustrations[0])
  assert.deepEqual(resolved,directionRecipe(rain,plate.id))
  assert.equal(JSON.stringify(data),before,'resolution never writes config, source or personal state')
  // Automatic presentation is stricter than manual inspection. Live preview can
  // expose an editorially pending image even when the geometry is reviewed.
  const inline={...data, blocks:paragraphs, preview:false}
  const inlinePlate=inline.config.illustrations[0]
  assert.deepEqual(resolveReadingMotion(inline,inlinePlate),resolved)
  for (const mutate of [
    d=>{d.media[asset.id].status='pending'},d=>{d.media[asset.id].status='rejected'},
    d=>{delete d.media[asset.id].status;d.preview=true},d=>{d.blocks=[]},
    d=>{d.blocks.push({...d.blocks[0]})},d=>{d.blocks[0].text='只有在后文才有这句原文依据。'},
    d=>{d.config.illustrations[0].motion.reviewed=false},d=>{d.config.illustrations[0].motion=null},
    d=>{d.config.illustrations[0].motion.after_byte++},d=>{d.media[asset.id].width++},
  ]) {const d=structuredClone(inline);mutate(d);assert.equal(resolveReadingMotion(d,d.config.illustrations[0]),null)}
  const projection=structuredClone(inline), m=projection.config.illustrations[0].motion
  delete m.evidence;delete m.note;delete projection.media[asset.id].status;m.playback_only=true
  assert.deepEqual(resolveReadingMotion(projection,projection.config.illustrations[0]),resolved,
    'reviewed exported geometry for an accepted, source-bound plate plays without private notes')
  for (const full of [rain, shore]) {
    const {note, evidence, ...bounds} = full
    const motion = {...bounds, playback_only:true}
    const get = (m) => {
      const p = {...plate, motion:m}
      return resolveEnvironmentMotion({...data,config:{illustrations:[p]}},p)
    }
    assert.deepEqual(get(motion), directionRecipe(full,plate.id),'geometry-only publication plays')
    assert.equal(validIllustrationMotion(motion),false,'reader projection cannot pass author review')
    for (const bad of [{...motion, note}, {...motion,evidence}, {...motion,reviewed:false},
      {...motion,source_sha256:'c'.repeat(64)}, {...bounds}, {...motion,playback_only:false}]) {
      assert.equal(get(bad),null,'incomplete/moved publication must not animate')
    }
  }
  for (const mutate of [
    d=>{d.config.illustrations[0].motion=null},d=>{d.config.illustrations[0].motion.reviewed=false},
    d=>{d.config.illustrations[0].after_byte++},d=>{d.config.illustrations[0].after_byte--},
    d=>{d.project.canonical_sha256='c'.repeat(64)},d=>{d.media[asset.id].sha256='c'.repeat(64)},
    d=>{d.media[asset.id].width++},d=>{delete d.media[asset.id].height},d=>{d.config.illustrations.push({...d.config.illustrations[0]})},
  ]) {const d=JSON.parse(before);mutate(d);assert.equal(resolveEnvironmentMotion(d,d.config.illustrations[0]),null)}
  // Explicit static and unfinished custom direction override exact built-in motion, too.
  for (const r of environmentMotionRecipes) {
    const assetId=r.imageAsset || 'upload'
    const p={id:r.plateId,image_asset_id:assetId,after_byte:r.afterByte}
    const d={project:{canonical_sha256:r.canonicalHash},config:{illustrations:[p]},preview:false,
      blocks:[{byte_end:r.afterByte}],media:{[assetId]:{id:assetId,type:'image',width:r.width,height:r.height,sha256:r.imageHash}}}
    assert.equal(resolveReadingMotion(d,p),r,'exact bound legacy rain and wave are eligible')
    p.after_byte++;d.blocks[0].byte_end++
    assert.equal(resolveReadingMotion(d,p),null,'moving a legacy plate invalidates automatic timing')
  }
  const fixed=environmentMotionRecipes[1], id='rebuilt-id'
  const demo={project:{canonical_sha256:fixed.canonicalHash},config:{illustrations:[{id:fixed.plateId,image_asset_id:id,after_byte:96,motion:null}]},media:{[id]:{id,type:'image',sha256:fixed.imageHash,width:fixed.width,height:fixed.height}}}
  assert.equal(resolveEnvironmentMotion(demo,demo.config.illustrations[0]),null)
  delete demo.config.illustrations[0].motion
  assert.equal(resolveEnvironmentMotion(demo,demo.config.illustrations[0]),fixed,'omitted legacy config unchanged')
  // Malformed nested JSON must return false, never throw into the reader.
  const hostile=[null,undefined,false,true,0,NaN,'rain',[],{},[{}],{effect:'rain-wet-ground',areas:null},
    {...rain,areas:[null]}, {...rain,areas:[[null,null,null]]},{...shore,bank:null},{...shore,hits:[null]},
    {...shore,hits:[[]]},{...rain,ground:[{}]}]
  for (const value of hostile) {assert.doesNotThrow(()=>validIllustrationMotion(value)); assert.equal(validIllustrationMotion(value),false); assert.doesNotThrow(()=>validMotionRecipe(value))}
  // Real runtime, fake platform clock: only active drawn time unlocks creator review.
  const names=['window','document','ResizeObserver','IntersectionObserver','requestAnimationFrame','cancelAnimationFrame']
  const saved=Object.fromEntries(names.map((n)=>[n,global[n]]))
  try {
    const events=(extra={})=>{const listeners=new Map();return {...extra, addEventListener(n,fn){if(!listeners.has(n))listeners.set(n,new Set());listeners.get(n).add(fn)},removeEventListener(n,fn){listeners.get(n)?.delete(fn)},emit(n){for(const fn of listeners.get(n)||[])fn()}}}
    const media=events({matches:false}), doc=events({hidden:false}), pending=new Map();let rid=0, observer, frames=0, cycles=0
    global.window=events({matchMedia:()=>media,devicePixelRatio:1});global.document=doc
    global.requestAnimationFrame=(fn)=>{pending.set(++rid,fn);return rid};global.cancelAnimationFrame=(id)=>pending.delete(id)
    global.ResizeObserver=class {observe(){} disconnect(){}}
    global.IntersectionObserver=class {constructor(fn){observer=fn} observe(){} disconnect(){}}
    const ctx=new Proxy({}, {get(_t,n){return n==='createRadialGradient'?()=>({addColorStop(){}}):()=>{}},set(){return true}})
    const image=events({complete:true,naturalWidth:1000,naturalHeight:700,isConnected:true,getBoundingClientRect:()=>({left:0,top:0,width:1000,height:700})})
    const viewport={isConnected:true,scrollLeft:0,scrollTop:0,clientLeft:0,clientTop:0,getBoundingClientRect:()=>({left:0,top:0,width:1000,height:700})}
    const canvas={hidden:true,style:{},width:0,height:0,getContext:()=>ctx}
    const {startEnvironmentMotion}=require(path.join(temp,'reader/motion/runtime.js'))
    const elapsed=[]
    const stop=startEnvironmentMotion(image,canvas,viewport,directionRecipe(rain,plate.id),()=>frames++,()=>cycles++,(n)=>elapsed.push(n))
    observer([{target:viewport,isIntersecting:true,intersectionRatio:.08}])
    assert.equal(pending.size,0,"seeing a sliver cannot count as creator review")
    observer([{target:viewport,isIntersecting:true,intersectionRatio:1}])
    const tick=(t)=>{const jobs=[...pending.values()];pending.clear();jobs.forEach((fn)=>fn(t))}
    for(let i=0;i<=100;i++)tick(i*50)
    assert.equal(frames,1);assert.equal(cycles,0,'first frame and five active seconds cannot approve a cycle')
    doc.hidden=true;doc.emit('visibilitychange');tick(999999)
    assert.equal(cycles,0,'hidden wall clock never unlocks review')
    doc.hidden=false;doc.emit('visibilitychange')
    for(let i=0;i<=65;i++)tick(1000000+i*50)
    assert.equal(cycles,1,'eight active seconds enable one cycle attestation')
    assert.deepEqual(elapsed,[0,1,2,3,4,5,6,7,8],'progress reports rendered seconds, not hidden wall time')
    for(let i=0;i<200;i++)tick(1100000+i*50)
    assert.equal(cycles,1,'notification is one-shot, not a per-frame React update')
    stop();assert.equal(pending.size,0);assert.equal(canvas.hidden,true)
  } finally {for(const n of names)if(saved[n]===undefined)delete global[n];else global[n]=saved[n]}
  console.log('Motion authoring: bounded Unicode/schema/geometry, explicit wet ground, arbitrary-image/source/position bindings, reviewed drafts/static override, mutation-free resolution, malformed JSON and real eight-active-second review gate passed.')
} finally {fs.rmSync(temp,{recursive:true,force:true})}
