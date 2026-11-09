const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path')
const { chromium } = require('playwright')
const out = path.resolve(__dirname,'../../data/verification/p9')
const fixture = JSON.parse(fs.readFileSync(path.join(out,'fixture.json')))
const base = process.argv[2] || 'http://127.0.0.1:8000'
;(async()=>{
  const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true})
  const report={passed:false,checked_at:new Date().toISOString(),project_id:fixture.project_id}
  try {
    const page=await browser.newPage({viewport:{width:375,height:812}})
    await page.goto(base+fixture.reader_url)
    await page.getByRole('button',{name:/^开始阅读/}).click()
    const anchor=await page.locator('.reader-root').getAttribute('data-resume-byte')
    await page.getByRole('button',{name:'设置',exact:true}).click()
    await page.getByRole('button',{name:/^本章画卷/}).click()
    await page.locator('.reader-gallery>div>button').filter({hasText:'军帐授计'}).click()
    for(const width of [320,375,414,768,1440]){
      await page.setViewportSize({width,height:812})
      const img=page.locator('.reader-expanded-image');await img.evaluate(i=>i.decode())
      await page.getByRole('button',{name:'放大细节 2×',exact:true}).click()
      const scroller=page.locator('.reader-image-viewport')
      assert.ok(await scroller.evaluate(e=>e.scrollWidth>e.clientWidth))
      await scroller.evaluate(e=>{e.scrollLeft=120;e.scrollTop=80})
      assert.ok(await scroller.evaluate(e=>e.scrollLeft>0))
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
      assert.equal(await page.locator('.reader-root').getAttribute('data-resume-byte'),anchor)
      await page.screenshot({path:path.join(out,'detail-zoom-'+width+'.png')})
      await page.getByRole('button',{name:'恢复完整画面',exact:true}).click()
    }
    report.detail_pan_five_viewports=true
    await page.close()
    const broken=await browser.newPage({viewport:{width:375,height:812}})
    const r=await broken.request.get(base+'/api/projects/'+fixture.project_id+'/reader/content'), data=await r.json()
    const asset=data.media[data.config.illustrations[0].image_asset_id]
    await broken.route('**'+asset.url,route=>route.abort())
    await broken.goto(base+fixture.reader_url)
    await broken.getByRole('button',{name:/^开始阅读/}).click()
    const first=broken.locator('.reader-plate').first()
    await first.scrollIntoViewIfNeeded()
    await first.getByText('这幅插图暂不可用，正文仍可阅读。').waitFor()
    assert.equal(await broken.locator('.reader-paragraph-text').count(),67)
    assert.equal(await first.locator('button.reader-plate-art').isDisabled(),true)
    const box=await first.locator('.reader-plate-art').boundingBox();assert.ok(box.height>100)
    assert.equal(await broken.locator('audio').evaluate(e=>e.paused),true)
    await broken.screenshot({path:path.join(out,'image-failure-375.png')})
    report.image_failure_reserves_space_and_keeps_prose=true
    report.passed=true
  } finally {fs.writeFileSync(path.join(out,'edge-report.json'),JSON.stringify(report,null,2));await browser.close()}
  console.log(JSON.stringify(report,null,2))
})().catch(e=>{console.error(e);process.exit(1)})
