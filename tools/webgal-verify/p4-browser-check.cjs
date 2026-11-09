// Full-text delivery check: real voices, figures and visual cards in a downloaded export.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const { chromium } = require('playwright');
const base = process.argv[2] || 'http://127.0.0.1:8000';
const root = path.resolve(__dirname, '../..');
const output = path.join(root, 'data/verification/p4');
fs.mkdirSync(output, { recursive: true });
const report = { passed: false, checked_at: new Date().toISOString() };

function figuresOnStage() {
  const found = [];
  function walk(node, visible = true, alpha = 1) {
    visible = visible && node.visible !== false && node.renderable !== false;
    alpha *= node.alpha ?? 1;
    const resource = node.texture?.baseTexture?.resource;
    const url = resource?.url || resource?.source?.src;
    if (visible && alpha > 0.01 && url?.includes('/game/figure/')) found.push(url);
    for (const child of node.children || []) walk(child, visible, alpha);
  }
  if (window.__PIXI_APP__) walk(window.__PIXI_APP__.stage);
  return found;
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  let server, engine;
  async function json(url, method = 'GET', data) {
    const r = await page.request.fetch(base + url, { method, data });
    assert.ok(r.ok(), await r.text());
    return r.json();
  }
  try {
    const raw = fs.readFileSync(path.join(root, 'samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt'));
    const response = await page.request.post(base + '/api/projects', { multipart: { file: { name: 'P4-赤壁联合交付验收.txt', mimeType: 'text/plain', buffer: raw }, rights_status: 'public_domain' } });
    assert.ok(response.ok());
    const pid = (await response.json()).id;
    report.project_id = pid;
    const prefix = `/api/projects/${pid}`;
    const review = () => json(prefix + '/review');
    const speech = () => json(prefix + '/speech');
    const visual = () => json(prefix + '/visual');
    async function waitJob(id) {
      for (let i = 0; i < 160; i++) {
        const job = (await json(prefix + '/jobs')).find(j => j.id === id);
        if (job.state !== 'running') return job;
        await page.waitForTimeout(300);
      }
      throw Error('job timeout');
    }
    let r = await review();
    const zhouyu = r.characters.find(c => c.display_name === '周瑜');
    const alias = r.characters.find(c => c.display_name === '瑜');
    assert.ok(zhouyu);
    if (alias) await json(prefix + `/characters/${alias.id}/merge`, 'POST', { revision: r.revision, target_id: zhouyu.id });
    const voices = (await speech()).capabilities.voices;
    for (const [name, sample, voicePrefix] of [['孔明', 'kongming', 'Eddy'], ['周瑜', 'zhouyu', 'Tingting']]) {
      r = await review();
      const character = r.characters.find(c => c.display_name === name);
      await json(prefix + `/characters/${character.id}`, 'PATCH', { revision: r.revision, display_name: name, aliases: character.aliases, status: 'confirmed' });
      r = await review();
      const asset = await json(prefix + `/characters/${character.id}/codex-sample`, 'POST', { revision: r.revision, sample_key: sample });
      r = await review();
      await json(prefix + `/assets/${asset.id}`, 'PATCH', { revision: r.revision, status: 'accepted', active: true });
      r = await review();
      const dialogue = r.dialogues.find(d => name === '孔明' ? d.text.startsWith('亮雖不才，曾遇異人') : d.text === '心腹攪痛，時復昏迷。');
      assert.ok(dialogue, name);
      await json(prefix + '/dialogues', 'PATCH', { revision: r.revision, dialogue_ids: [dialogue.id], speaker_id: character.id });
      let s = await speech();
      const voice = voices.find(v => v.startsWith(voicePrefix));
      assert.ok(voice, voicePrefix);
      await json(prefix + `/speech/profiles/${character.id}`, 'PATCH', { revision: s.revision, voice, speed: 180 });
      s = await speech();
      await json(prefix + `/speech/lines/${dialogue.id}`, 'PATCH', { revision: s.revision, selected: true });
    }
    // Real incomplete state must block export before any accepted audio exists.
    const blocked = await json(prefix + '/delivery');
    assert.equal(blocked.ready, false);
    assert.equal(blocked.checks.find(c => c.id === 'audio').passed, false);
    await page.goto(base);
    await page.evaluate(id => localStorage.setItem('storygal-project', id), pid);
    await page.reload();
    await page.getByRole('button', { name: '交付检查', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: '导出当前版本', exact: true }).isDisabled(), true);
    const failed = await waitJob((await json(prefix + '/exports', 'POST')).job_id);
    assert.equal(failed.state, 'failed');
    for (const line of (await speech()).lines.filter(l => l.selected)) {
      const job = await waitJob((await json(prefix + '/speech/generate', 'POST', { dialogue_id: line.id })).job_id);
      assert.equal(job.state, 'completed', job.error);
      const s = await speech();
      const updated = s.lines.find(l => l.id === line.id);
      await json(prefix + `/speech/lines/${line.id}/accept`, 'POST', { revision: s.revision, take_ids: Object.fromEntries(updated.segments.map(seg => [seg.key, seg.candidate.id])) });
    }
    const text = await json(prefix + '/text');
    function paragraphRefs(marker) {
      const source = raw.toString(), pos = source.indexOf(marker);
      assert.ok(pos > 0, marker);
      const start = Buffer.byteLength(source.slice(0, source.lastIndexOf('\n', pos) + 1));
      const end = Buffer.byteLength(source.slice(0, source.indexOf('\n', pos)));
      return { ids: text.spans.filter(s => s.byte_start >= start && s.byte_end <= end && s.kind !== 'whitespace').map(s => s.id), end };
    }
    const proof = paragraphRefs('卻說魯肅見周瑜臥病');
    const kongmingLine = (await speech()).lines.find(l => l.selected && l.speaker_name === '孔明');
    assert.ok(kongmingLine.segments.length > 1);
    const anchor = text.units.find(u => u.id === kongmingLine.segments[0].unit_id).byte_end;
    let v = await visual();
    const diagram = await json(prefix + '/visual/items', 'POST', { revision: v.revision, kind: 'diagram', title: '孔明與周瑜：原文醫病示意', anchor_byte: anchor, evidence_span_ids: proof.ids, graph: { nodes: [{ id: 'a', label: '孔明', evidence_span_ids: proof.ids }, { id: 'b', label: '周瑜', evidence_span_ids: proof.ids }], edges: [{ from_id: 'a', to_id: 'b', label: '醫', directed: true, evidence_span_ids: proof.ids }] } });
    v = await visual();
    await json(prefix + `/visual/items/${diagram.id}/render`, 'POST', { revision: v.revision });
    v = await visual();
    await json(prefix + `/visual/items/${diagram.id}/review`, 'PATCH', { revision: v.revision, status: 'accepted', enabled: true, evidence_confirmed: true });
    const fire = paragraphRefs('黃蓋用刀一招');
    v = await visual();
    const illustration = await json(prefix + '/visual/items', 'POST', { revision: v.revision, kind: 'illustration', title: '赤壁火船', anchor_byte: text.units.find(u => u.byte_end >= fire.end).byte_end, evidence_span_ids: fire.ids, graph: null });
    v = await visual();
    await json(prefix + `/visual/items/${illustration.id}/codex-sample`, 'POST', { revision: v.revision });
    v = await visual();
    await json(prefix + `/visual/items/${illustration.id}/review`, 'PATCH', { revision: v.revision, status: 'accepted', enabled: true });
    await page.getByRole('button', { name: '重新检查', exact: true }).click();
    await page.getByText('✓ 当前制作状态可以导出。', { exact: true }).waitFor();
    await page.getByRole('button', { name: '导出当前版本', exact: true }).click();
    let exported;
    for (let i = 0; i < 160; i++) {
      exported = (await json(prefix + '/jobs')).find(j => j.kind === 'export' && j.id !== failed.id);
      if (exported && exported.state !== 'running') break;
      await page.waitForTimeout(300);
    }
    assert.equal(exported.state, 'completed', exported.error);
    report.export_url = exported.result.play_url;
    report.download_url = exported.result.download_url;
    await page.getByRole('link', { name: '打开完整播放 ↗', exact: true }).waitFor();
    await page.getByRole('button', { name: /^导出 WebGAL/ }).waitFor();
    assert.equal(await page.getByRole('button', { name: '保存人工复核记录', exact: true }).isDisabled(), true);
    for (const width of [320, 375, 414, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({ path: path.join(output, `delivery-${width}.png`), fullPage: true });
    }
    assert.equal((await json(prefix + '/delivery')).records.length, 0);
    const downloaded = await page.request.get(base + exported.result.download_url);
    assert.ok(downloaded.ok());
    const bytes = await downloaded.body();
    assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), exported.result.archive_sha256);
    const archive = path.join(output, 'storygal-p4.zip');
    fs.writeFileSync(archive, bytes);
    const standalone = path.join(output, 'standalone', exported.id);
    const python = path.join(root, 'backend/.venv/bin/python');
    const unpack = spawnSync(python, ['-c', 'import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])', archive, standalone], { encoding: 'utf8' });
    assert.equal(unpack.status, 0, unpack.stderr);
    const verification = spawnSync(python, [path.join(standalone, 'verify_package.py')], { encoding: 'utf8' });
    assert.equal(verification.status, 0, verification.stderr);
    report.package_check = JSON.parse(verification.stdout);
    assert.ok(fs.readFileSync(path.join(standalone, 'storygal-source/original.txt')).equals(raw));
    const manifest = JSON.parse(fs.readFileSync(path.join(standalone, 'storygal-manifest.json')));
    assert.equal(manifest.figure_assets.length, 2);
    assert.equal(manifest.visual_events.length, 2);
    const voiced = manifest.units.filter(u => u.vocal_id);
    const takes = Object.fromEntries(manifest.speech.lines.flatMap(line => line.segments.filter(s => s.accepted).map(s => [s.accepted.id, s.accepted])));
    assert.ok(voiced.length >= 3);
    const types = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.wav': 'audio/wav', '.ttf': 'font/ttf' };
    server = http.createServer((req, res) => {
      const file = path.resolve(standalone, '.' + decodeURIComponent(new URL(req.url, 'http://localhost').pathname.replace(/\/$/, '/index.html')));
      if (!file.startsWith(standalone + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream' });
      fs.createReadStream(file).pipe(res);
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const standaloneURL = `http://127.0.0.1:${server.address().port}/index.html`;
    engine = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    engine.on('pageerror', e => errors.push(e.message));
    const resources = { figures: new Set(), audio: new Set(), visuals: new Set() };
    engine.on('response', r => { if (r.status() !== 200) return; for (const [name, folder] of [['figures', 'figure'], ['audio', 'vocal'], ['visuals', 'background']]) if (r.url().includes(`/game/${folder}/`)) resources[name].add(r.url()); });
    await engine.addInitScript(() => { window.__plays = []; document.addEventListener('playing', e => { if (e.target instanceof HTMLMediaElement) window.__plays.push({ src: e.target.currentSrc, duration: e.target.duration }); }, true); const start = AudioBufferSourceNode.prototype.start; AudioBufferSourceNode.prototype.start = function (...args) { window.__plays.push({ buffer: true, duration: this.buffer?.duration }); return start.apply(this, args); }; });
    await engine.goto(standaloneURL);
    await engine.locator('.html-body__title-enter').click();
    await engine.locator('.html-body__title-enter').waitFor({ state: 'hidden' });
    if (await engine.getByText('简体中文', { exact: true }).isVisible()) await engine.getByText('简体中文', { exact: true }).click();
    await engine.getByText('开始游戏', { exact: true }).first().locator('..').click();
    await engine.locator('#textBoxMain').waitFor();
    await engine.waitForTimeout(1800);
    let cards = 0, restored = false, previousFigure = null, audioCursor = 0;
    for (const unit of manifest.units) {
      report.last_frame = unit.id;
      await engine.waitForFunction(t => Array.from(document.querySelectorAll('#textBoxMain span[id]>span')).map(e => e.firstChild.textContent).join('') === t, unit.text, { timeout: 8000 });
      if (await engine.locator('#textBoxMain .Textelement_start').count()) { await engine.mouse.click(700, 300); await engine.waitForFunction(() => !document.querySelector('#textBoxMain .Textelement_start')); }
      const speaker = await engine.locator('#textBoxMain').evaluate(root => { const text = root.lastElementChild; const headings = Array.from(root.children).filter(e => e !== text && e.id !== 'miniAvatar'); return headings.length ? Array.from(headings.at(-1).querySelectorAll('[class*="_zhanwei_"]')).map(e => e.firstChild.textContent).join('') : ''; });
      assert.equal(speaker, unit.speaker_name || '', `speaker frame ${unit.id}`);
      if (previousFigure && !unit.figure_asset_id) {
        await engine.waitForTimeout(500);
        assert.deepEqual(await engine.evaluate(figuresOnStage), []);
      }
      previousFigure = unit.figure_asset_id;
      if (unit.vocal_id) {
        await engine.waitForFunction(({ after, id, duration }) => window.__plays.slice(after).some(p => p.src?.endsWith('/' + id + '.wav') || p.buffer && Math.abs(p.duration - duration) < 0.03), { after: audioCursor, id: unit.vocal_id, duration: takes[unit.vocal_id].duration }, { timeout: 6000 });
        audioCursor = await engine.evaluate(() => window.__plays.length);
        await engine.waitForTimeout(500);
        const displayed = await engine.evaluate(figuresOnStage);
        assert.ok(displayed.some(url => url.endsWith(unit.figure_asset_id + '.png')), `figure frame ${unit.id}: ${JSON.stringify(displayed)}`);
        await engine.screenshot({ path: path.join(output, `speaking-${unit.speaker_name}.png`) });
        if (cards && unit.speaker_name === '孔明') restored = true;
      }
      await engine.mouse.click(700, 300);
      for (const event of manifest.visual_events.filter(e => e.after_unit_id === unit.id)) {
        await engine.waitForFunction(() => !document.querySelector('#textBoxMain'));
        await engine.waitForTimeout(500);
        assert.deepEqual(await engine.evaluate(figuresOnStage), []);
        await engine.screenshot({ path: path.join(output, `playing-${event.kind}.png`) });
        cards++;
        await engine.mouse.click(700, 300);
      }
      if (unit.id % 50 === 0) console.log(`P4: ${unit.id + 1}/${manifest.units.length} frames`);
    }
    await engine.waitForFunction(() => !document.querySelector('#textBoxMain'));
    const plays = await engine.evaluate(() => window.__plays);
    assert.equal(resources.figures.size, 2);
    assert.equal(resources.audio.size, voiced.length);
    assert.ok(plays.filter(p => p.src?.includes('/game/vocal/') || p.buffer && p.duration > 0 && p.duration < 120).length >= voiced.length);
    assert.equal(cards, 2);
    assert.ok(restored);
    assert.deepEqual(errors, []);
    Object.assign(report, { passed: true, original_bytes_equal: true, characters: raw.toString().length, text_frames: manifest.units.length, speaker_labels_equal: true, figures: 2, voiced_frames: voiced.length, audio_started: true, audio_each_frame_started: true, visual_pages: cards, figure_hidden_on_cards_and_restored: restored, independent_download_playback: true, reached_end: true, incomplete_audio_blocked_and_retry_succeeded: true, manual_review_left_pending: true, viewports: [320, 375, 414, 768, 1440], archive_sha256: exported.result.archive_sha256 });
    console.log(JSON.stringify(report));
  } catch (e) {
    report.error = String(e.stack || e);
    if (engine) await engine.screenshot({ path: path.join(output, 'failure.png') });
    throw e;
  } finally {
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    await browser.close();
    if (server) await new Promise(resolve => server.close(resolve));
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
