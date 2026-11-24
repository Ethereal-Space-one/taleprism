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
      useMemo(fn, deps) {
        const i = index++, old = slots[i];
        if (!old || deps.some((d, n) => d !== old.deps[n])) slots[i] = { deps, value: fn() };
        return slots[i].value;
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
        { byte_start: 0, audio: clips, narration: { id: "n", duration: 2, label: "段落朗读" } },
        { byte_start: 13, audio: [{ take_id: "c", byte_start: 14, byte_end: 20 }], soundscape: { id: "s", duration: 12 } },
        { byte_start: 28, audio: [], soundscape: { id: "w", duration: 12 } },
        { byte_start: 40, audio: [] },
      ],
      media: {
        n: { url: "/narration.wav" },
        s: { url: "/pencil.wav" },
        w: { url: "/wind.wav" },
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
    // Explicit paragraph readings share the single output but never join dialogue queues.
    global.document.hidden = false; listeners.get("visibilitychange")();
    hook.stop(); render(); hook.setAutomatic(true); render();
    const idleCount=playCalls.length;
    hook.autoAt(0,6,new Set(["n"]),hook.revision()); render();
    hook.play("n",0,"automatic"); render();
    assert.equal(playCalls.length,idleCount,"narration is never automatic");
    hook.play("n"); render(); assert.equal(hook.current,"n");
    audio.currentTime=.65; hook.suspend(); render();
    assert.equal(hook.point().time,.65); hook.autoAt(0,6,new Set(["a"]),hook.revision()); render();
    assert.equal(hook.current,"n","paused passage not displaced by another cue");
    hook.resume(); render(); assert.equal(hook.current,"n"); assert.equal(audio.currentTime,.65);
    hook.leave(new Set(["n"])); render(); assert.equal(hook.status,"playing");
    const whileNarrated=playCalls.length; ended();
    assert.equal(hook.current,null); assert.equal(playCalls.length,whileNarrated,"passage end never queues dialogue");
    hook.restore({id:"n",time:.5}); render(); assert.equal(hook.status,"paused");
    hook.resume(); render(); hook.leave(new Set(["a"])); render(); assert.equal(hook.current,null);
    hook.play("n"); render(); const oldNarrationReject=rejects.at(-1);
    hook.play("a"); render(); oldNarrationReject(new Error("late narration failure")); await Promise.resolve(); render();
    assert.equal(hook.current,"a"); assert.equal(hook.status,"playing","stale narration cannot break dialogue");
    // Creative sound uses the actual accepted source. No priming asset, request
    // for a later paragraph, or playback on an unrelated first-paragraph gesture.
    const act = (fn) => { fn(); render(); };
    const count = () => playCalls.length;
    const rejectedPolicy = Object.assign(new Error("audible autoplay denied"), { name: "NotAllowedError" });
    const rejectLast = async (reason) => { rejects.at(-1)(reason); await Promise.resolve(); render() };
    const fresh = () => act(() => { hook.stop(); hook.resetCueVisit(); });
    // ReaderView's automatic transport invalidates encounter cues, then pauses
    // only automatically started dialogue. Its manual transport is independent.
    const togglePerformance = () => act(() => {
      hook.interruptCue();
      hook.pauseAutomaticDialogue();
    });
    for (const id of ["s", "n", "a"]) {
      fresh(); act(() => hook.setAutomatic(true)); act(() => hook.play(id));
      audio.currentTime = .65;
      act(() => hook.cueAt(28));
      const calls = count();
      togglePerformance();
      assert.equal(hook.automatic, false);
      assert.equal(hook.status, "playing", `manual ${id} survives the automatic switch`);
      assert.equal(audio.paused, false);
      assert.equal(count(), calls);
      assert.deepEqual(hook.point(), { id, time: .65 });
      ended();
      if (id === "a") {
        assert.equal(hook.current, "b", "manual dialogue sequence stays intact");
        ended();
      }
      assert.equal(hook.current, null, "deferred automated cues are not replayed");
    }
    fresh(); act(() => hook.setAutomatic(true)); act(() => hook.play("c", 0, "automatic"));
    togglePerformance(); assert.equal(hook.status, "paused"); assert.equal(audio.paused, true);
    ended(); assert.equal(hook.current, "c", "automatic dialogue no longer advances");
    fresh(); act(() => hook.cueAt(13)); togglePerformance();
    assert.equal(hook.current, null, "automatic soundscape does stop");
    act(() => hook.cueAt(13)); assert.equal(hook.current, null, "automatic cue does not replay");
    fresh();
    const opening = count();
    act(() => hook.cueAt(0));
    assert.equal(count(), opening);
    assert.equal(audio.src, "");
    act(() => hook.cueAt(13)); // synchronous with the owner's real reading start
    assert.equal(playCalls.at(-1), "/pencil.wav");
    assert.equal(hook.current, "s");
    assert.equal(audio.loop, false);
    assert.equal(hook.point(), null, "automatic sound isn't a history restore target");
    act(() => hook.cueAt(13)); ended();
    act(() => hook.cueAt(40)); act(() => hook.cueAt(13));
    assert.equal(count(), opening + 1, "no duplicate from dwell, end, or reversal");
    act(() => hook.cueAt(28)); ended();
    assert.equal(count(), opening + 2);
    assert.equal(hook.current, null, "finite cue ends without continuing anything");

    // Policy failure is distinct from a corrupt/missing file. Offer a single
    // current-gesture retry, do not retry on render/scroll; new cues may still
    // start after a later user activation without requiring per-cue consent.
    fresh(); act(() => hook.cueAt(13));
    await rejectLast(rejectedPolicy);
    assert.equal(hook.cueBlocked, true); assert.equal(hook.current, null);
    const blockedCount = count();
    act(() => hook.cueAt(13)); act(() => hook.cueAt(13));
    assert.equal(count(), blockedCount);
    act(hook.enableCueSound);
    assert.equal(count(), blockedCount + 1);
    assert.equal(hook.cueBlocked, false); assert.equal(hook.current, "s");
    ended(); act(() => hook.cueAt(28)); assert.equal(hook.current, "w");
    fresh(); act(() => hook.cueAt(13)); await rejectLast(rejectedPolicy);
    act(() => hook.cueAt(40)); assert.equal(hook.cueBlocked, false);
    const gone = count(); act(hook.enableCueSound); assert.equal(count(), gone);
    act(() => hook.cueAt(28)); assert.equal(hook.current, "w");
    const stalePolicy = rejects.at(-1);
    act(() => hook.play("n")); stalePolicy(rejectedPolicy); await Promise.resolve(); render();
    assert.equal(hook.current, "n"); assert.equal(hook.cueBlocked, false);
    fresh(); act(() => hook.cueAt(13)); await rejectLast(new Error("bad file"));
    assert.equal(hook.cueBlocked, false); assert.equal(hook.status, "failed");
    const damagedCount = count(); act(() => hook.cueAt(13)); assert.equal(count(), damagedCount);
    act(() => hook.play("s")); assert.equal(hook.status, "playing", "manual retry still works");

    // A paragraph rising under a manual reading can't seize its single element.
    // Wait only for the still-current paragraph; no replay backlog after jumps.
    fresh(); act(() => hook.play("n"));
    const manualCount = count(); act(() => hook.cueAt(13)); act(() => hook.cueAt(28));
    assert.equal(hook.current, "n"); assert.equal(count(), manualCount);
    ended(); assert.equal(hook.current, "w"); assert.equal(count(), manualCount + 1);
    fresh(); act(() => hook.play("a")); act(() => hook.cueAt(13));
    ended(); assert.equal(hook.current, "b", "don't interrupt the reader's same-paragraph dialogue");
    ended(); assert.equal(hook.current, "s"); ended(); assert.equal(hook.current, null);
    fresh(); act(() => hook.play("n")); act(() => hook.cueAt(13));
    act(() => hook.cueAt(40)); ended(); assert.equal(hook.current, null);
    fresh(); act(() => hook.play("n")); act(() => hook.cueAt(13)); act(hook.suspend);
    const pausedCount = count(); act(() => hook.cueAt(13)); ended();
    assert.equal(count(), pausedCount); assert.equal(hook.current, "n");
    act(hook.resume); ended(); assert.equal(hook.current, null);
    fresh(); act(() => hook.play("s")); ended(); const manualSound = count();
    act(() => hook.cueAt(13)); assert.equal(count(), manualSound, "manual play counts as hearing this visit");
    fresh(); act(() => hook.cueAt(13)); assert.equal(count(), manualSound + 1);

    // Visibility, mute, pause, history and skip invalidate pending asynchronous work.
    fresh(); act(() => hook.cueAt(13)); const late = rejects.at(-1);
    act(() => { global.document.hidden = true; listeners.get("visibilitychange")(); });
    late(rejectedPolicy); await Promise.resolve(); render(); assert.equal(hook.cueBlocked, false);
    const hid = count(); act(() => hook.cueAt(28)); assert.equal(count(), hid);
    act(() => { global.document.hidden = false; listeners.get("visibilitychange")(); });
    assert.equal(count(), hid, "returning to tab alone is not a reading action");
    fresh(); act(() => hook.cueAt(13)); await rejectLast(rejectedPolicy);
    act(() => hook.setCueMuted(true)); assert.equal(audio.muted, true); assert.equal(hook.cueBlocked, false);
    const quiet = count(); act(hook.enableCueSound); act(() => hook.cueAt(28)); act(() => hook.play("n"));
    assert.equal(count(), quiet);
    act(() => hook.setCueMuted(false)); assert.equal(count(), quiet); assert.equal(audio.muted, false);
    act(() => hook.cueAt(28)); assert.equal(count(), quiet + 1);
    fresh(); act(() => hook.cueAt(13)); await rejectLast(rejectedPolicy);
    act(() => hook.leave(new Set(["s"]), true)); const skipped = count();
    act(hook.enableCueSound); assert.equal(count(), skipped); assert.equal(hook.cueBlocked, false);
    fresh(); act(() => hook.cueAt(13)); await rejectLast(rejectedPolicy);
    act(() => hook.restore(null)); const restored = count();
    act(hook.enableCueSound); assert.equal(count(), restored); assert.equal(hook.cueBlocked, false);
    fresh(); act(() => hook.cueAt(13)); await rejectLast(rejectedPolicy);
    const movedBeforeScrollFrame = count(); act(() => hook.enableCueSound(new Set(["w"])));
    assert.equal(count(), movedBeforeScrollFrame); assert.equal(hook.cueBlocked, false);
    fresh(); act(() => hook.play("n")); act(() => hook.cueAt(13)); act(hook.interruptCue);
    assert.equal(hook.current,"n"); assert.equal(hook.status,"playing");
    ended(); assert.equal(hook.current,null,"discontinuity dropped the deferred cue, not the narration");
    fresh(); act(() => hook.cueAt(13)); act(hook.interruptCue);
    assert.equal(hook.current,null); const interrupted = count();
    act(() => hook.cueAt(13)); assert.equal(count(),interrupted,"no automatic replay after interruption");
    fresh(); act(() => hook.cueAt(13)); act(hook.suspend); act(hook.interruptCue);
    const held = count(); act(() => hook.cueAt(13)); assert.equal(count(),held);
    assert.equal(hook.status,"paused","reader's explicit pause is not a play request");
    for (const i of effects) slots[i]?.cleanup?.();
    console.log(
      "Reader audio hook: natural visibility, manual queue, paused return, single-channel approved cues, policy grant/retry, mute, priority, no repeat or stale resume, and visibility suspension passed.",
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
