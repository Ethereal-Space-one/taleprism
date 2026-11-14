// Exercise the real audio hook with deterministic hook slots and an audio double.
// This verifies transitions/races, not browser decoding or audible output.
const assert = require("node:assert/strict");
const fs = require("node:fs"),
  os = require("node:os"),
  path = require("node:path");
const Module = require("node:module"),
  { spawnSync } = require("node:child_process");
const root = path.resolve(__dirname, "../.."),
  temp = fs.mkdtempSync(path.join(os.tmpdir(), "taleprism-reader-audio-"));
const originalLoad = Module._load,
  originalDocument = global.document;
(async () => {
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
        path.join(root, "frontend/src/reader/useDialogueAudio.ts"),
      ],
      { encoding: "utf8" },
    );
    assert.equal(compile.status, 0, compile.stdout + compile.stderr);
    const slots = [],
      effects = [],
      listeners = new Map();
    let index = 0;
    const react = {
      useRef(initial) {
        const i = index++;
        return (slots[i] ||= { current: initial });
      },
      useState(initial) {
        const i = index++;
        if (!(i in slots)) slots[i] = initial;
        return [
          slots[i],
          (value) => {
            slots[i] = typeof value === "function" ? value(slots[i]) : value;
          },
        ];
      },
      useCallback(fn, deps) {
        const i = index++,
          old = slots[i];
        if (!old || deps.some((d, n) => d !== old.deps[n]))
          slots[i] = { deps, fn };
        return slots[i].fn;
      },
      useEffect(fn, deps) {
        const i = index++,
          old = slots[i];
        if (!old || deps.some((d, n) => d !== old.deps[n])) {
          old?.cleanup?.();
          slots[i] = { deps, cleanup: fn() };
          effects.push(i);
        }
      },
    };
    global.document = {
      hidden: false,
      addEventListener: (name, fn) => listeners.set(name, fn),
      removeEventListener: (name) => listeners.delete(name),
    };
    Module._load = function (name, ...rest) {
      return name === "react" ? react : originalLoad.call(this, name, ...rest);
    };
    const { useDialogueAudio } = require(
      path.join(temp, "reader/useDialogueAudio.js"),
    );
    Module._load = originalLoad;
    const clips = [
      { take_id: "a", byte_start: 2, byte_end: 6 },
      { take_id: "b", byte_start: 7, byte_end: 12 },
    ];
    const data = {
      blocks: [
        { audio: clips },
        { audio: [{ take_id: "c", byte_start: 14, byte_end: 20 }] },
      ],
      media: {
        a: { url: "/a.wav" },
        b: { url: "/b.wav" },
        c: { url: "/c.wav" },
      },
    };
    const playCalls = [],
      rejects = [];
    const audio = {
      src: "",
      currentTime: 0,
      paused: true,
      ended: false,
      error: null,
      pause() {
        this.paused = true;
      },
      load() {
        this.ended = false;
        this.error = null;
      },
      removeAttribute() {
        this.src = "";
      },
      play() {
        this.paused = false;
        this.ended = false;
        playCalls.push(this.src);
        return new Promise((resolve, reject) => rejects.push(reject));
      },
    };
    let hook;
    function render() {
      index = 0;
      hook = useDialogueAudio(data);
      hook.element.current = audio;
      return hook;
    }
    function ended() {
      audio.ended = true;
      hook.ended();
      render();
    }
    render().play("a");
    render();
    assert.equal(hook.status, "playing");
    const oldReject = rejects[0];
    audio.currentTime = 1.25;
    hook.suspend();
    render();
    assert.equal(hook.status, "paused");
    assert.deepEqual(hook.point(), { id: "a", time: 1.25 });
    oldReject(new Error("old aborted play"));
    await Promise.resolve();
    render();
    assert.equal(
      hook.status,
      "paused",
      "late rejection must not overwrite pause",
    );
    hook.restore({ id: "b", time: 2 });
    render();
    assert.equal(hook.status, "paused");
    assert.equal(audio.paused, true);
    assert.equal(hook.current, "b");
    const before = playCalls.length;
    ended();
    assert.equal(playCalls.length, before, "return never resumes or queues");
    hook.play("a");
    render();
    hook.leave(new Set(["a", "b"]));
    render();
    assert.equal(
      hook.status,
      "playing",
      "natural anchor changes retain visible line",
    );
    audio.ended = false;
    hook.ended();
    render();
    assert.equal(hook.current, "a", "ignore stale ended from old source");
    ended();
    assert.equal(hook.current, "b", "explicit manual same-paragraph queue");
    hook.leave(new Set(["c"]));
    render();
    assert.equal(hook.current, null);
    assert.equal(audio.paused, true);
    hook.setAutomatic(true);
    render();
    let token = hook.revision();
    hook.autoAt(12, 16, new Set(["c"]), token);
    render();
    assert.equal(hook.current, "c");
    hook.leave(new Set(["c"]));
    render();
    assert.equal(hook.status, "playing");
    ended();
    assert.equal(hook.current, null);
    token = hook.revision();
    hook.autoAt(12, 16, new Set(["c"]), token);
    render();
    assert.equal(hook.current, null, "auto never repeats heard line");
    // A delayed scroll settle cannot start audio after explicit stop/navigation.
    token = hook.revision();
    hook.stop();
    render();
    const calls = playCalls.length;
    hook.autoAt(0, 4, new Set(["a"]), token);
    render();
    assert.equal(playCalls.length, calls);
    hook.play("a");
    render();
    const rejected = rejects.at(-1);
    rejected(new Error("blocked playback"));
    await Promise.resolve();
    render();
    assert.equal(hook.status, "failed");
    assert.match(hook.notice, /正文可以继续阅读/);
    hook.resume();
    render();
    assert.equal(hook.status, "playing");
    global.document.hidden = true;
    listeners.get("visibilitychange")();
    render();
    assert.equal(hook.status, "paused");
    const afterHidden = playCalls.length;
    ended();
    assert.equal(playCalls.length, afterHidden);
    hook.restore(null);
    render();
    assert.equal(hook.current, null);
    assert.equal(audio.src, "");
    for (const i of effects) slots[i]?.cleanup?.();
    console.log(
      "Reader audio hook: natural visibility, manual queue, paused return, no auto-repeat, stale events/promises and hidden-page suspension passed.",
    );
  } finally {
    Module._load = originalLoad;
    global.document = originalDocument;
    fs.rmSync(temp, { recursive: true, force: true });
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
