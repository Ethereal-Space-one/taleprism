// Continuous reader verification through real UI, real system speech and an extracted export.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const { chromium } = require('playwright');
const base = process.argv[2] || 'http://127.0.0.1:8000';
const root = path.resolve(__dirname, '../..');
const out = path.join(root, 'data/verification/p5');
fs.mkdirSync(out, { recursive: true });
const report = { passed: false, checked_at: new Date().toISOString() };
const python = path.join(root, 'backend/.venv/bin/python');
const visible = text => text.replace(/^\uFEFF/, '').split(/\r\n|\r|\n/).map(line => line.replace(/^[ \t\u3000]+|[ \t\u3000]+$/g, '')).join('');

(async () => {
  if (!process.argv.includes('--reuse') || !fs.existsSync(path.join(out, 'fixture.json'))) {
    const prepared = spawnSync(python, [path.join(root, 'tools/prepare_reader_sample.py'), '--base', base], { encoding: 'utf8' });
    assert.equal(prepared.status, 0, prepared.stderr);
  }
  const fixture = JSON.parse(fs.readFileSync(path.join(out, 'fixture.json')));
  report.project_id = fixture.project_id;
  const prefix = `/api/projects/${fixture.project_id}`;
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const maker = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  let reader, server;
  maker.on('pageerror', e => errors.push(e.message));
  async function json(url, method = 'GET', data) { const response = await maker.request.fetch(base + url, { method, data }); assert.ok(response.ok(), await response.text()); return response.json(); }
  async function until(fn, timeout = 15000) { const start = Date.now(); while (Date.now() - start < timeout) { const value = await fn(); if (value) return value; await maker.waitForTimeout(120); } throw Error('condition timeout'); }
  async function waitJob(id) { return until(async () => { const job = (await json(prefix + '/jobs')).find(j => j.id === id); return job && job.state !== 'running' ? job : false; }, 60000); }
  async function startReading(page, resume = false) { await page.getByRole('button', { name: resume ? /^继续阅读/ : /^开始阅读/ }).click(); await page.locator('.reader-scroll').waitFor(); }
  async function goScene(page, title) {
    await page.getByRole('button', { name: '打开章节目录' }).click();
    await page.locator('.reader-contents').getByRole('button', { name: new RegExp('^' + title) }).click();
    await page.waitForTimeout(230);
    await page.waitForFunction(t => document.querySelector('.reader-stage-caption>span')?.textContent === t, title);
  }
  async function imagesReady(page) { await page.waitForFunction(() => Array.from(document.querySelectorAll('.reader-cover-art,.reader-background,.reader-portraits img')).every(i => i.complete && i.naturalWidth > 0)); }
  async function viewport(page, width, height = 1000) { await page.setViewportSize({ width, height }); await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))); }
  async function noOverflow(page) { assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false); assert.equal(await page.evaluate(() => document.querySelector('.reader-root')?.scrollWidth > innerWidth), false); }
  try {
    const raw = fs.readFileSync(path.join(root, 'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'));
    const initial = await json(prefix + '/reader');
    const pending = initial.assets.filter(a => a.status !== 'accepted');
    if (pending.length) {
      assert.equal((await json(prefix + '/reader/content')).preview, true);
      const failed = await waitJob((await json(prefix + '/reader/exports', 'POST')).job_id);
      assert.equal(failed.state, 'failed'); report.pending_assets_blocked = true;
    }
    await maker.goto(base); await maker.evaluate(pid => localStorage.setItem('storygal-project', pid), fixture.project_id); await maker.reload();
    await maker.getByRole('button', { name: '独立阅读器', exact: true }).click();
    await maker.locator('.reader-asset-grid figure').first().waitFor();
    for (const asset of pending) {
      const card = maker.locator('.reader-asset-grid figure').filter({ has: maker.locator('figcaption', { hasText: asset.sample_key }) });
      await card.getByRole('button', { name: '接受此图', exact: true }).click();
      await until(async () => (await json(prefix + '/reader')).assets.find(a => a.id === asset.id).status === 'accepted');
    }
    await maker.getByText('编辑封面、场景与人物', { exact: true }).click();
    assert.equal(await maker.locator('.reader-scene-row').first().getByLabel('孔明', { exact: true }).isChecked(), true);
    const saveConfig = maker.getByRole('button', { name: '保存阅读器配置', exact: true });
    for (const title of ['赤壁·配置验收', '赤壁']) {
      await maker.getByLabel('章节名称', { exact: true }).fill(title); await saveConfig.click();
      await until(async () => (await json(prefix + '/reader')).config.title === title && await saveConfig.isEnabled());
    }
    await maker.getByText('编辑封面、场景与人物', { exact: true }).click();
    for (const width of [320,375,414,768,1440]) { await viewport(maker, width); assert.equal(await maker.evaluate(() => document.documentElement.scrollWidth > innerWidth), false); await maker.screenshot({ path: path.join(out, `maker-${width}.png`), fullPage: true }); }
    report.maker_config_saved = true;
    const content = await json(prefix + '/reader/content');
    assert.equal(content.preview, false); assert.equal(content.issues.length, 0);
    assert.equal(content.config.scenes.length, 10);
    reader = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    reader.on('pageerror', e => errors.push(e.message));
    await reader.goto(base + fixture.reader_url);
    await reader.getByRole('heading', { name: '赤壁', exact: true }).waitFor();
    await imagesReady(reader);
    for (const width of [320, 375, 414, 768, 1440]) { await viewport(reader, width); await noOverflow(reader); await reader.screenshot({ path: path.join(out, `cover-${width}.png`), fullPage: true }); }
    for (const [width, height] of [[1280,800],[320,640]]) { await viewport(reader, width, height); await noOverflow(reader); const rect = await reader.getByRole('button', { name: /^开始阅读/ }).boundingBox(); assert.ok(rect.y >= 0 && rect.y + rect.height <= height); await reader.screenshot({ path: path.join(out, `cover-${width}x${height}.png`), fullPage: true }); }
    await viewport(reader, 1440);
    await startReading(reader);
    await imagesReady(reader);
    assert.equal(await reader.locator('.reader-paragraph-text').evaluateAll(es => es.map(e => e.textContent).join('')), visible(raw.toString()));
    assert.equal(await reader.locator('audio').evaluate(a => a.paused && !a.getAttribute('src')), true);
    assert.equal(await reader.locator('.reader-spoken').count(), 0);
    report.contrast = await reader.evaluate(() => {
      const style = getComputedStyle(document.querySelector('.reader-root'));
      const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1; const ctx = canvas.getContext('2d');
      function luminance(name) { ctx.fillStyle = style.getPropertyValue(name).trim(); ctx.fillRect(0,0,1,1); const rgb = [...ctx.getImageData(0,0,1,1).data].slice(0,3).map(v => { const s=v/255; return s<=.04045 ? s/12.92 : ((s+.055)/1.055)**2.4 }); return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722; }
      function ratio(a,b) { const x=luminance(a),y=luminance(b); return Math.round((Math.max(x,y)+.05)/(Math.min(x,y)+.05)*100)/100; }
      return { body: ratio('--reader-ink','--reader-panel'), helper: ratio('--reader-muted','--reader-panel'), accent: ratio('--reader-accent','--reader-panel'), map: ratio('--reader-map-ink','--reader-map-paper') };
    });
    assert.ok(report.contrast.body >= 7 && report.contrast.helper >= 4.5 && report.contrast.accent >= 4.5 && report.contrast.map >= 7);
    for (const width of [320, 375, 414, 768, 1440]) { await viewport(reader, width); await imagesReady(reader); await noOverflow(reader); await reader.screenshot({ path: path.join(out, `reading-${width}.png`), fullPage: true }); }
    await goScene(reader, '南屏山·祭风'); await imagesReady(reader);
    const position = await reader.locator('.reader-scroll').evaluate(el => el.scrollTop);
    await reader.getByRole('button', { name: '地图', exact: true }).click();
    await reader.getByRole('img', { name: /^赤壁战区地图/ }).waitFor();
    assert.equal(await reader.getByRole('button', { name: '火攻推进 · 未读', exact: true }).isDisabled(), true);
    await reader.getByRole('button', { name: '乌林', exact: true }).click();
    assert.ok((await reader.locator('.map-place-detail').textContent()).includes('洪湖'));
    for (const width of [320, 375, 414, 768, 1440]) { await viewport(reader, width); const toggle = reader.getByRole('button', { name: width < 600 ? '两岸局部' : '战区概览', exact: true }); if (await toggle.count()) await toggle.click(); await noOverflow(reader); await reader.screenshot({ path: path.join(out, `map-${width}.png`), fullPage: true }); }
    await reader.getByRole('button', { name: '关闭面板' }).click();
    // A viewport resize legitimately changes scroll geometry; verify map itself preserves position at one size.
    await goScene(reader, '南屏山·祭风');
    const beforeMap = await reader.locator('.reader-scroll').evaluate(el => el.scrollTop);
    await reader.getByRole('button', { name: '地图', exact: true }).click(); await reader.getByRole('button', { name: '关闭面板' }).click();
    assert.ok(Math.abs(await reader.locator('.reader-scroll').evaluate(el => el.scrollTop) - beforeMap) < 2);
    assert.ok(position > 0);
    const zhouBlock = content.blocks.find(b => b.audio.some(a => content.characters[a.speaker_id].name === '周瑜'));
    await reader.locator(`#${zhouBlock.id}`).getByRole('button', { name: '朗读周瑜第1段', exact: true }).click();
    await reader.waitForFunction(() => document.querySelector('audio').currentTime > .2);
    assert.ok((await reader.locator('.reader-portraits .is-speaking').textContent()).includes('周瑜'));
    assert.ok(await reader.locator('.reader-spoken').count());
    await reader.locator('.reader-audio-controls').getByRole('button', { name: '暂停', exact: true }).click();
    const pausedTime = await reader.locator('audio').evaluate(a => a.currentTime); await reader.waitForTimeout(250);
    assert.ok(Math.abs(await reader.locator('audio').evaluate(a => a.currentTime) - pausedTime) < .05);
    assert.equal(await reader.locator('audio').evaluate(a => a.paused), true);
    await reader.locator('.reader-audio-controls').getByRole('button', { name: '重播', exact: true }).click();
    await reader.waitForFunction(() => !document.querySelector('audio').paused && document.querySelector('audio').currentTime > 0);
    // Native scroll, rather than opening a panel, must cancel speech when leaving its paragraph.
    const altar = content.config.scenes.find(s => s.title === '南屏山·祭风');
    await reader.locator('.reader-scroll').evaluate((el, byte) => { const p = document.querySelector(`[data-byte-start="${byte}"]`); el.scrollTop += p.getBoundingClientRect().top - el.getBoundingClientRect().top - 24; }, altar.start_byte);
    await reader.waitForFunction(() => document.querySelector('audio').paused && !document.querySelector('audio').getAttribute('src'));
    assert.equal(await reader.locator('.reader-spoken').count(), 0);
    const kongmingBlock = content.blocks.find(b => b.audio.some(a => content.characters[a.speaker_id].name === '孔明'));
    assert.equal(kongmingBlock.audio.length, 2);
    await reader.locator(`#${kongmingBlock.id}`).getByRole('button', { name: '朗读孔明第1段', exact: true }).click();
    await reader.waitForFunction(() => document.querySelector('audio').currentTime > .1 && document.querySelector('audio').duration > 0);
    await reader.locator('audio').evaluate(a => { a.currentTime = a.duration - .12; });
    await reader.waitForFunction(id => document.querySelector('audio').currentSrc.endsWith('/' + id) && document.querySelector('audio').currentTime > 0, kongmingBlock.audio[1].take_id);
    await reader.screenshot({ path: path.join(out, 'speaking-kongming.png') });
    await goScene(reader, '山林败走'); await imagesReady(reader);
    const forest = content.config.scenes.find(s => s.title === '山林败走');
    await reader.getByRole('button', { name: '设置', exact: true }).click();
    const sizeSlider = reader.getByLabel(/正文字号/); await sizeSlider.focus(); await sizeSlider.press('Home'); for (let i = 0; i < 7; i++) await sizeSlider.press('ArrowRight'); await reader.getByRole('button', { name: '关闭面板' }).click();
    assert.equal(await reader.locator('.reader-paragraph.is-current').getAttribute('data-byte-start'), String(forest.start_byte));
    await reader.reload(); await reader.getByRole('button', { name: /^继续阅读/ }).waitFor(); await startReading(reader, true); await imagesReady(reader);
    await reader.waitForFunction(title => document.querySelector('.reader-stage-caption>span')?.textContent === title, '山林败走');
    assert.equal(await reader.locator('.reader-scroll').evaluate(el => el.style.getPropertyValue('--reader-size')), '25px');
    await reader.getByRole('button', { name: '地图', exact: true }).click();
    assert.equal(await reader.getByRole('button', { name: '战后撤军', exact: true }).isEnabled(), true);
    await reader.screenshot({ path: path.join(out, 'map-retreat.png') });
    await reader.getByRole('button', { name: '关闭面板' }).click();
    for (const title of ['东风起', '火起江面', '山林败走']) { await goScene(reader, title); await imagesReady(reader); await reader.screenshot({ path: path.join(out, `scene-${title}.png`) }); }
    await reader.locator('.reader-scroll').evaluate(el => { el.scrollTop = el.scrollHeight; }); await reader.getByLabel('阅读进度 100%').waitFor();
    await reader.screenshot({ path: path.join(out, 'end.png') });
    // A failed image must not prevent the full original text from remaining readable.
    const fallback = await browser.newPage({ viewport: { width: 375, height: 1000 } });
    await fallback.route(base + content.media[content.config.scenes[0].asset_id].url, route => route.fulfill({ status: 404, body: '' }));
    await fallback.goto(base + fixture.reader_url); await startReading(fallback); await fallback.getByText('场景图片暂不可用，正文仍可阅读。', { exact: true }).waitFor();
    assert.equal(await fallback.locator('.reader-paragraph-text').evaluateAll(es => es.map(e => e.textContent).join('')), visible(raw.toString()));
    await fallback.screenshot({ path: path.join(out, 'image-fallback-375.png') }); await fallback.close();
    await maker.getByRole('button', { name: '导出独立阅读器', exact: true }).click();
    const job = await until(async () => (await json(prefix + '/jobs')).find(j => j.kind === 'reader_export' && j.state === 'completed'), 60000);
    const response = await maker.request.get(base + job.result.download_url); assert.ok(response.ok()); const zip = await response.body();
    assert.equal(crypto.createHash('sha256').update(zip).digest('hex'), job.result.archive_sha256);
    const archive = path.join(out, 'storygal-reader.zip'); fs.writeFileSync(archive, zip);
    const unpacked = path.join(out, 'standalone', job.id);
    const unpack = spawnSync(python, ['-c', 'import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])', archive, unpacked], { encoding: 'utf8' }); assert.equal(unpack.status, 0, unpack.stderr);
    const checked = spawnSync(python, [path.join(unpacked, 'verify_package.py')], { encoding: 'utf8' }); assert.equal(checked.status, 0, checked.stderr);
    const mime = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.wav': 'audio/wav' };
    server = http.createServer((req, res) => { const file = path.resolve(unpacked, '.' + new URL(req.url, 'http://localhost').pathname.replace(/\/$/, '/index.html')); if (!file.startsWith(unpacked + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream' }); fs.createReadStream(file).pipe(res); });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const offline = await browser.newPage({ viewport: { width: 1440, height: 1000 } }); const apiCalls = [];
    offline.on('pageerror', e => errors.push(e.message)); offline.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/')) apiCalls.push(r.url()); });
    await offline.goto(`http://127.0.0.1:${server.address().port}/index.html`); await imagesReady(offline); await startReading(offline); await imagesReady(offline);
    assert.equal(await offline.locator('.reader-paragraph-text').evaluateAll(es => es.map(e => e.textContent).join('')), visible(raw.toString()));
    await offline.locator(`#${zhouBlock.id}`).getByRole('button', { name: '朗读周瑜第1段', exact: true }).click(); await offline.waitForFunction(() => document.querySelector('audio').currentTime > 0);
    await goScene(offline, '火起江面'); await imagesReady(offline); await offline.getByRole('button', { name: '地图', exact: true }).click(); await offline.getByRole('img', { name: /^赤壁战区地图/ }).waitFor(); await offline.getByRole('button', { name: '关闭面板' }).click();
    await offline.locator('.reader-scroll').evaluate(el => { el.scrollTop = el.scrollHeight; }); await offline.getByLabel('阅读进度 100%').waitFor();
    assert.deepEqual(apiCalls, []); assert.deepEqual(errors, []);
    const specialText = '原文 <script>window.__readerXSS=1</script> {变量} -next 😀。';
    const specialResponse = await maker.request.post(base + '/api/projects', { multipart: { file: { name: 'reader-specials.txt', mimeType: 'text/plain', buffer: Buffer.from(specialText) }, rights_status: 'owned' } });
    assert.ok(specialResponse.ok()); const special = await specialResponse.json();
    const specialPage = await browser.newPage(); await specialPage.goto(base + '/read/' + special.id); await startReading(specialPage);
    assert.equal(await specialPage.locator('.reader-paragraph-text').textContent(), specialText);
    assert.equal(await specialPage.evaluate(() => window.__readerXSS), undefined); await specialPage.close();
    assert.equal((await json(prefix + '/delivery')).records.length, 0);
    Object.assign(report, { passed: true, reader_url: fixture.reader_url, export_url: job.result.play_url, download_url: job.result.download_url, paragraphs: content.blocks.length, original_bytes_equal: (await maker.request.get(base + prefix + '/source')).body().then(b => b.equals(raw)), text_equal: true, scenes: 10, background_images: 5, cover: true, portraits: 2, audio_clips: 3, real_audio_played: true, audio_pause_replay_and_scroll_cancel: true, same_paragraph_queue: true, map_phase_gate_and_places: true, map_preserves_reading_position: true, progress_and_font_restored: true, missing_image_keeps_text: true, standalone_without_api: true, reached_end: true, manual_review_left_pending: true, package_check: JSON.parse(checked.stdout), viewports: [320,375,414,768,1440] });
    report.original_bytes_equal = await report.original_bytes_equal;
    console.log(JSON.stringify(report));
  } catch (e) { report.error = String(e.stack || e); if (reader) await reader.screenshot({ path: path.join(out, 'failure.png') }); throw e; }
  finally { fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2)); await browser.close(); if (server) await new Promise(resolve => server.close(resolve)); }
})().catch(e => { console.error(e); process.exitCode = 1; });
