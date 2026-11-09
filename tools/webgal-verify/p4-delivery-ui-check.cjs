// Synthetic review-form check; never marks the full chapter as user-approved.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const base = process.argv[2] || 'http://127.0.0.1:8000';
const output = path.resolve(__dirname, '../../data/verification/p4');
fs.mkdirSync(output, { recursive: true });
const report = { passed: false };
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const page = await browser.newPage();
  async function json(url, method = 'GET', data) { const r = await page.request.fetch(base + url, { method, data }); assert.ok(r.ok(), await r.text()); return r.json(); }
  try {
    const r = await page.request.post(base + '/api/projects', { multipart: { file: { name: '复核表单自动测试.txt', mimeType: 'text/plain', buffer: Buffer.from('此项目只用于自动检查复核表单，不代表用户审查。') }, rights_status: 'local_test' } });
    assert.ok(r.ok());
    const pid = (await r.json()).id, prefix = `/api/projects/${pid}`;
    async function exportNow() { const id = (await json(prefix + '/exports', 'POST')).job_id; for (let i = 0; i < 120; i++) { const job = (await json(prefix + '/jobs')).find(j => j.id === id); if (job.state !== 'running') { assert.equal(job.state, 'completed', job.error); return job; } await page.waitForTimeout(150); } throw Error('export timeout'); }
    await exportNow();
    await page.goto(base); await page.evaluate(id => localStorage.setItem('storygal-project', id), pid); await page.reload();
    await page.getByRole('button', { name: '交付检查', exact: true }).click();
    const boxes = page.locator('.delivery-review input[type=checkbox]');
    const save = page.getByRole('button', { name: '保存人工复核记录', exact: true });
    await save.waitFor(); assert.equal(await save.isDisabled(), true);
    for (let i = 0; i < 5; i++) await boxes.nth(i).check();
    assert.equal(await save.isEnabled(), true);
    const latest = await exportNow();
    await page.getByRole('button', { name: '重新检查', exact: true }).click();
    await page.waitForFunction(id => document.querySelector('.delivery-output a')?.getAttribute('href')?.includes(id), latest.id);
    assert.equal(await boxes.evaluateAll(es => es.filter(e => e.checked).length), 0);
    assert.equal(await save.isDisabled(), true);
    for (let i = 0; i < 5; i++) await boxes.nth(i).check();
    await page.locator('.delivery-review textarea').fill('自动化界面测试记录；不是用户最终审查。');
    await save.click();
    await page.getByText(/此导出版本已有人工复核记录/).waitFor();
    assert.equal(await boxes.evaluateAll(es => es.filter(e => e.checked).length), 0);
    const record = (await json(prefix + '/delivery')).records[0];
    assert.equal(record.export_id, latest.id);
    const v = await json(prefix + '/visual');
    await json(prefix + '/visual/settings', 'PATCH', { revision: v.revision, style: 'ink', budget: 4 });
    await page.getByRole('button', { name: '重新检查', exact: true }).click();
    await page.getByText('制作状态已变，请先导出当前版本。', { exact: true }).waitFor();
    for (let i = 0; i < 5; i++) await boxes.nth(i).check();
    assert.equal(await save.isDisabled(), true);
    Object.assign(report, { passed: true, project_id: pid, all_checks_required: true, new_export_resets_checks: true, record_saved_with_export_id: true, changed_state_blocks_review: true });
    console.log(JSON.stringify(report));
  } finally { fs.writeFileSync(path.join(output, 'review-ui-report.json'), JSON.stringify(report, null, 2)); await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
