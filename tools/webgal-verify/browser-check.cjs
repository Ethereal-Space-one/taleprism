/* End-to-end checks against the real UI and bundled WebGAL, no mocked renderer. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const base = (process.argv[2] || 'http://127.0.0.1:8000').replace(/\/$/, '');
const root = path.resolve(__dirname, '../..');
const output = path.join(root, 'data/verification');
const selector = '#textBoxMain span[id] > span';
fs.mkdirSync(output, { recursive: true });

async function getJson(request, url) {
  const response = await request.get(base + url);
  assert.equal(response.status(), 200, url);
  return response.json();
}

async function exportUI(page) {
  await page.getByRole('button', { name: '导出 WebGAL' }).click();
  const link = page.getByRole('link', { name: '打开播放 ↗' });
  await link.waitFor({ timeout: 60000 });
  return link.getAttribute('href');
}

async function checkEngine(browser, url, label, report) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {
    if (response.status() >= 400 && !/\/lib\/live2d/.test(response.url()))
      errors.push(`${response.status()} ${response.url()}`);
  });
  try {
    const manifestUrl = url.replace(/index\.html$/, 'storygal-manifest.json');
    const manifest = await getJson(page.request, manifestUrl);
    const expected = manifest.units;
    await page.goto(base + url);
    await page.locator('.html-body__title-enter').click();
    await page.locator('.html-body__title-enter').waitFor({ state: 'hidden' });
    const language = page.getByText('简体中文', { exact: true });
    if (await language.isVisible()) await language.click();
    await page.getByText('开始游戏', { exact: true }).first().locator('..').click();
    await page.locator('#textBoxMain').waitFor();
    // Let the stock engine's title-to-stage entrance finish before judging visibility.
    await page.waitForTimeout(1800);
    let checked = 0;
    for (const unit of expected) {
      await page.waitForFunction(({ selector, text }) =>
        Array.from(document.querySelectorAll(selector)).map(e => e.firstChild.textContent).join('') === text,
        { selector, text: unit.text }, { timeout: 10000 });
      if (await page.locator('#textBoxMain .Textelement_start').count()) {
        await page.mouse.click(700, 300); // First click settles typewriter animation.
        await page.waitForFunction(() => !document.querySelector('#textBoxMain .Textelement_start'));
      }
      const actual = await page.locator(selector).evaluateAll(nodes => nodes.map(e => e.firstChild.textContent).join(''));
      assert.equal(actual, unit.text, `${label} frame ${unit.id}`);
      const clipped = await page.locator(selector).evaluateAll(nodes => nodes.filter(e => {
        const outer = e.children[0];
        const rect = outer.getBoundingClientRect();
        const frame = e.closest('#textBoxMain').lastElementChild.getBoundingClientRect();
        return rect.left < frame.left - 2 || rect.right > frame.right + 2 || rect.top < frame.top - 2 || rect.bottom > frame.bottom + 2;
      }).map(e => e.firstChild.textContent));
      assert.deepEqual(clipped, [], `${label} frame ${unit.id}: clipped text`);
      await page.waitForFunction(selector => Array.from(document.querySelectorAll(selector)).every(e => {
        let opacity = 1;
        for (let node = e.children[0]; node; node = node.parentElement) {
          const style = getComputedStyle(node);
          if (style.display === 'none' || style.visibility === 'hidden') return false;
          opacity *= Number(style.opacity);
        }
        return opacity > 0.9;
      }), selector, { timeout: 5000 });
      checked++;
      if (unit.id === 1) await page.screenshot({ path: path.join(output, `${label}-playing.png`) });
      await page.mouse.click(700, 300); // Second click advances to the next original unit.
      if (checked % 40 === 0) console.log(`${label}: ${checked}/${expected.length} frames checked`);
    }
    await page.waitForFunction(() => !document.querySelector('#textBoxMain'));
    assert.deepEqual(errors, [], `${label}: browser/resource errors`);
    report.playback.push({ label, project_id: manifest.project.id, export_url: url,
      units: checked, visible_text_equal: true, no_clipping: true, reached_end: true, errors });
    console.log(`${label}: all ${checked} frames passed`);
  } finally { await page.close(); }
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const report = { checked_at: new Date().toISOString(), base, ui: [], playback: [], passed: false };
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const uiErrors = [];
    page.on('pageerror', e => uiErrors.push(e.message));
    await page.goto(base);
    await page.evaluate(() => localStorage.removeItem('storygal-project'));
    await page.reload();
    await page.getByRole('button', { name: '试用赤壁样例 →' }).click();
    await page.getByRole('heading', { name: '原文', exact: true }).waitFor();
    const first = await page.getByTestId('unit-text').innerText();
    await page.getByRole('button', { name: '下一框' }).click();
    assert.notEqual(await page.getByTestId('unit-text').innerText(), first);
    await page.keyboard.press('ArrowLeft');
    assert.equal(await page.getByTestId('unit-text').innerText(), first);
    await page.getByRole('button', { name: '校验原文', exact: true }).click();
    await page.getByRole('button', { name: '✓ 原文校验通过' }).waitFor();
    const chibi = await exportUI(page);
    await page.screenshot({ path: path.join(output, 'workbench-desktop.png'), fullPage: true });
    for (const width of [320, 375, 414, 768]) {
      await page.setViewportSize({ width, height: 950 });
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      assert.equal(overflow, false, `horizontal overflow at ${width}px`);
      await page.screenshot({ path: path.join(output, `workbench-${width}.png`), fullPage: true });
      report.ui.push({ viewport: width, no_horizontal_overflow: true });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole('button', { name: '导入新文本' }).click();
    await page.getByLabel('TXT 文件').setInputFiles(path.join(root, 'samples/special-characters.txt'));
    await page.getByLabel('文本权利状态').selectOption('local_test');
    await page.getByRole('button', { name: '导入并预览' }).click();
    await page.getByRole('heading', { name: 'special-characters', exact: true }).waitFor();
    const special = await exportUI(page);
    const download = await page.getByRole('link', { name: '下载工程 ↓' }).getAttribute('href');
    const zip = await page.request.get(base + download);
    assert.equal(zip.status(), 200);
    assert.ok((await zip.body()).length > 10000);
    assert.deepEqual(uiErrors, []);
    report.ui.push({ import: true, sample: true, pagination: true, keyboard: true, verify: true, export: true, download: true, errors: uiErrors });
    await page.getByRole('button', { name: /三國演義_第049-050回_赤壁/ }).first().click();
    await checkEngine(browser, chibi, 'chibi', report);
    await checkEngine(browser, special, 'special', report);
    report.passed = true;
  } catch (error) {
    report.error = String(error.stack || error);
    throw error;
  } finally {
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
