// Local, synthetic, no network/model credentials. Requires a built frontend and the backend venv.
// TALEPRISM_CHROMIUM=/path/to/chromium node tools/webgal-verify/plate-screening-workbench.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const net = require("node:net");
const { spawn, execFileSync } = require("node:child_process");
const { chromium } = require("playwright");
const ROOT = path.resolve(__dirname, "../.."),
  TMP = fs.mkdtempSync(path.join(os.tmpdir(), "plate-screening-ui-"));
const py =
  process.env.TALEPRISM_PYTHON || path.join(ROOT, "backend/.venv/bin/python");
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
const wait = async (fn, label) => {
  for (let i = 0; i < 160; i++) {
    if (await fn()) return;
    await sleep(100);
  }
  throw Error("Timed out: " + label);
};
async function port() {
  const s = net.createServer();
  await new Promise((r) => s.listen(0, "127.0.0.1", r));
  const p = s.address().port;
  await new Promise((r) => s.close(r));
  return p;
}
(async () => {
  let server, browser;
  try {
    const p = await port(),
      base = "http://127.0.0.1:" + p,
      raw = "灯仍亮着。\n圆形水面反射微光。\n末段保留沉默。";
    assert(
      fs.existsSync(path.join(ROOT, "frontend/dist/index.html")),
      "build the frontend first",
    );
    const childEnv = {
      ...process.env,
      STORYGAL_DATA_DIR: TMP,
      PYTHONPATH: path.join(ROOT, "backend/src"),
      OPENAI_API_KEY: "",
      DEEPSEEK_API_KEY: "",
    };
    server = spawn(
      py,
      [
        "-m",
        "uvicorn",
        "storygal.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        String(p),
      ],
      { cwd: ROOT, env: childEnv, stdio: "ignore" },
    );
    await wait(
      async () =>
        fetch(base + "/api/health")
          .then((r) => r.ok)
          .catch(() => false),
      "local workbench",
    );
    browser = await chromium.launch({
      executablePath: process.env.TALEPRISM_CHROMIUM || undefined,
    });
    const ctx = await browser.newContext({
        viewport: { width: 1000, height: 770 },
      }),
      page = await ctx.newPage();
    let external = [];
    await ctx.route("**/*", async (route) => {
      const u = route.request().url();
      if (u.startsWith(base) || !/^https?:/.test(u)) return route.continue();
      external.push(u);
      return route.abort();
    });
    async function api(url, opts) {
      const r = await fetch(base + url, opts);
      assert(
        r.ok,
        "" + r.status + " " + url + " " + (!r.ok ? await r.text() : ""),
      );
      return r.json();
    }
    const form = new FormData();
    form.set("file", new Blob([raw]), "光斑.txt");
    form.set("rights_status", "owned");
    form.set("single_plate_studio", "true");
    const project = await api("/api/projects", { method: "POST", body: form }),
      prefix = "/api/projects/" + project.id;
    const img = path.join(TMP, "synthetic.png");
    execFileSync(py, [
      "-c",
      "from PIL import Image,ImageDraw; import sys; im=Image.new('RGB',(128,80),'#203344'); ImageDraw.Draw(im).ellipse((40,24,88,55),fill='#c6ab74'); im.save(sys.argv[1])",
      img,
    ]);
    page.setDefaultTimeout(12000);
    await page.goto(base + "/?studio=" + project.id + "&lane=art");
    await page.getByLabel("插图文件").setInputFiles(img);
    await page.getByLabel("图片来源与许可").fill("合成测试图片");
    await page
      .getByRole("button", { name: "上传为候选图", exact: true })
      .click();
    await page.getByRole("button", { name: "接受这张底图" }).click();
    await page.getByLabel("放在此段之后").selectOption({ index: 2 });
    await page.getByRole("button", { name: /放置静图/ }).click();
    let sec = page.getByRole("region", { name: "逐幅动静审图" });
    await sec.getByText(/共 1 幅 · 未审 1/).waitFor();
    const before = await api(prefix + "/reader");
    assert.equal(before.config.illustrations[0].motion, null);
    // No decisions gate the regular reader export.
    await page
      .getByRole("button", { name: "导出独立阅读器", exact: true })
      .click();
    await page.getByRole("link", { name: "下载阅读器 ↓" }).waitFor();
    await sec.getByRole("button", { name: /逐幅动静审图/ }).click();
    assert.equal(
      await sec.getByRole("img").evaluate((e) => e.naturalWidth),
      128,
    );
    assert.equal(
      await sec.locator("blockquote").innerText(),
      "圆形水面反射微光。",
    );
    await sec.getByLabel("动静选择").selectOption("motion");
    await sec.getByLabel("候选动效类型").selectOption("wave-impact-backwash");
    const answers = [
      "圆形水面反射微光",
      "中央椭圆浅色，无浪线。",
      "仅作岸浪候选，需后续导演。",
      "保持静止的深色背景。",
      "合成段落只留一处反光。",
    ];
    for (let i = 0; i < answers.length; i++)
      await sec.locator("textarea").nth(i).fill(answers[i]);
    await sec.getByRole("button", { name: "保存本幅判断" }).click();
    await sec.getByText("已保存本幅判断。读者版和动效配置均未修改。").waitFor();
    const first = await api(prefix + "/plate-screening");
    assert(first.report.ok);
    assert.equal(first.report.counts.active, 0);
    assert.equal(
      first.worksheet.plates[0].proposed_effect,
      "wave-impact-backwash",
    );
    assert.deepEqual((await api(prefix + "/reader")).config, before.config);
    const download = page.waitForEvent("download");
    await sec.getByRole("button", { name: /下载私有审图单/ }).click();
    const worksheetFile = path.join(TMP, "worksheet.json");
    await (await download).saveAs(worksheetFile);
    assert.deepEqual(
      JSON.parse(fs.readFileSync(worksheetFile)),
      first.worksheet,
    );
    await page.goto(base + "/?project=" + project.id);
    await page
      .getByRole("navigation", { name: "工作台视图" })
      .getByRole("button", { name: "交付检查" })
      .click();
    const delivery = page.getByRole("region", { name: "交付检查" });
    await delivery.getByRole("button", { name: "保存人工复核记录" }).waitFor();
    const cbs = delivery.locator(".delivery-review input[type=checkbox]");
    for (let i = 0; i < 5; i++) await cbs.nth(i).check();
    await delivery.getByRole("button", { name: "保存人工复核记录" }).click();
    await delivery.getByText(/此导出版本已有人工复核记录/).waitFor();
    sec = delivery.getByRole("region", { name: "逐幅动静审图" });
    await sec.getByRole("button", { name: /逐幅动静审图/ }).click();
    await sec.getByLabel("动静选择").selectOption("deferred");
    await sec
      .getByLabel("哪些部分动或不动？")
      .fill("反光收拢目前不支持，保留静图。");
    await sec.getByRole("button", { name: "保存本幅判断" }).click();
    await delivery.getByText(/有历史人工记录/).waitFor();
    assert.equal(
      await delivery.getByText(/此导出版本已有人工复核记录/).count(),
      0,
    );
    assert.equal((await api(prefix + "/delivery")).current_signoff, null);
    assert.deepEqual((await api(prefix + "/reader")).config, before.config);
    const corrected = await api(prefix + "/plate-screening");
    fs.writeFileSync(worksheetFile, JSON.stringify(corrected.worksheet));
    const r = await fetch(base + prefix + "/bundle");
    assert(r.ok);
    const restore = new FormData();
    restore.set("file", new Blob([await r.arrayBuffer()]), "draft.zip");
    const cloned = await api("/api/project-bundles", {
      method: "POST",
      body: restore,
    });
    await page.goto(base + "/?project=" + cloned.id);
    await page
      .getByRole("navigation", { name: "工作台视图" })
      .getByRole("button", { name: "独立阅读器", exact: true })
      .click();
    sec = page.getByRole("region", { name: "逐幅动静审图" });
    await sec.getByText(/共 1 幅 · 未审 1/).waitFor();
    await sec.getByRole("button", { name: /逐幅动静审图/ }).click();
    page.once("dialog", (d) => d.dismiss());
    await sec.getByLabel("导入私有审图单 JSON").setInputFiles(worksheetFile);
    const clonePrefix = "/api/projects/" + cloned.id;
    assert.equal((await api(clonePrefix + "/plate-screening")).revision, 0);
    page.once("dialog", (d) => d.accept());
    await sec.getByLabel("导入私有审图单 JSON").setInputFiles(worksheetFile);
    await sec.getByText(/已核对全部绑定并合并私有审图单/).waitFor();
    assert.equal(
      (await api(clonePrefix + "/plate-screening")).report.counts.deferred,
      1,
    );
    assert.deepEqual(external, []);
    console.log(
      "PASS native Chromium: upload → accept → place actual image; draft export before screening; bound candidate no motion; private download; signature invalidated by editorial-only edit; exact-restore import requires consent.",
    );
  } finally {
    if (browser) await browser.close();
    if (server) server.kill();
    fs.rmSync(TMP, { recursive: true, force: true });
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
