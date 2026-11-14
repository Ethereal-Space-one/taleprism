const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const base = (process.argv[2] || 'http://127.0.0.1:8000').replace(/\/$/, '');
const out = path.resolve(__dirname, '../../data/verification/p1');
fs.mkdirSync(out, { recursive: true });
const STORY = '孔明曰：「此都督病源也。」\n周瑜曰：「願先生賜教。」\n孔明笑曰：「亮有一方。」\n天色漸暗。\n有人問：「誰在那裡？」';
const report = { checked_at: new Date().toISOString(), passed: false, ui: [], playback: {} };
async function waitState(page, pid, test) {
  let last;
  for (let n = 0; n < 120; n++) {
    last = await (await page.request.get(base + `/api/projects/${pid}/review`)).json();
    if (test(last)) return last;
    await page.waitForTimeout(150);
  }
  throw Error('Review state update timed out');
}
async function waitJob(page, pid, kind, oldId) {
  for (let n = 0; n < 200; n++) {
    const jobs = await (await page.request.get(base + `/api/projects/${pid}/jobs`)).json();
    const job = jobs.find(j => j.kind === kind && j.id !== oldId);
    if (job && job.state !== 'running') { assert.equal(job.state, 'completed', job.error); return job; }
    await page.waitForTimeout(900);
  }
  throw Error(`${kind} timeout`);
}
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  try {
    await page.goto(base);
    await page.getByRole('button', { name: '导入新文本' }).click();
    await page.getByLabel('TXT 文件').setInputFiles({ name: 'P1-人物与立绘验收.txt', mimeType: 'text/plain', buffer: Buffer.from(STORY) });
    await page.getByLabel('文本权利状态').selectOption('public_domain');
    const response = page.waitForResponse(r => r.url() === base + '/api/projects' && r.request().method() === 'POST');
    await page.getByRole('button', { name: '导入并预览' }).click();
    const project = await (await response).json();
    const pid = project.id;
    report.project_id = pid;
    await page.getByRole('button', { name: /人物与审校/ }).click();
    await page.getByRole('tab', { name: /角色资产/ }).click();
    await page.getByRole('button', { name: '编辑角色 孔明', exact: true }).click();
    let form = page.locator('.identity-form');
    await form.getByLabel('角色名称').fill('諸葛亮');
    await form.getByLabel('别名与称呼').fill('孔明');
    await form.getByLabel('身份说明').fill('公有领域样例的人工确认角色；形象参考道衣、散发、跣足描写。');
    await form.getByRole('button', { name: '保存并确认身份' }).click();
    let s = await waitState(page, pid, s => s.characters.some(c => c.display_name === '諸葛亮' && c.status === 'confirmed'));
    const kongming = s.characters.find(c => c.display_name === '諸葛亮');
    await page.getByRole('button', { name: '导入 Codex 候选图' }).click();
    s = await waitState(page, pid, s => s.assets.some(a => a.character_id === kongming.id));
    assert.equal(s.assets[0].status, 'pending');
    await page.getByRole('button', { name: '接受并设为立绘' }).click();
    await waitState(page, pid, s => s.characters.find(c => c.id === kongming.id).active_figure_id);
    await page.getByRole('button', { name: '编辑角色 周瑜', exact: true }).click();
    await page.locator('.identity-form').getByRole('button', { name: '保存并确认身份' }).click();
    s = await waitState(page, pid, s => s.characters.some(c => c.display_name === '周瑜' && c.status === 'confirmed'));
    const zhouyu = s.characters.find(c => c.display_name === '周瑜');
    await page.locator('.codex-import select').selectOption('zhouyu');
    await page.getByRole('button', { name: '导入 Codex 候选图' }).click();
    await waitState(page, pid, s => s.assets.some(a => a.character_id === zhouyu.id));
    await page.getByRole('button', { name: '接受并设为立绘' }).click();
    await waitState(page, pid, s => s.characters.find(c => c.id === zhouyu.id).active_figure_id);
    // Exercise identity merge in the UI; preserve the established target ID.
    await page.getByRole('button', { name: '＋ 新建角色' }).click();
    await page.locator('.identity-form').getByLabel('角色名称').fill('臥龍');
    await page.getByRole('button', { name: '添加并确认角色' }).click();
    await waitState(page, pid, s => s.characters.some(c => c.display_name === '臥龍'));
    await page.getByRole('button', { name: '编辑角色 臥龍', exact: true }).click();
    await page.getByLabel('合并目标').selectOption(kongming.id);
    await page.getByRole('button', { name: '合并角色', exact: true }).click();
    await waitState(page, pid, s => s.characters.find(c => c.id === kongming.id).aliases.includes('臥龍'));
    await page.getByRole('button', { name: '编辑角色 諸葛亮', exact: true }).click();
    await page.screenshot({ path: path.join(out, 'characters-desktop.png'), fullPage: true });
    await page.getByRole('tab', { name: /对白审校/ }).click();
    await page.getByLabel('对白筛选').selectOption('all');
    const names = ['諸葛亮', '周瑜', '諸葛亮', null];
    for (let i = 0; i < names.length; i++) {
      await page.getByRole('button', { name: `审校对白 ${i + 1}`, exact: true }).click();
      await page.locator('.speaker-buttons').getByRole('button', { name: names[i] ? new RegExp(names[i]) : /保留未知/ }).click();
      await waitState(page, pid, s => s.dialogues[i].status === 'reviewed');
    }
    s = await (await page.request.get(base + `/api/projects/${pid}/review`)).json();
    assert.equal(s.pending_count, 0);
    assert.deepEqual(s.dialogues.map(d => d.speaker_id), [kongming.id, zhouyu.id, kongming.id, null]);
    const reviewed = s.dialogues.map(d => [d.id, d.speaker_id]);
    // A live model request and then a cached rerun must not replace human decisions.
    await page.getByRole('button', { name: 'DeepSeek 抽取候选' }).click();
    const analysis = await waitJob(page, pid, 'analysis');
    await page.getByRole('button', { name: 'DeepSeek 抽取候选' }).waitFor({ state: 'visible' });
    await page.getByRole('button', { name: 'DeepSeek 抽取候选' }).click();
    const rerun = await waitJob(page, pid, 'analysis', analysis.id);
    assert.equal(rerun.result.requests, 0);
    s = await (await page.request.get(base + `/api/projects/${pid}/review`)).json();
    assert.deepEqual(s.dialogues.map(d => [d.id, d.speaker_id]), reviewed);
    report.ai = { first: analysis.result, rerun: rerun.result, manual_decisions_preserved: true };
    for (const width of [320, 375, 414, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({ path: path.join(out, `review-${width}.png`), fullPage: true });
      report.ui.push({ width, no_horizontal_overflow: true });
    }
    await page.getByRole('button', { name: '交付检查', exact: true }).click();
    await page.getByText('其他格式 · WebGAL 兼容导出', { exact: true }).click();
    await page.getByRole('button', { name: '检查 WebGAL 兼容性', exact: true }).click();
    await page.getByRole('dialog', { name: 'WebGAL 兼容导出' }).getByRole('button', { name: '导出 WebGAL 兼容版', exact: true }).click();
    const exported = await waitJob(page, pid, 'export');
    const url = exported.result.play_url;
    report.export_url = url;
    const manifest = await (await page.request.get(base + url.replace('index.html', 'storygal-manifest.json'))).json();
    assert.equal(manifest.figure_assets.length, 2);
    assert.equal(manifest.units.filter(u => u.figure_asset_id === s.characters.find(c => c.id === kongming.id).active_figure_id).length, 2);
    const source = await page.request.get(base + `/api/projects/${pid}/source`);
    assert.equal((await source.body()).toString(), STORY);
    const engine = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    engine.on('pageerror', e => errors.push(e.message));
    const fetchedFigures = new Set();
    engine.on('response', r => { if (/\/game\/figure\//.test(r.url()) && r.status() === 200) fetchedFigures.add(r.url()); });
    await engine.goto(base + url);
    await engine.locator('.html-body__title-enter').click();
    await engine.locator('.html-body__title-enter').waitFor({ state: 'hidden' });
    if (await engine.getByText('简体中文', { exact: true }).isVisible()) await engine.getByText('简体中文', { exact: true }).click();
    await engine.getByText('开始游戏', { exact: true }).first().locator('..').click();
    await engine.locator('#textBoxMain').waitFor();
    await engine.waitForTimeout(1800);
    let checked = 0;
    for (const unit of manifest.units) {
      await engine.waitForFunction(text => Array.from(document.querySelectorAll('#textBoxMain span[id] > span')).map(e => e.firstChild.textContent).join('') === text, unit.text);
      if (await engine.locator('#textBoxMain .Textelement_start').count()) {
        await engine.mouse.click(700, 300);
        await engine.waitForFunction(() => !document.querySelector('#textBoxMain .Textelement_start'));
      }
      // The speaker heading is rendered with stroke/shadow copies; read only base text nodes.
      const speaker = await engine.locator('#textBoxMain').evaluate(root => {
        const text = root.lastElementChild;
        const headings = Array.from(root.children).filter(e => e !== text && e.id !== 'miniAvatar');
        if (!headings.length) return '';
        return Array.from(headings.at(-1).querySelectorAll('[class*="_zhanwei_"]')).map(e => e.firstChild.textContent).join('');
      });
      assert.equal(speaker, unit.speaker_name || '', `speaker at frame ${unit.id}`);
      if (unit.id === 0 || unit.id === 1 || unit.id === 3) {
        await engine.waitForTimeout(500);
        await engine.screenshot({ path: path.join(out, `playback-${unit.id}.png`) });
      }
      checked++;
      await engine.mouse.click(700, 300);
    }
    await engine.waitForFunction(() => !document.querySelector('#textBoxMain'));
    assert.equal(fetchedFigures.size, 2);
    assert.deepEqual(errors, []);
    report.playback = { checked_frames: checked, text_equal: true, speaker_labels_equal: true, unique_figures: fetchedFigures.size, reused_kongming: true, unknown_speaker_cleared: true, reached_end: true };
    report.passed = true;
    console.log(JSON.stringify(report.playback));
  } catch (error) {
    report.error = String(error.stack || error);
    throw error;
  } finally {
    fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
