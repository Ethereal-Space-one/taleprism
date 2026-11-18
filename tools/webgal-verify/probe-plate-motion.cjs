// Observe the supplied reader's real DOM and canvas. No mocks, play() calls,
// forced CSS/motion preferences or per-plate activation. Invoked only after
// screen_plates.py authenticates the reader envelope, runtime and inventory.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const [folder, chrome, output] = process.argv.slice(2);
const story = JSON.parse(
  fs.readFileSync(path.join(folder, "reader.json"), "utf8"),
);
const plates = story.config.illustrations || [];
const ids = plates.map((p) => p.id);
assert.equal(new Set(ids).size, ids.length, "Ambiguous plate identity");
const base = "http://127.0.0.1:38887/taleprism/";
const members = new Map([
  ["index.html", "text/html; charset=utf-8"],
  ["assets/reader.js", "application/javascript"],
  ["assets/reader.css", "text/css"],
]);
for (const asset of Object.values(story.media)) {
  const rel = asset.url.replace(/^\.\//, "");
  assert.match(rel, /^media\/[a-zA-Z0-9_.-]+$/);
  members.set(
    rel,
    {
      png: "image/png",
      jpg: "image/jpeg",
      jpeg: "image/jpeg",
      webp: "image/webp",
      wav: "audio/wav",
      mp3: "audio/mpeg",
      ogg: "audio/ogg",
      m4a: "audio/mp4",
    }[rel.split(".").pop()] || "application/octet-stream",
  );
}
async function inspect(browser, reduced) {
  const ctx = await browser.newContext({
    viewport: { width: 1130, height: 820 },
    reducedMotion: reduced ? "reduce" : "no-preference",
    offline: true,
    serviceWorkers: "block",
    acceptDownloads: false,
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await ctx.route("**/*", async (route) => {
    const url = route.request().url();
    const name = url.startsWith(base) ? url.slice(base.length) : "";
    if (route.request().method() !== "GET" || !members.has(name)) {
      errors.push("Request outside edition inventory");
      return route.abort();
    }
    await route.fulfill({
      body: fs.readFileSync(path.join(folder, name)),
      contentType: members.get(name),
    });
  });
  try {
    await page.goto(base + "index.html");
    await page.getByRole("button", { name: /^开始阅读/ }).click();
    const cards = page.locator("figure.reader-plate[data-illustration-id]");
    const dom = await cards.evaluateAll((xs) =>
      xs.map((x) => x.dataset.illustrationId),
    );
    assert.deepEqual(
      [...dom].sort(),
      [...ids].sort(),
      "Reader did not expose every finished plate",
    );
    const sc = page.locator(".reader-scroll"),
      box = await sc.boundingBox();
    assert.ok(box);
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.55);
    // Observe each render frame, including transient wrong-plate or reduced-motion
    // flashes outside the current sampling interval. Sample alpha, never text/audio.
    await page.evaluate(() => {
      const observations = new Map();
      window.__plateProbe = observations;
      function sample() {
        for (const c of document.querySelectorAll(
          "canvas.reader-inline-motion:not([hidden])",
        )) {
          const card = c.closest("figure[data-illustration-id]");
          if (!card || !c.width || !c.height) continue;
          const id = card.dataset.illustrationId;
          if (!observations.has(id))
            observations.set(id, { effects: new Set(), frames: new Set() });
          const row = observations.get(id);
          row.effects.add(c.dataset.motionEffect || "(unknown)");
          if (row.frames.size >= 3) continue;
          const d = c
            .getContext("2d")
            .getImageData(0, 0, c.width, c.height).data;
          let fp = 2166136261,
            n = 0;
          for (let i = 3; i < d.length; i += 4)
            if (d[i]) {
              n++;
              fp = Math.imul(fp ^ i, 16777619) ^ d[i];
            }
          if (n) row.frames.add(n + ":" + (fp >>> 0));
        }
        requestAnimationFrame(sample);
      }
      requestAnimationFrame(sample);
    });
    const markers = {};
    for (let i = 0; i < dom.length; i++) {
      const card = cards.nth(i),
        id = dom[i];
      let reached = false;
      for (let k = 0; k < 3000; k++) {
        const pos = await card.evaluate((el) => {
          const r = el
              .querySelector("button[data-illustration-anchor]")
              .getBoundingClientRect(),
            s = el.closest(".reader-scroll").getBoundingClientRect();
          const centre = (r.top + r.bottom) / 2;
          return {
            delta: centre - (s.top + s.height * 0.52),
            seen:
              Math.max(
                0,
                Math.min(r.bottom, s.bottom) - Math.max(r.top, s.top),
              ) / Math.min(s.height, r.height),
            h: s.height,
          };
        });
        if (pos.seen > 0.58) {
          reached = true;
          break;
        }
        await page.mouse.wheel(
          0,
          Math.sign(pos.delta) * Math.min(Math.abs(pos.delta), pos.h * 0.45),
        );
        await page.waitForTimeout(40);
      }
      assert.ok(
        reached,
        "Cannot bring actual plate into the reading viewport: " + id,
      );
      const img = card.locator("button[data-illustration-anchor] img");
      await img.evaluate(async (im) => {
        await im.decode();
        if (!im.naturalWidth || !im.naturalHeight)
          throw Error("Image failed to decode");
      });
      const marker = await card
        .locator("button[data-illustration-anchor]")
        .getAttribute("data-auto-motion");
      assert.ok(
        marker === null || marker === id,
        "Motion marker is bound to another plate",
      );
      markers[id] = marker !== null;
      if (!reduced && marker) {
        await page
          .waitForFunction(
            (id) => (window.__plateProbe.get(id)?.frames.size || 0) >= 2,
            id,
            { timeout: 5000 },
          )
          .catch(() => {
            throw Error(
              "Motion is marked eligible but two distinct nonempty frames were not observed: " +
                id,
            );
          });
      } else {
        // Wait through the reading dwell even on a plate expected to stay still.
        await page.waitForTimeout(1050);
      }
    }
    const pixels = await page.evaluate(() =>
      Object.fromEntries(
        [...window.__plateProbe].map(([id, r]) => [
          id,
          { effects: [...r.effects], frames: r.frames.size },
        ]),
      ),
    );
    assert.deepEqual(errors, []);
    assert.ok(
      Object.keys(pixels).every((id) => ids.includes(id)),
      "Unexpected canvas outside book",
    );
    return Object.fromEntries(
      ids.map((id) => {
        const item = pixels[id] || { effects: [], frames: 0 };
        if (!markers[id] || reduced)
          assert.equal(item.frames, 0, "Unexpected motion: " + id);
        else {
          assert.equal(item.effects.length, 1, "Ambiguous effect on " + id);
          assert.ok(item.frames >= 2, "No moving pixels: " + id);
        }
        return [id, { eligible: markers[id], ...item }];
      }),
    );
  } finally {
    await ctx.close();
  }
}
(async () => {
  const browser = await chromium.launch({
    executablePath: chrome,
    headless: true,
  });
  try {
    const normal = await inspect(browser, false),
      reduced = await inspect(browser, true);
    const result = {
      schema_version: 1,
      browser_version: browser.version(),
      observations: ids.map((plate_id) => ({
        plate_id,
        eligible_effect: normal[plate_id].eligible
          ? normal[plate_id].effects[0]
          : null,
        normal_frames: normal[plate_id].frames,
        reduced_frames: reduced[plate_id].frames,
      })),
    };
    fs.writeFileSync(output, JSON.stringify(result), { flag: "wx" });
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
