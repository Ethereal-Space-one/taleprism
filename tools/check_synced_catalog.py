"""Verify disposable Reading Lab exports, offline playback and (optional) prior-edition stability.

Example: --book proof-strip OUT/reader.zip --book rain-grid OTHER/reader.zip --output QA --full
Add --baseline NAME PRIOR.zip for a comparison with a previous export of the same fixture.
"""

import argparse
import io
import json
import tempfile
import wave
from pathlib import Path
from urllib.parse import urlsplit

from chibi_source import digest, read_zip, verify_inventory
from playwright.sync_api import expect, sync_playwright

SAMPLES = Path(__file__).resolve().parents[1] / "examples/reading-lab"
CASES = {
    "proof-strip": (6, "铅笔在纸上划过，随后静默"),
    "rain-grid": (2, "细雨中一辆车驶过"),
}


def load(path, expected=None):
    payload = Path(path).read_bytes()
    h = digest(payload)
    assert not expected or expected == h, "Wrong previous ZIP: " + str(path)
    files = read_zip(payload)
    verify_inventory(files)
    return h, files, json.loads(files["reader.json"])


def check_archive(name, path, previous, raw):
    sha, files, story = load(path)
    paragraph, label = CASES[name]
    sample = (SAMPLES / name / "source.txt").read_bytes()
    source_sha = digest(sample)
    start = sample.index(sample.strip().split(b"\n\n")[paragraph - 1])
    source = files["storygal-source/source.utf8.txt"]
    assert source == files["storygal-source/original.txt"]
    assert digest(source) == source_sha == story["project"]["canonical_sha256"]
    assert story["project"]["sha256"] == source_sha and story["schema_version"] in (
        5,
        6,
    )
    blocks, media = story["blocks"], story["media"]
    sounds = [(i + 1, b) for i, b in enumerate(blocks) if b.get("soundscape")]
    assert len(sounds) == 1 and sounds[0][1]["byte_start"] == start
    idx, block = sounds[0]
    cue = block["soundscape"]
    assert cue["duration"] == 12 and cue["description"] == label
    assert media[cue["id"]]["origin"] == "paragraph_soundscape"
    cursor = 0
    for b in blocks:
        a, z = b["byte_start"], b["byte_end"]
        assert cursor <= a < z and source[a:z].decode() == b["text"]
        assert not source[cursor:a].decode().strip()
        cursor = z
    assert not source[cursor:].decode().strip()
    for asset in media.values():
        assert digest(files[asset["url"].removeprefix("./")]) == asset["sha256"]
    wav = files[media[cue["id"]]["url"].removeprefix("./")]
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getparams()[:4] == (2, 2, 24000, 288000) and w.getcomptype() == "NONE"
    assert "不是现场录音、音乐或朗读" in files["RIGHTS.txt"].decode()
    prior_sha, retained = None, {}
    if previous:
        prior_sha, old, base = load(previous)
        assert base["config"]["title"] == story["config"]["title"]
        assert base["config"].get("subtitle") == story["config"].get("subtitle")
        if not raw:
            assert base["project"]["id"] == story["project"]["id"], "Unstable work ID"
        for n in ("storygal-source/original.txt", "storygal-source/source.utf8.txt"):
            assert old[n] == files[n]
        assert len(base["blocks"]) == len(blocks)
        for a, b in zip(base["blocks"], blocks, strict=True):
            for k in (
                "id",
                "byte_start",
                "byte_end",
                "text",
                "heading",
                "runs",
                "audio",
                "narration",
            ):
                assert a.get(k) == b.get(k), (name, k, b["byte_start"])
        old_plates = base["config"].get("illustrations", [])
        new_plates = story["config"].get("illustrations", [])
        for a, b in zip(old_plates, new_plates, strict=True):
            for k in ["image_asset_id", "after_byte", "title"] + (
                [] if raw else ["id"]
            ):
                assert a[k] == b[k], (name, "plate", k)
        assert set(media) == set(base["media"]) | {cue["id"]}
        for key, a in base["media"].items():
            b = media[key]
            assert a["type"] == b["type"] and a["sha256"] == b["sha256"]
            assert (
                old[a["url"].removeprefix("./")] == files[b["url"].removeprefix("./")]
            )
            if a.get("credit"):
                assert (
                    a["credit"] == b["credit"]
                    and a["credit"] in files["RIGHTS.txt"].decode()
                )
            retained[key] = a["sha256"]
    return (
        files,
        story,
        {
            "zip_sha256": sha,
            "baseline_sha256": prior_sha,
            "stable_ids_checked": bool(previous and not raw),
            "work_id": story["project"]["id"],
            "source_sha256": source_sha,
            "source_bytes": len(source),
            "blocks": len(blocks),
            "plates": len(story["config"].get("illustrations", [])),
            "old_media_sha256": retained,
            "cue": {
                "paragraph": idx,
                "byte_start": start,
                "description": label,
                "sha256": digest(wav),
            },
        },
    )


