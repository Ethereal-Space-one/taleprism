"""Build and exercise the synthetic Proof Strip fixture through the production local workbench API.

Requires the built frontend (both bundles), synced backend and Python Playwright,
Pillow and Chromium. Run from anywhere; output directory must not already exist.
All project and browser state is disposable; there is no provider invocation.
Random project/media/job IDs make ZIP hashes per-run, not reproducible identities.
"""

import argparse
import hashlib
import io
import json
import re
import sys
import tempfile
import time
import wave
import zipfile
from array import array
from pathlib import Path

from check_passage_voice import ROOT, server
from PIL import Image
from playwright.sync_api import expect, sync_playwright


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def ok(r):
    assert r.ok, f"{r.status} {r.url}: {r.text()[:1200]}"
    return r


def upload(name, mime, raw):
    return {"name": name, "mimeType": mime, "buffer": raw}


class Project:
    def __init__(self, api, url, pid):
        self.api, self.url, self.pid = api, url, pid
        self.base = url + "/api/projects/" + pid

    def get(self, path):
        return ok(self.api.get(self.base + path))

    def state(self):
        return self.get("/reader").json()

    def revise(self, path, body, method="patch"):
        return ok(
            getattr(self.api, method)(
                self.base + path, data={**body, "revision": self.state()["revision"]}
            )
        ).json()

    def configure(self, **changes):
        return self.revise("/reader", {**self.state()["config"], **changes})

    def export(self):
        jid = ok(self.api.post(self.base + "/reader/exports")).json()["job_id"]
        for _ in range(300):
            item = next(j for j in self.get("/jobs").json() if j["id"] == jid)
            if item["state"] == "completed":
                raw = ok(self.api.get(self.url + item["result"]["download_url"])).body()
                assert digest(raw) == item["result"]["archive_sha256"]
                return raw
            assert item["state"] != "failed", item
            time.sleep(0.1)
        raise AssertionError("reader export did not finish")

    def import_bundle(self, raw):
        result = ok(
            self.api.post(
                self.url + "/api/project-bundles",
                multipart={"file": upload("project.zip", "application/zip", raw)},
            )
        ).json()
        assert result["id"] != self.pid
        return Project(self.api, self.url, result["id"])


