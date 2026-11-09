// Recheck character switching and asset layouts without any paid model calls.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const base = process.argv[2] || 'http://127.0.0.1:8000';
const output = path.resolve(__dirname, '../../data/verification/p1');
(async () => {
  const report = JSON.parse(fs.readFileSync(path.join(output, 'report.json')));
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await page.goto(base);
    await page.evaluate(pid => localStorage.setItem('storygal-project', pid), report.project_id);
    await page.reload();
    await page.getByRole('button', { name: /人物与审校/ }).click();
    await page.getByRole('tab', { name: /角色资产/ }).click();
    await page.getByRole('button', { name: '编辑角色 周瑜', exact: true }).click();
    assert.equal(await page.locator('.codex-import select').inputValue(), 'zhouyu');
    await page.getByRole('button', { name: '编辑角色 諸葛亮', exact: true }).click();
    assert.equal(await page.locator('.codex-import select').inputValue(), 'kongming');
    assert.equal(await page.getByLabel('合并目标').inputValue(), '');
    const widths = [];
    for (const width of [320, 375, 414, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({ path: path.join(output, `characters-${width}.png`), fullPage: true });
      widths.push(width);
    }
    const result = { passed: true, checked_at: new Date().toISOString(), project_id: report.project_id,
      character_switch_resets_candidate: true, merge_target_resets: true, asset_widths: widths };
    fs.writeFileSync(path.join(output, 'assets-ui-report.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
