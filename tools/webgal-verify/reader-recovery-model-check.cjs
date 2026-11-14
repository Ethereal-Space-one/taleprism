const assert = require("node:assert/strict");
const fs = require("node:fs"),
  os = require("node:os"),
  path = require("node:path");
const { spawnSync } = require("node:child_process");
const root = path.resolve(__dirname, "../.."),
  temp = fs.mkdtempSync(path.join(os.tmpdir(), "taleprism-reader-recovery-"));
try {
  const compile = spawnSync(
    path.join(root, "frontend/node_modules/.bin/tsc"),
    [
      "--module",
      "commonjs",
      "--target",
      "ES2022",
      "--skipLibCheck",
      "--outDir",
      temp,
      ...["model", "position", "readingSession", "imageRecovery"].map((name) =>
        path.join(root, `frontend/src/reader/${name}.ts`),
      ),
    ],
    { encoding: "utf8" },
  );
  assert.equal(compile.status, 0, compile.stdout + compile.stderr);
  const m = require(path.join(temp, "reader/model.js")),
    session = require(path.join(temp, "reader/readingSession.js")),
    images = require(path.join(temp, "reader/imageRecovery.js"));
  const blocks = ["甲😀乙", "第二段原文", "第三段原文"].map((text, i, all) => {
    const byte_start = all.slice(0, i).reduce((n, t) => n + m.byteLength(t), 0);
    return {
      id: `b${i}`,
      byte_start,
      byte_end: byte_start + m.byteLength(text),
      text,
      audio: [],
      runs: [],
      heading: false,
    };
  });
  const data = {
    blocks,
    config: {
      scenes: [],
      illustrations: [
        {
          id: "plate-a",
          image_asset_id: "image-a",
          after_byte: blocks[0].byte_end,
        },
      ],
    },
  };
  const old = {
    byte: blocks[0].byte_end - 3,
    offset: 0,
    plate: "plate-a",
    imageOffset: 0.62,
  };
  const migrated = m.readRecord(
    data,
    JSON.stringify({
      version: 2,
      resume: old,
      marks: [{ id: "m", text: "旧书签", position: old }, null],
      preferences: { size: 25 },
    }),
  );
  assert.equal(migrated.resume.imageAsset, "image-a");
  assert.equal(migrated.resume.imageOffset, 0.62);
  assert.equal(migrated.marks.length, 1);
  assert.equal(migrated.preferences.size, 25);
  const positions = require(path.join(temp, "reader/position.js"));
  let artTop = 100,
    artHeight = 200;
  const art = {
    getBoundingClientRect: () => ({
      top: artTop - viewport.scrollTop,
      height: artHeight,
    }),
  };
  const figure = {
    dataset: {
      illustrationId: "plate-a",
      imageAsset: "image-a",
      sourceByte: String(blocks[0].byte_end - 3),
    },
    querySelector: () => art,
    getBoundingClientRect: () => ({
      top: artTop - viewport.scrollTop,
      bottom: artTop - viewport.scrollTop + artHeight + 50,
    }),
  };
  const viewport = {
    scrollTop: 0,
    getBoundingClientRect: () => ({ top: 10, bottom: 810 }),
    querySelectorAll: () => [figure],
    focus: () => {
      viewport.focused = true;
    },
  };
  positions.restorePosition(
    viewport,
    { ...migrated.resume, imageOffset: 0.5 },
    true,
  );
  assert.equal(viewport.scrollTop, 166);
  assert.equal(viewport.focused, true);
  assert.equal(
    positions.capturePosition(viewport).imageOffset,
    0.5,
    "offset is in actual art, not its caption",
  );
  artTop = 250;
  artHeight = 400;
  positions.restorePosition(viewport, { ...migrated.resume, imageOffset: 0.5 });
  assert.equal(
    positions.capturePosition(viewport).imageOffset,
    0.5,
    "responsive reflow restores normalized internal point",
  );
  const moved = {
    ...data,
    config: {
      ...data.config,
      illustrations: [
        {
          id: "renamed",
          image_asset_id: "image-a",
          after_byte: blocks[2].byte_end,
        },
      ],
    },
  };
  const recovered = m.validPosition(moved, migrated.resume);
  assert.equal(recovered.plate, "renamed");
  assert.equal(recovered.byte, blocks[2].byte_end - 3);
  assert.equal(recovered.imageOffset, 0.62);
  assert.equal(
    m.validPosition(moved, { ...recovered, imageOffset: Infinity }).imageOffset,
    0,
  );
  assert.ok(
    m.sameBookmarkPosition(recovered, { ...recovered, imageOffset: 0.63 }),
  );
  assert.ok(
    !m.sameBookmarkPosition(recovered, { ...recovered, imageOffset: 0.85 }),
  );
  assert.ok(
    !m.sameBookmarkPosition(recovered, { byte: recovered.byte, offset: 0 }),
  );
  let nav = {
    view: recovered,
    resume: recovered,
    furthest: recovered.byte,
    visits: [],
  };
  nav = m.navigationReducer(nav, {
    type: "visit",
    position: { byte: 0, offset: 0 },
  });
  nav = m.navigationReducer(nav, {
    type: "scroll",
    position: { byte: 3, offset: 0 },
  });
  assert.deepEqual(nav.resume, recovered);
  nav = m.navigationReducer(nav, {
    type: "restore",
    position: recovered,
    visits: [],
  });
  assert.equal(nav.view.imageOffset, 0.62);
  const legacy = m.readRecord(
    data,
    JSON.stringify({ at: 3, size: 24, marks: [] }),
  );
  assert.equal(legacy.resume.byte, 3);
  assert.equal(legacy.preferences.size, 24);
  assert.equal(m.readRecord(data, "{bad").resume.byte, 0);
  let gesture = session.followScroll(null, 0, 3, 80);
  gesture = session.followScroll(gesture, 3, 10, 90);
  assert.equal(gesture.from, 0);
  assert.equal(session.isReadingStep(gesture, 800), true);
  for (let i = 0; i < 6; i++)
    gesture = session.followScroll(gesture, 10 + i, 11 + i, 90);
  assert.equal(
    session.isReadingStep(gesture, 800),
    false,
    "multi-event fast skip is not natural reading",
  );
  gesture = session.followScroll(null, 0, 10, 90);
  gesture = session.followScroll(gesture, 10, 3, -50);
  gesture = session.followScroll(gesture, 3, 12, 90);
  assert.equal(
    session.isReadingStep(gesture, 800),
    false,
    "a reversed gesture is not forward reading",
  );
  const clips = [
    { take_id: "a", byte_start: 2, byte_end: 6 },
    { take_id: "b", byte_start: 7, byte_end: 12 },
    { take_id: "c", byte_start: 13, byte_end: 18 },
  ];
  assert.equal(
    session.automaticClip(clips, new Set(), new Set(["b"]), 0, 10).take_id,
    "b",
    "never play an offscreen crossed line",
  );
  assert.equal(
    session.automaticClip(clips, new Set(["b"]), new Set(["a", "b"]), 6, 10),
    undefined,
    "never auto-repeat heard lines",
  );
  assert.equal(
    session.nextDialogue(clips, "a", new Set(["a"])),
    null,
    "do not queue offscreen audio",
  );
  assert.equal(
    session.nextDialogue(clips, "a", new Set(["b"]), new Set(["b"])),
    null,
    "automatic queue skips heard audio",
  );
  assert.equal(
    session.nextDialogue(clips, "a", null).take_id,
    "b",
    "explicit manual group can continue",
  );
  let requests = images.imageRecoveryReducer(
    {},
    { type: "failed", id: "art", attempt: 0 },
  );
  assert.equal(
    images.imageRecoveryReducer(requests, {
      type: "loaded",
      id: "art",
      attempt: 0,
    }),
    requests,
    "a late load from another instance cannot clear failure or start an automatic request loop",
  );
  requests = images.imageRecoveryReducer(requests, {
    type: "retry",
    id: "art",
  });
  assert.deepEqual(requests.art, { attempt: 1, status: "loading" });
  assert.equal(
    images.imageRecoveryReducer(requests, { type: "retry", id: "art" }),
    requests,
    "double click cannot start concurrent retry",
  );
  assert.equal(
    images.imageRecoveryReducer(requests, {
      type: "failed",
      id: "art",
      attempt: 0,
    }),
    requests,
    "ignore stale error",
  );
  requests = images.imageRecoveryReducer(requests, {
    type: "loaded",
    id: "art",
    attempt: 1,
  });
  assert.equal(requests.art.status, "ready");
  assert.equal(
    images.imageRecoveryReducer(requests, { type: "retry", id: "art" }),
    requests,
  );
  for (let i = 1; i < images.MAX_IMAGE_RETRIES; i++) {
    requests = images.imageRecoveryReducer(requests, {
      type: "failed",
      id: "art",
      attempt: i,
    });
    requests = images.imageRecoveryReducer(requests, {
      type: "retry",
      id: "art",
    });
  }
  requests = images.imageRecoveryReducer(requests, {
    type: "failed",
    id: "art",
    attempt: images.MAX_IMAGE_RETRIES,
  });
  assert.equal(
    images.imageRecoveryReducer(requests, { type: "retry", id: "art" }),
    requests,
    "retry bound enforced in state, not only UI",
  );
  assert.equal(
    images.imageRetryUrl("/media/a.png#view", 2),
    "/media/a.png?taleprism_retry=2#view",
  );
  assert.equal(
    images.imageRetryUrl("/media/a.png?x=1", 1),
    "/media/a.png?x=1&taleprism_retry=1",
  );
  assert.equal(
    images.imageRetryUrl("https://external.example/a?signature=private", 2),
    "https://external.example/a?signature=private",
  );
  console.log(
    "Reader recovery: gesture/audio selection, illustration migration/navigation, and bounded request transitions passed.",
  );
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}
