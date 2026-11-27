const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const cp = require('node:child_process')
const root = path.resolve(__dirname, '../..')
const tmp = fs.mkdtempSync(path.join(os.tmpdir(),'tale-passage-proof-'))
try {
  cp.execFileSync(path.join(root,'frontend/node_modules/.bin/tsc'), ['--module','commonjs','--target','ES2022','--strict','--skipLibCheck','--outDir',tmp,path.join(root,'frontend/src/studio/passageProofModel.ts')])
  const {proofAt,inspectPhrase,publicAudio}=require(path.join(tmp,'studio/passageProofModel.js'))
  const blocks = ['🌧', '站台。','旧身份。'].map((text,i,all) => {
    const byte_start=Buffer.byteLength(all.slice(0,i).join('\r\n')) + (i ? 2 : 0)
    return {id:'b'+i,byte_start,byte_end:byte_start+Buffer.byteLength(text),text,audio:[]}
  })
  blocks[1].soundscape={id:'a',description:'钟声',label:'声景'}
  blocks[1].narration={id:'n',label:'旁白'}
  blocks[1].audio=[{take_id:'v',speaker_id:'s'}]
  const data={blocks,project:{canonical_sha256:'not-a-frozen-sample'},config:{title:'渡口',subtitle:'',illustrations:[{id:'plate',image_asset_id:'p',after_byte:blocks[1].byte_end,title:'旧身份',description:'字条写着旧身份'}]},media:{a:{type:'audio',credit:'作者'},v:{type:'audio'}},characters:{s:{name:'船长'}}}
  assert.equal(proofAt(data,4,'before'),null)
  const start=proofAt(data,0,'before')
  assert.equal(start.last,undefined)
  assert.deepEqual(start.gallery,[])
  assert.deepEqual(inspectPhrase(data,start,'渡口'),['封面文字'])
  const before=proofAt(data,1,'before')
  assert.equal(before.last.text,'🌧')
  assert.deepEqual(inspectPhrase(data,before,'旧身份'),[])
  const after=proofAt(data,1,'after')
  assert.deepEqual(inspectPhrase(data,after,'旧身份'),['已解锁画卷标题','插图说明或替代文字'])
  for(const key of ['旁白','船长','钟声','作者']) assert.deepEqual(inspectPhrase(data,after,key),['声音标签、说话人或署名'])
  assert.deepEqual(inspectPhrase(data,after,' '),[])
  assert.equal(publicAudio(after.last,data).filter(a=>!a.media).length,1)
  assert.ok(inspectPhrase(data,proofAt(data,2,'after'),'旧身份').includes('已读原文'))
  assert.deepEqual(inspectPhrase(data,proofAt(data,0,'before'),'旧身份'),[])  // backwards, not high-water
  const contiguous={...data,blocks:blocks.map((b,i)=>i===2?{...b,byte_start:blocks[1].byte_end}:b)}
  assert.equal(proofAt(contiguous,2,'before').gallery.length,1)  // touching block byte boundaries
  console.log('Passage proof: 4-surface hints, audio metadata and missing media, empty/future/emoji/CRLF/backwards boundaries passed.')
} finally { fs.rmSync(tmp,{recursive:true,force:true}) }