def verify_reader_zip(raw, source):
    """Verify every member against the exporter inventory, not just ZIP CRCs."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None
        for runtime in ("assets/reader.js", "assets/reader.css"):
            assert z.getinfo(runtime).file_size > 0, (
                f"Empty runtime asset: {runtime}; freeze frontend build before export"
            )
        files = json.loads(z.read("storygal-delivery.json"))["files"]
        assert set(z.namelist()) == set(files) | {"storygal-delivery.json"}
        assert len(z.namelist()) == len(set(z.namelist()))
        for name, info in files.items():
            data = z.read(name)
            assert len(data) == info["bytes"] and digest(data) == info["sha256"], name
        for name in ("original.txt", "source.utf8.txt"):
            assert z.read("storygal-source/" + name) == source
        return json.loads(z.read("reader.json"))


def pencil_profile(wav):
    with wave.open(io.BytesIO(wav), "rb") as w:
        rate, channels = w.getframerate(), w.getnchannels()
        assert (rate, channels, w.getsampwidth()) == (24000, 2, 2)
        frames = w.getnframes()
        values = array("h", w.readframes(frames))
    if sys.byteorder == "big":
        values.byteswap()
    nonzero = [i // channels for i, v in enumerate(values) if v]
    assert nonzero and frames == rate * 12
    first, last = min(nonzero), max(nonzero)
    # A finite gesture, not a conventional sound-bed or a silent placeholder.
    assert last - first < rate * 5 and first > 0 and frames - last > rate * 3
    return {
        "duration_s": frames / rate,
        "first_nonzero_s": round(first / rate, 4),
        "last_nonzero_s": round(last / rate, 4),
        "tail_silence_s": round((frames - last - 1) / rate, 4),
        "sha256": digest(wav),
    }


def private_absent(reader_raw, strings):
    with zipfile.ZipFile(io.BytesIO(reader_raw)) as z:
        for name in z.namelist():
            data = z.read(name)
            for value in strings:
                assert value.encode() not in data, name
                escaped = json.dumps(value, ensure_ascii=True)[1:-1].encode()
                assert escaped not in data, name


def optional_author_review(project, browser, fixtures, source, out):
    """This project has never requested a creative proposal or opened the panel."""
    with browser.new_context(
        viewport={"width": 1230, "height": 840}, accept_downloads=True
    ) as ctx:
        page = ctx.new_page()
        traffic, errors = [], []
        page.on("request", lambda r: traffic.append((r.method, r.url)))
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(project.url + "/?studio=" + project.pid + "&lane=finish")
        button = page.get_by_role("button", name="导出独立阅读器", exact=True)
        expect(button).to_be_enabled(timeout=12000)
        summary = page.locator("summary").filter(has_text="One More Thing")
        panel = summary.locator("..")
        assert summary.count() == 1 and not panel.evaluate("e=>e.open")
        assert button.evaluate(
            "(e,s)=>!!(e.compareDocumentPosition(s)&Node.DOCUMENT_POSITION_FOLLOWING)",
            summary.element_handle(),
        )
        button.click()
        with page.expect_download(timeout=30000) as event:
            page.get_by_role("link", name="下载阅读器").click(timeout=30000)
        path = out / "plain-baseline.zip"
        event.value.save_as(path)
        plain = verify_reader_zip(path.read_bytes(), source)
        assert not plain["config"].get("echo_fold") and not plain["media"]
        assert not any("/creative/" in url for _, url in traffic)
        before = project.state()
        summary.click()
        for key, label in (
            ("sound", "声音"),
            ("image", "影像"),
            ("presentation", "呈现方式"),
        ):
            panel.get_by_role("button", name=label, exact=True).click()
            importer = panel.locator("details.creative-import")
            if not importer.evaluate("e=>e.open"):
                importer.locator("summary").click()
            with page.expect_response(
                lambda r: (
                    r.url.endswith("/creative/import") and r.request.method == "POST"
                )
            ) as imported:
                panel.get_by_label("导入本篇提案 JSON").set_input_files(
                    str(fixtures / (key + ".json"))
                )
            payload = ok(imported.value).json()
            expect(
                panel.get_by_text(payload["rationale"], exact=False).first
            ).to_be_visible()
            panel.get_by_role("button", name="不用这条提案").click()
            expect(
                panel.get_by_text(payload["rationale"], exact=False)
            ).not_to_be_visible()
            assert (
                project.state() == before
                and not project.get("/reader/soundscapes").json()["takes"]
            )
        page.reload()
        expect(summary).to_be_visible()
        assert not panel.evaluate("e=>e.open")
        summary.click()
        for name in ("sound", "image", "presentation"):
            rationale = json.loads((fixtures / (name + ".json")).read_bytes())[
                "proposal"
            ]["rationale"]
            assert rationale not in panel.inner_text()
        assert project.state() == before
        assert not errors, errors
        assert not [
            u
            for _, u in traffic
            if u.startswith(("http:", "https:")) and not u.startswith(project.url + "/")
        ]
        assert not [u for _, u in traffic if "/creative/propose" in u]
        writes = [(m, u) for m, u in traffic if m not in ("GET", "HEAD", "OPTIONS")]
        assert all(
            u.endswith(("/reader/exports", "/creative/import")) for _, u in writes
        ), writes


def prepare(project, fixture, source, plan, payloads, out):
    assert project.get("/source").body() == source
    s0 = project.state()
    responses = {}
    for key, request in payloads.items():
        assert request["source_sha256"] == digest(source) and request["lens"] == key
        r = ok(
            project.api.post(project.base + "/reader/creative/import", data=request)
        ).json()
        assert r == {"origin": "imported", "lens": key, **request["proposal"]}, r
        responses[key] = r
    assert (
        project.state() == s0 and not project.get("/reader/soundscapes").json()["takes"]
    )
    art, sound, echo = (responses[k] for k in ("image", "sound", "presentation"))
    assert (art["image"], sound["sound"], echo["decision"]) == (
        "still",
        "pencil",
        "echo",
    )
    blocks = s0["paragraphs"]

    def block(anchor):
        par = blocks[anchor["paragraph"] - 1]
        assert par["text"].count(anchor["quote"]) == 1
        assert source[par["byte_start"] : par["byte_end"]].decode() == par["text"]
        return par

    sb, ab = block(sound["later"]), block(art["later"])
    pair = {k: echo[k] for k in ("earlier", "later")}
    for anchor in pair.values():
        block(anchor)
    assert (
        echo["earlier"]["paragraph"],
        echo["later"]["paragraph"],
        art["later"]["paragraph"],
        sound["later"]["paragraph"],
    ) == (2, 5, 3, 6)

    # Programmatic equivalent of this sample editor's explicit media choices.
    # Stage and inspect actual candidates before accepting; import itself made no writes.
    mix = project.revise(
        "/reader/soundscapes",
        {
            "byte_start": sb["byte_start"],
            "evidence": sound["later"]["quote"],
            "rain": False,
            "pencil": True,
        },
        "post",
    )
    (take,) = mix["takes"]
    assert take["status"] == "pending" and take["pencil"]
    with Image.open(fixture / "plate.png") as original:
        art_size, pixels = original.size, original.convert("RGBA").tobytes()
    uploaded = ok(
        project.api.post(
            project.base + "/reader/assets",
            multipart={
                "revision": str(project.state()["revision"]),
                "kind": "scene",
                "license_text": plan["credit"],
                "file": upload(
                    "plate.png", "image/png", (fixture / "plate.png").read_bytes()
                ),
            },
        )
    ).json()
    assert uploaded["status"] == "pending"
    aid = uploaded["id"]
    candidate = project.get("/reader/assets/" + aid).body()
    with Image.open(io.BytesIO(candidate)) as checked:
        assert checked.size == art_size and checked.convert("RGBA").tobytes() == pixels
    snd = ok(project.api.get(project.url + take["url"])).body()
    sound_profile = pencil_profile(snd)
    assert not project.get("/reader/content").json()["media"]
    project.revise("/reader/soundscapes/" + take["id"], {"status": "accepted"})
    project.revise("/reader/assets/" + aid, {"status": "accepted"})
    illustration = {
        "id": "studio-first-illustration",
        "after_byte": ab["byte_end"],
        "image_asset_id": aid,
        "title": plan["caption"],
        "description": plan["alt"],
        "motion": None,
    }
    project.configure(
        reading_layout="illustrated", illustrations=[illustration], echo_fold=pair
    )
    # Synthetic note sentinel: exercise the boundary in *both* directions.
    private_note = (
        "QA_ONLY_NOTE: calibration check; never include this sentinel in the reader."
    )
    editorial = ok(
        project.api.post(
            project.base + "/reader/editorial",
            data={
                "revision": 0,
                "anchor": ab["byte_start"],
                "category": "visual",
                "note": private_note,
                "state": "resolved",
            },
        )
    ).json()
    assert editorial["issues"][0]["note"] == private_note
    reader_raw = project.export()
    (out / "reader.zip").write_bytes(reader_raw)
    book = verify_reader_zip(reader_raw, source)
    assert book["config"]["echo_fold"] == pair and book["config"]["illustrations"] == [
        illustration
    ]
    assert len(book["media"]) == 2 and book["schema_version"] >= 6
    assert [i + 1 for i, b in enumerate(book["blocks"]) if b.get("soundscape")] == [
        sound["later"]["paragraph"]
    ]
    private_absent(
        reader_raw, [private_note, *(r["rationale"] for r in responses.values())]
    )
    with zipfile.ZipFile(io.BytesIO(reader_raw)) as z:
        for asset, raw in (
            (book["media"][aid], candidate),
            (book["media"][take["id"]], snd),
        ):
            assert asset["sha256"] == digest(raw) and z.read(asset["url"][2:]) == raw
        z.extractall(out / "book")  # Archive just made by the isolated exporter.
    editable = project.get("/bundle").body()
    (out / "editable.zip").write_bytes(editable)
    twin = project.import_bundle(editable)
    assert twin.get("/source").body() == source
    tc = twin.get("/reader/content").json()
    assert tc["config"]["echo_fold"] == pair and tc["config"]["illustrations"] == [
        illustration
    ]
    assert twin.get("/reader/editorial").json()["issues"][0]["note"] == private_note
    (saved,) = twin.get("/reader/soundscapes").json()["takes"]
    assert (
        saved["status"] == "accepted"
        and saved["pencil"]
        and saved["evidence"] == take["evidence"]
    )
    assert ok(project.api.get(project.url + saved["url"])).body() == snd
    assert twin.get("/reader/assets/" + aid).body() == candidate
    twin_book = verify_reader_zip(twin.export(), source)
    for key in ("blocks", "config", "media"):
        assert twin_book[key] == book[key], key
    with zipfile.ZipFile(io.BytesIO(editable)) as z:
        for r in responses.values():
            assert all(r["rationale"].encode() not in z.read(n) for n in z.namelist())
    return book, sound_profile


def offline_reader(browser, out, source, book, width):
    """Run after the author service stops, from the unmodified extracted ZIP."""
    phone = width < 500
    with browser.new_context(
        offline=True,
        viewport={"width": width, "height": 810},
        is_mobile=phone,
        has_touch=phone,
        reduced_motion="reduce" if phone else "no-preference",
    ) as ctx:
        traffic, errors = [], []
        page = ctx.new_page()
        page.set_default_timeout(8000)
        page.on("request", lambda r: traffic.append(r.url))
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto((out / "book/index.html").as_uri())
        fold = page.locator(".reader-echo-fold")
        assert not fold.is_visible()
        # Exercise reader-directed disclosure and replay, not v0.9 automatic mode.
        page.get_by_role("button", name="安静阅读", exact=True).click()
        body = page.locator(".reader-paragraph-text")
        paragraphs = source.decode().strip().split("\n\n")
        expect(body).to_have_text(paragraphs)
        echo = book["config"]["echo_fold"]
        # This six-paragraph edition ends with its author's last line, not a completion dashboard.
        ending = page.locator("article.reader-prose footer")
        expect(ending).to_have_attribute("aria-label", "篇末")
        assert (
            not ending.locator("button, h2, a").count() and ending.inner_text() == "◆"
        )
        assert (
            ending.evaluate("e=>e.previousElementSibling.id")
            == book["blocks"][-1]["id"]
        )
        summary, leaf = fold.locator("summary"), fold.locator("blockquote")
        # The folded margin stays with its paragraph, also on a wide display.
        alignment = fold.evaluate("""e=>{
            const a=e.getBoundingClientRect(), b=e.previousElementSibling.getBoundingClientRect();
            return [Math.abs(a.left-b.left),Math.abs(a.width-b.width)]
        }""")
        assert max(alignment) <= 2, (width, alignment)
        assert fold.count() == 1 and not fold.evaluate("e=>e.open")
        expect(leaf).to_have_count(0)  # no surprise browser Find match while folded
        assert echo["earlier"]["quote"] not in summary.inner_text()
        assert echo["later"]["quote"] not in summary.inner_text()
        assert (
            fold.evaluate("e=>e.previousElementSibling.id")
            == book["blocks"][echo["later"]["paragraph"] - 1]["id"]
        )
        assert not page.locator(".reader-paragraph .reader-echo-fold").count()
        # Silence and static pixels at startup, including where the illustration is expanded.
        audio = page.locator("audio")
        assert audio.evaluate("a=>a.paused && !a.currentSrc")
        assert not any(u.endswith(".wav") for u in traffic)
        (plate_meta,) = book["config"]["illustrations"]
        plate = page.locator("figure.reader-plate")
        expect(plate).to_have_count(1)
        assert plate.get_attribute("data-display-after-byte") == str(
            plate_meta["after_byte"]
        )
        assert (
            plate.evaluate("e=>e.previousElementSibling.id") == book["blocks"][2]["id"]
        )
        plate.scroll_into_view_if_needed()
        image = plate.locator("img")
        page.wait_for_function(
            "()=>document.querySelector('figure.reader-plate img')?.naturalWidth>0"
        )
        assert image.get_attribute("alt") == plate_meta["description"]
        assert (
            image.evaluate("e=>e.naturalWidth")
            == book["media"][plate_meta["image_asset_id"]]["width"]
        )
        plate_button = plate.get_by_role(
            "button", name="放大插图：" + plate_meta["title"]
        )
        plate_button.click()
        dialog = page.locator("dialog[open]")
        expect(dialog).to_be_visible()
        assert not dialog.get_by_role(
            "button", name=re.compile("开启动效|关闭动效")
        ).count()
        assert not page.locator("canvas").count() and audio.evaluate("a=>a.paused")
        page.screenshot(path=str(out / f"plate-{width}.png"))
        page.keyboard.press("Escape")
        expect(plate_button).to_be_focused()
        summary.scroll_into_view_if_needed()
        # Native keyboard disclosure; after opening, there is exactly one earlier quote,
        # no private reading, future text, controls or hidden requirement to continue.
        summary.focus()
        summary.press("Enter")
        expect(leaf).to_be_visible()
        expect(leaf).to_have_text(echo["earlier"]["quote"])
        assert fold.locator("blockquote").count() == 1
        assert paragraphs[-1] not in fold.inner_text()
        assert not fold.locator("button, audio, img, canvas").count()
        assert audio.evaluate("a=>a.paused && !a.currentSrc")
        page.screenshot(path=str(out / f"echo-{width}.png"))
        # Select across the open marginal note: copy uses exact source, never the extra quote.
        copied = page.evaluate("""() => {
            const paras=[...document.querySelectorAll('.reader-paragraph-text')];
            const run=(e,sel)=>e.querySelector(sel).firstChild;
            const r=document.createRange(), a=run(paras[4],'[data-source-start]'),
              b=run(paras[5],'[data-source-start]:last-of-type');
            r.setStart(a,0);r.setEnd(b,b.length);
            const s=getSelection();s.removeAllRanges();s.addRange(r);
            const dt=new DataTransfer(); paras[4].dispatchEvent(new ClipboardEvent('copy',
                {bubbles:true,cancelable:true,clipboardData:dt}));
            s.removeAllRanges();return dt.getData('text/plain');
        }""")
        assert copied == "\n\n".join(paragraphs[4:6]), repr(copied)
        summary.press("Enter")
        expect(leaf).to_be_hidden()
        expect(summary).to_be_focused()
        sound = page.get_by_role("button", name="听此处声景：第 6 段", exact=True)
        expect(sound).to_have_count(1)
        assert (
            sound.evaluate("e=>e.closest('.reader-paragraph').id")
            == book["blocks"][-1]["id"]
        )
        assert not any(u.endswith(".wav") for u in traffic)
        sound.click()
        page.wait_for_function(
            "()=>{const a=document.querySelector('audio');return !a.paused && a.currentTime>.12}"
        )
        assert audio.evaluate("a=>a.currentSrc").endswith(
            book["media"][book["blocks"][-1]["soundscape"]["id"]]["url"][1:]
        )
        # No seek: the delivered PCM reaches a real browser media-ended event.
        page.wait_for_function(
            "()=>{const a=document.querySelector('audio');return a.ended && a.paused}",
            timeout=18500,
        )
        expect(sound).to_be_visible()
        assert not fold.evaluate("e=>e.open") and not page.locator("canvas").count()
        if page.get_by_role("button", name="阅读工具", exact=True).count():
            page.get_by_role("button", name="阅读工具", exact=True).click()
        page.get_by_role("button", name="设置", exact=True).click()
        page.get_by_role("button", name="隐藏回声折页", exact=True).click()
        page.keyboard.press("Escape")
        assert not fold.count()
        expect(body).to_have_text(paragraphs)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
        assert not errors, errors
        assert all(u.startswith(("file:", "data:", "blob:")) for u in traffic), traffic
        return {
            "width": width,
            "phone_emulation": phone,
            "no_http_requests": True,
            "requests": len(traffic),
            "natural_audio_end": True,
            "cross_fold_copy_exact": True,
            "fold_paragraph_alignment_delta_px": alignment,
            "ends_quietly_on_last_line": True,
        }


def legacy(project, archive):
    with zipfile.ZipFile(archive) as z:
        source = z.read("original.txt")
    copy = project.import_bundle(archive.read_bytes())
    book = verify_reader_zip(copy.export(), source)
    assert not book["config"].get("echo_fold")
    (take,) = copy.get("/reader/soundscapes").json()["takes"]
    assert take["rain"] and not take.get("pencil") and take["car_at"] == 6
    assert book["config"]["illustrations"][0]["motion"]["reviewed"] is True
    return {
        "archive": archive.name,
        "legacy_rain_car_and_reviewed_motion": "preserved",
        "schema_version": book["schema_version"],
    }


def quiet_case(api, url, fixture):
    source = (fixture / "source.txt").read_bytes()
    made = ok(
        api.post(
            url + "/api/projects",
            multipart={
                "rights_status": "owned",
                "file": upload("quiet-control.txt", "text/plain", source),
            },
        )
    ).json()
    project = Project(api, url, made["id"])
    before = project.state()
    for key in ("sound", "image", "presentation"):
        raw = json.loads((fixture / (key + ".json")).read_bytes())
        response = ok(
            api.post(project.base + "/reader/creative/import", data=raw)
        ).json()
        assert set(response) == {"origin", "lens", "decision", "rationale"}
        assert response["decision"] == "quiet" and response["origin"] == "imported"
    assert project.state() == before
    book = verify_reader_zip(project.export(), source)
    assert not book["media"] and not book["config"].get("echo_fold")
    assert not book["config"].get("illustrations")
    return {
        "all_three_quiet": True,
        "source_sha256": digest(source),
        "no_added_media_or_fold": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--edition", type=Path, default=ROOT / "examples/reading-lab/proof-strip"
    )
    parser.add_argument(
        "--backend-python", default=str(ROOT / "backend/.venv/bin/python")
    )
    parser.add_argument("--chromium")
    parser.add_argument(
        "--rain-bundle",
        type=Path,
        help="Optional editable output from check_soundscape_browser.py",
    )
    parser.add_argument(
        "--skip-author-ui",
        action="store_true",
        help="Build/check edition without the author UI smoke",
    )
    args = parser.parse_args()
    fixture, out = args.edition.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = (fixture / "source.txt").read_bytes()
    payloads = {
        k: json.loads((fixture / (k + ".json")).read_bytes())
        for k in ("sound", "image", "presentation")
    }
    plan = json.loads((fixture / "edition.json").read_bytes())
    with (
        tempfile.TemporaryDirectory(prefix="taleprism-creative-") as tmp,
        sync_playwright() as pw,
    ):
        browser = pw.chromium.launch(executable_path=args.chromium)
        with server(args.backend_python, Path(tmp), out) as url:
            api = pw.request.new_context()
            pid = ok(
                api.post(
                    url + "/api/projects",
                    multipart={
                        "rights_status": "owned",
                        "single_plate_studio": "true",
                        "file": upload(plan["title"] + ".txt", "text/plain", source),
                    },
                )
            ).json()["id"]
            project = Project(api, url, pid)
            if not args.skip_author_ui:
                optional_author_review(project, browser, fixture, source, out)
                print(
                    "Cold final-review panel: skip, export, review all three, discard, reload: PASS.",
                    flush=True,
                )
            else:
                verify_reader_zip(project.export(), source)
            book, pcm = prepare(project, fixture, source, plan, payloads, out)
            print(
                "Imported three source-bound proposals. Export/backup/restore/re-export: PASS.",
                flush=True,
            )
            old = legacy(project, args.rain_bundle) if args.rain_bundle else None
            quiet = quiet_case(api, url, fixture / "quiet")
            api.dispose()
        # No development server or project database available to either browser context.
        screens = []
        for width in (1170, 390):
            screens.append(offline_reader(browser, out, source, book, width))
            print(
                f"{width}px unmodified file:// reading, fold, image, sound, privacy: PASS.",
                flush=True,
            )
        report = {
            "passed": True,
            "chromium": browser.version,
            "edition": plan["title"],
            "source_bytes": len(source),
            "source_sha256": digest(source),
            "lens_origin": "3 separately imported synthetic proposals, no live provider",
            "author_skip_export_review_discard_reload": not args.skip_author_ui,
            "offline": screens,
            "pencil_pcm": pcm,
            "editable": "fresh project, re-export matched blocks/config/media",
            "privacy": "editorial note retained only in backup; the three unadopted explanations not saved in either ZIP",
            "rain_bundle_roundtrip": old,
            "abstention_control": quiet,
            "limits": "Headless Chromium and phone emulation; not hardware, Safari, human listening or owner approval.",
            "packages": {
                n: digest((out / n).read_bytes())
                for n in ("reader.zip", "editable.zip")
            },
        }
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        browser.close()


if __name__ == "__main__":
    main()
