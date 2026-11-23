// Real built workbench preview AND exported file:// reader. Entirely local; synthetic prose.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const net = require("node:net");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { spawn } = require("node:child_process");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "../..");
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "tale-echo-"));
const source =
  "😀纸船上写着「稍候」。\r\n\r\n风把灯吹灭。\n　她终于放开了船。\n水声还在。𠮷";
const fold = {
  earlier: { paragraph: 1, quote: "「稍候」" },
  later: { paragraph: 3, quote: "放开了船" },
};
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
let server, browser;
async function main() {
  const port = await new Promise((done) => {
    const s = net.createServer().listen(0, "127.0.0.1", () => {
      const port = s.address().port;
      s.close(() => done(port));
    });
  });
  const origin = "http://127.0.0.1:" + port;
  server = spawn(
    process.env.BACKEND_PYTHON || path.join(root, "backend/.venv/bin/python"),
    [
      "-m",
      "uvicorn",
      "storygal.app:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--log-level",
      "warning",
    ],
    {
      cwd: root,
      env: {
        ...process.env,
        STORYGAL_DATA_DIR: temp,
        PYTHONPATH: path.join(root, "backend/src"),
      },
      stdio: ["ignore", "ignore", "inherit"],
    },
  );
  for (let n = 0; n < 100; n++) {
    try {
      if ((await fetch(origin + "/api/health")).ok) break;
    } catch {}
    await sleep(100);
  }
  browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || "/usr/bin/chromium",
  });
  const setup = await browser.newContext({ baseURL: origin });
  const api = setup.request;
  const created = await api.post("/api/projects", {
    multipart: {
      rights_status: "owned",
      file: {
        name: "纸船.txt",
        buffer: Buffer.from(source),
        mimeType: "text/plain",
      },
    },
  });
  assert.equal(created.status(), 201);
  const { id } = await created.json();
  const base = "/api/projects/" + id;
  const reader = await (await api.get(base + "/reader")).json();
  assert(
    (
      await api.patch(base + "/reader", {
        data: { ...reader.config, revision: reader.revision, echo_fold: fold },
      })
    ).ok(),
  );
  assert((await api.post(base + "/reader/exports")).ok());
  let job;
  for (let n = 0; n < 80; n++) {
    job = (await (await api.get(base + "/jobs")).json())[0];
    if (job?.state === "completed" || job?.state === "failed") break;
    await sleep(100);
  }
  assert.equal(job.state, "completed", JSON.stringify(job));
  const exported = path.join(
    temp,
    "projects",
    id,
    "exports",
    job.id,
    "index.html",
  );
  assert(fs.existsSync(exported));
  for (const [url, width] of [
    [origin + "/read/" + id, 960],
    [pathToFileURL(exported).href, 360],
  ]) {
    const localFile = url.startsWith("file:");
    const ctx = await browser.newContext({
      viewport: { width, height: 820 },
      offline: localFile,
    });
    const errors = [],
      external = [];
    await ctx.route(/^https?:/, (r) => {
      if (localFile || new URL(r.request().url()).origin !== origin) {
        external.push(r.request().url());
        return r.abort();
      }
      return r.continue();
    });
    const p = await ctx.newPage();
    p.on("pageerror", (e) => errors.push(e.message));
    p.setDefaultTimeout(12000);
    await p.goto(url);
    // Legacy manual-disclosure contract, selected explicitly in v0.9.
    await p.getByRole("button", { name: "安静阅读", exact: true }).click();
    const echo = p.locator("details.reader-echo-fold"),
      quote = echo.locator("blockquote");
    await echo.waitFor();
    assert(!(await echo.evaluate((el) => el.open)));
    assert.equal(await quote.count(), 0);
    assert.equal(
      await echo.evaluate((el) =>
        el.previousElementSibling
          .querySelector(".reader-paragraph-text")
          .textContent.trim(),
      ),
      "她终于放开了船。",
    );
    assert.equal(
      await echo.evaluate(
        (el) =>
          el.nextElementSibling.querySelector(".reader-paragraph-text")
            .textContent,
      ),
      "水声还在。𠮷",
    );
    assert.equal(await echo.locator("[data-source-start]").count(), 0);
    const position = await p
      .locator(".reader-root")
      .getAttribute("data-resume-byte");
    const historySize = await p.evaluate(() => history.length);
    const summary = echo.locator("summary");
    await summary.focus();
    await summary.press("Enter");
    await quote.waitFor();
    assert.equal(await quote.textContent(), fold.earlier.quote);
    assert.match(await echo.innerText(), /前文原句 · 第 1 段/);
    assert.equal(await p.evaluate(() => history.length), historySize);
    assert.equal(
      await p.locator(".reader-root").getAttribute("data-resume-byte"),
      position,
    );
    assert(await p.locator("audio").evaluate((a) => a.paused));
    // Native copy event while the selected range crosses the open fold.
    const copyAcrossFold = (inset) =>
      p.evaluate((inset) => {
        const spans = document.querySelectorAll(
          ".reader-prose [data-source-start]",
        );
        const first = spans[0].firstChild,
          last = [...spans].at(-1).firstChild;
        const range = new Range();
        range.setStart(first, inset);
        range.setEnd(last, last.length - inset);
        const sel = getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        const dt = new DataTransfer();
        document.dispatchEvent(
          new ClipboardEvent("copy", {
            bubbles: true,
            cancelable: true,
            clipboardData: dt,
          }),
        );
        sel.removeAllRanges();
        return dt.getData("text/plain");
      }, inset);
    assert.equal(await copyAcrossFold(0), source);
    assert.equal(
      await copyAcrossFold(1),
      source,
      "DOM Range endpoints inside emoji/CJK supplementary characters preserve the original selection and gaps",
    );
    await summary.press("Space");
    await quote.waitFor({ state: "hidden" });
    await p.getByRole("button", { name: "阅读工具", exact: true }).click();
    await p.getByRole("button", { name: "搜索", exact: true }).click();
    await p.getByRole("checkbox", { name: "精确匹配" }).check();
    await p.getByLabel("查找原文").fill(fold.earlier.quote);
    const results = p.locator(".reader-search .reader-results button");
    await results.first().waitFor();
    assert.equal(await results.count(), 1);
    await p.getByRole("button", { name: "关闭面板" }).click();
    await p.locator("dialog").waitFor({ state: "hidden" });
    await p.getByRole("button", { name: "设置", exact: true }).click();
    await p.getByRole("button", { name: "隐藏回声折页" }).click();
    await p.getByRole("button", { name: "关闭面板" }).click();
    await p.locator("dialog").waitFor({ state: "hidden" });
    assert.equal(await echo.count(), 0);
    await p.reload();
    await p.getByRole("button", { name: /开始阅读|继续阅读/ }).click();
    assert.equal(await echo.count(), 0);
    assert.equal(await p.locator(".reader-paragraph-text").count(), 4);
    assert(
      await p.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      "PASS " +
        (localFile ? "offline portable file:// 360px" : "preview 960px") +
        ": after later paragraph, keyboard, exact original copy/search, stable progress, quiet reading, persistent opt-out",
    );
    await ctx.close();
  }
}
main()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(async () => {
    await browser?.close();
    if (server && server.exitCode === null) {
      const exited = new Promise((done) => server.once("exit", done));
      server.kill();
      await exited;
    }
    fs.rmSync(temp, { recursive: true, force: true });
  });