def read_offline(browser, name, folder, story, report, out):
    # The only app entry point is the actual embedded reader in the taken ZIP.
    with browser.new_context(
        offline=True,
        viewport={"width": 390 if name == "proof-strip" else 1100, "height": 820},
        reduced_motion="reduce",
        locale="zh-CN",
        service_workers="block",
    ) as ctx:
        p = ctx.new_page()
        p.set_default_timeout(12000)
        requests, errors = [], []
        ctx.on("request", lambda r: requests.append(r.url))
        p.on("pageerror", lambda e: errors.append(str(e)))
        p.goto((folder / "index.html").as_uri())
        assert (
            p.locator("#taleprism-story").evaluate("e=>JSON.parse(e.textContent)")
            == story
        )
        expect(p.get_by_role("heading", level=1)).to_be_visible()
        # Deliberately test the reader-directed path separately from auto encounters.
        start = p.get_by_role("button", name="开始阅读 →", exact=True)
        expect(start).to_be_visible()
        quiet = p.get_by_role("button", name="安静阅读", exact=True)
        (quiet if quiet.count() else start).click()
        paragraph = p.locator("section.reader-paragraph")
        assert paragraph.evaluate_all(
            """ss=>ss.map(e=>[+e.dataset.byteStart,
            [...e.querySelectorAll('.reader-paragraph-text [data-source-start]')].map(s=>s.textContent).join('')])"""
        ) == [[b["byte_start"], b["text"]] for b in story["blocks"]]
        # Let initial rendering and its queued handlers settle before silence assertion.
        p.evaluate(
            "()=>new Promise(ok=>requestAnimationFrame(()=>requestAnimationFrame(ok)))"
        )
        assert not [u for u in requests if urlsplit(u).path.lower().endswith(".wav")]
        assert p.locator("audio").evaluate_all(
            "aa=>aa.every(a=>a.paused&&!a.currentTime)"
        )
        assert p.locator("[data-soundscape-paragraph]").count() == 1
        assert p.get_by_role("button", name="听此处声景：").count() == 1
        idx = report["cue"]["paragraph"]
        b = story["blocks"][idx - 1]
        sound = p.get_by_role("button", name=f"听此处声景：第 {idx} 段", exact=True)
        expect(sound).to_contain_text(b["soundscape"]["description"])
        desc = sound.evaluate(
            "e=>document.getElementById(e.getAttribute('aria-describedby')).textContent"
        )
        assert b["soundscape"]["description"] in desc and "12 秒" in desc
        sound.scroll_into_view_if_needed()
        p.screenshot(path=str(out / (name + ".png")))

        def native_start(control, media_id):
            control.press("Enter")
            p.wait_for_function(
                """url=>{const a=document.querySelector('audio');
                return a && !a.paused&&!a.error&&!a.muted&&a.volume>0&&a.playbackRate===1&&a.currentTime>.15&&
                new URL(a.currentSrc).href===new URL(url,location.href).href}""",
                arg=story["media"][media_id]["url"],
            )

        if b.get("narration"):
            assert (
                b.get("narration")
                and p.locator("[data-narrated-paragraph]").count() == 1
            )
            voice = p.get_by_role("button", name=f"听这一段：第 {idx} 段", exact=True)
            native_start(voice, b["narration"]["id"])
        native_start(sound, b["soundscape"]["id"])
        assert p.locator("audio").count() == 1
        if b.get("narration"):
            expect(voice).to_be_visible()
            assert p.get_by_role("button", name="暂停朗读：").count() == 0
        p.wait_for_function(
            "()=>{const a=document.querySelector('audio');return a.ended&&a.paused}",
            timeout=16500,
        )
        played = p.locator("audio").evaluate(
            """a=>({duration:a.duration,rate:a.playbackRate,
            ranges:Array.from({length:a.played.length},(_,i)=>[a.played.start(i),a.played.end(i)])})"""
        )
        assert played == {"duration": 12, "rate": 1, "ranges": [[0, 12]]}, played
        expect(sound).to_be_visible()
        assert p.locator("audio").evaluate("a=>a.paused && a.ended")
        assert p.url.split("#")[0] == (folder / "index.html").as_uri()
        assert not errors, errors
        assert not [
            u for u in requests if urlsplit(u).scheme not in {"file", "data", "blob"}
        ], requests
        report.update(
            native_playback=played,
            narration_to_sound=bool(b.get("narration")),
            no_initial_wav=True,
            no_remote_requests=True,
            file_dom_matches_json=True,
            visible_description=b["soundscape"]["description"],
        )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--book", nargs=2, action="append", required=True, metavar=("NAME", "ZIP")
    )
    ap.add_argument(
        "--baseline",
        nargs=2,
        action="append",
        default=[],
        metavar=("NAME", "PREVIOUS_ZIP"),
    )
    ap.add_argument(
        "--raw",
        action="store_true",
        help="Developer smoke only: skip stable identity assertion",
    )
    ap.add_argument(
        "--full",
        action="store_true",
        help="Require both public fixture exports",
    )
    ap.add_argument(
        "--chromium", help="Executable path; omit to use Playwright's Chromium"
    )
    ap.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New verification directory, must not exist",
    )
    args = ap.parse_args()
    books, bases = dict(args.book), dict(args.baseline)
    if (
        len(books) != len(args.book)
        or len(bases) != len(args.baseline)
        or set(books) - set(CASES)
        or set(bases) - set(books)
        or (args.full and set(books) != set(CASES))
    ):
        ap.error(
            "Use proof-strip or rain-grid, and both for --full. Baselines need matching books."
        )
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=args.chromium)
        results = {}
        for name, path in books.items():
            files, story, report = check_archive(name, path, bases.get(name), args.raw)
            with tempfile.TemporaryDirectory(prefix="taleprism-file-reader-") as tmp:
                folder = Path(tmp)
                for rel, blob in files.items():
                    dst = folder / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(blob)
                del files
                read_offline(browser, name, folder, story, report, out)
            results[name] = report
            print(name, report["zip_sha256"], report["cue"], "PASS", flush=True)
        (out / "catalog-proof.json").write_text(
            json.dumps(
                {
                    "both_fixtures": args.full,
                    "raw": args.raw,
                    "chromium": browser.version,
                    "editions": results,
                    "limit": "Native desktop Chromium playback and layout; not a human listening test or device/Safari test.",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        browser.close()


if __name__ == "__main__":
    main()
