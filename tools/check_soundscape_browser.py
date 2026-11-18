"""Author a passage sound, protected motion and illustration, then read the real ZIP offline.

Requires synced backend, built workbench/reader, Python Playwright and Chromium.
Uses a new disposable local data store. The example assets are original to this edition.
"""

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from check_passage_voice import ROOT, server
from playwright.sync_api import expect, sync_playwright


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chromium")
    ap.add_argument("--backend-python", default=str(ROOT / "backend/.venv/bin/python"))
    ap.add_argument(
        "--edition", type=Path, default=ROOT / "examples/reading-lab/rain-grid"
    )
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    fixture = args.edition.resolve()
    plan = json.loads((fixture / "edition.json").read_text())
    source = (fixture / "source.txt").read_bytes()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)

    def mark(s):
        notes.append(s)
        print(s, flush=True)

    notes = []
    with (
        tempfile.TemporaryDirectory(prefix="taleprism-sound-") as tmp,
        server(args.backend_python, Path(tmp), out) as url,
        sync_playwright() as pw,
    ):
        browser = pw.chromium.launch(executable_path=args.chromium)
        ctx = browser.new_context(
            accept_downloads=True, viewport={"width": 1280, "height": 900}
        )
        page = ctx.new_page()
        page.set_default_timeout(14000)
        errors, external = [], []
        ctx.on(
            "request",
            lambda r: (
                external.append(r.url)
                if r.url.startswith(("http:", "https:"))
                and not r.url.startswith(url + "/")
                else None
            ),
        )
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.get_by_role("link", name="用自己的图文开始", exact=True).first.click()
        page.get_by_label("原文输入方式").select_option("file")
        page.get_by_label("原文 TXT 文件").set_input_files(
            {"name": plan["title"] + ".txt", "mimeType": "text/plain", "buffer": source}
        )
        page.get_by_label("原文权利状态").select_option("owned")
        page.get_by_role("button", name="新建项目，先编声景").click()
        scope = (
            page.locator("details")
            .filter(has=page.get_by_label("声景对应的原文段落"))
            .last
        )
        selector = page.get_by_label("声景对应的原文段落")
        selector.select_option(index=2)
        pid = parse_qs(urlparse(page.url).query)["studio"][0]
        base = url + "/api/projects/" + pid
        assert ctx.request.get(base + "/source").body() == source
        scope.get_by_label("原文依据", exact=True).fill(plan["sound_evidence"])
        scope.get_by_label("持续细雨", exact=False).check()
        scope.get_by_label("一辆车驶过", exact=False).check()
        timing = scope.get_by_label("车辆经过的时刻", exact=False)
        timing.fill("6")
        page.get_by_role("button", name="生成待审声景").click()
        listen = page.get_by_label("试听待审声景", exact=True)
        listen.wait_for()
        adopt = page.get_by_role("button", name="已对照原文，采用此声景")
        expect(adopt).to_be_disabled()
        assert not any(
            b.get("soundscape")
            for b in ctx.request.get(base + "/reader/content").json()["blocks"]
        )
        listen.evaluate("a=>a.play()")
        expect(adopt).to_be_enabled(timeout=20000)
        adopt.click()
        page.get_by_label("已采用的段落声景", exact=True).wait_for()
        mark(
            "Exact original + passage evidence. Pending mix absent from reader; whole 12 s played before explicit adoption."
        )
        page.get_by_role("button", name="添加插图或返回底图制作").click()
        page.get_by_label("插图文件").set_input_files(fixture / plan["plate"])
        page.get_by_label("图片来源与许可").fill(plan["art_credit"])
        page.get_by_role("button", name="上传为候选图").click()
        page.get_by_role("button", name="接受这张底图").click()
        page.get_by_label("插图名称").fill(plan["caption"])
        page.get_by_label("插图替代文字（可选）").fill(plan["alt"])
        page.get_by_label("放在此段之后").select_option(index=2)
        page.get_by_role("button", name="放置静图").click()
        director = page.locator("details.motion-director")
        expect(director).to_have_attribute("open", "")
        director.get_by_label("逐字原文依据", exact=False).fill(plan["motion_evidence"])
        director.get_by_label("画面观察与保护范围", exact=False).fill(plan["direction"])
        svg = director.locator(".motion-director-map svg")

        def polygon(points):
            svg.scroll_into_view_if_needed()
            box = svg.bounding_box()
            for x, y in points:
                svg.click(position={"x": x * box["width"], "y": y * box["height"]})
            director.get_by_role("button", name="闭合并加入范围").click()

        for area in plan["areas"]:
            polygon(area)
        director.get_by_role("button", name="标接雨湿地").click()
        for ground in plan["ground"]:
            polygon(ground)
        drops = director.get_by_label("雨线数量", exact=False)
        drops.fill("46")
        rings = director.get_by_role("slider").last
        rings.focus()
        rings.press("Home")
        for _ in range(4):
            rings.press("ArrowRight")
        director.get_by_role("button", name="打开动效对照").click()
        director.get_by_role("button", name="开启动效").click()
        director.locator(
            ".motion-director-preview .reader-image-viewport"
        ).scroll_into_view_if_needed()
        reviewed = director.get_by_role("checkbox")
        expect(reviewed).to_be_enabled(timeout=35000)
        reviewed.check()
        director.get_by_role("button", name="纳入章节草稿").click()
        page.get_by_role("button", name="保存章节编排").click()
        export = page.get_by_role("button", name="导出独立阅读器")
        expect(export).to_be_enabled()
        export.click()
        with page.expect_download() as d:
            page.get_by_role("link", name="下载阅读器").click(timeout=30000)
        d.value.save_as(out / "reader.zip")
        page.get_by_text("备份可编辑工程", exact=True).click()
        with page.expect_download() as d:
            page.get_by_role("button", name="下载工程 ZIP").click()
        d.value.save_as(out / "editable.zip")
        with zipfile.ZipFile(out / "reader.zip") as z:
            assert (
                z.testzip() is None and z.read("storygal-source/original.txt") == source
            )
            content = json.loads(z.read("reader.json"))
            assert content["schema_version"] == 5
            cue = content["blocks"][1]["soundscape"]
            asset = content["media"][cue["id"]]
            assert cue["duration"] == 12 and cue["description"] == "细雨中一辆车驶过"
            assert sum(bool(b.get("soundscape")) for b in content["blocks"]) == 1
            assert (
                asset["origin"] == "paragraph_soundscape"
                and sum(n.endswith(".wav") for n in z.namelist()) == 1
            )
            payload = content["config"]["illustrations"][0]["motion"]
            assert (
                payload["reviewed"]
                and "note" not in payload
                and "evidence" not in payload
            )
            assert plan["direction"].encode() not in z.read("index.html") and plan[
                "direction"
            ].encode() not in z.read("reader.json")
            z.extractall(out / "book")
        result = ctx.request.post(
            url + "/api/project-bundles",
            multipart={
                "file": {
                    "name": "editable.zip",
                    "mimeType": "application/zip",
                    "buffer": (out / "editable.zip").read_bytes(),
                }
            },
        )
        assert result.status == 201, result.text()
        copied = url + "/api/projects/" + result.json()["id"]
        assert copied != base
        assert ctx.request.get(copied + "/source").body() == source
        stored = ctx.request.get(copied + "/reader/soundscapes").json()["takes"]
        assert (
            len(stored) == 1
            and stored[0]["status"] == "accepted"
            and stored[0]["car_at"] == 6
        )
        assert stored[0]["evidence"] == plan["sound_evidence"]
        mark(
            "Reviewed illustration/mask and independently reviewed sound exported; a fresh edit copy retains the private cue choices, original, and motion direction."
        )
        ctx.close()
        for w, reduced in [(1000, False), (390, True)]:
            c = browser.new_context(
                offline=True,
                viewport={"width": w, "height": 810},
                reduced_motion="reduce" if reduced else "no-preference",
            )
            pg = c.new_page()
            pg.set_default_timeout(12000)
            req = []
            pg.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            pg.on("request", lambda r, req=req: req.append(r.url))
            pg.goto((out / "book/index.html").as_uri())
            # This legacy contract is the manual path, including independent motion.
            pg.get_by_role("button", name="安静阅读", exact=True).click()
            doc = pg.get_by_label("连续阅读正文")
            body = pg.locator(".reader-paragraph-text")
            assert [s.strip() for s in body.all_text_contents()] == [
                s.strip() for s in source.decode().splitlines() if s.strip()
            ]
            quiet = pg.get_by_role("button", name="听此处声景：第 2 段", exact=True)
            assert quiet.count() == 1 and not [u for u in req if u.endswith(".wav")]
            assert not pg.locator("canvas").count()
            quiet.scroll_into_view_if_needed()
            y = doc.evaluate("e=>e.scrollTop")
            quiet.click()

            def clock_advances(pg=pg):
                for _ in range(45):
                    if pg.locator("audio").evaluate(
                        "e=>!e.paused && e.currentTime>0.15"
                    ):
                        return
                    pg.wait_for_timeout(100)
                raise AssertionError("the delivered sample did not play")

            clock_advances()
            pg.get_by_role("button", name="暂停声景").click()
            assert pg.locator("audio").evaluate("a=>a.paused")
            pg.get_by_role("button", name="继续声景").click()
            clock_advances()
            pg.get_by_role("button", name="停止声景").click()
            expect(quiet).to_be_focused()
            assert (
                abs(y - doc.evaluate("e=>e.scrollTop")) < 4
                and not pg.locator("canvas").count()
            )
            plate = pg.get_by_role(
                "button", name="放大插图：" + plan["caption"], exact=True
            )
            plate.click()
            dlg = pg.locator("dialog[open]")
            motion = dlg.get_by_role("button", name="开启动效")
            expect(motion).to_have_attribute("aria-pressed", "false")
            sound = dlg.get_by_role("button", name="听此处声景：第 2 段")
            sound.click()
            clock_advances()
            expect(dlg).to_be_visible()
            expect(motion).to_have_attribute("aria-pressed", "false")
            if reduced:
                expect(motion).to_be_disabled()
            else:
                motion.click()
                expect(dlg.locator("canvas")).to_be_visible()
                assert pg.locator("audio").evaluate("a=>!a.paused")
                overlay = dlg.locator("canvas")
                for _ in range(24):
                    pixels = overlay.evaluate("""c=>{const {width:w,height:h}=c, a=c.getContext('2d').getImageData(0,0,w,h).data;
                    let wet=0,dry=0;for(let y=0;y<h;y++)for(let x=0;x<w;x++){if(!a[(y*w+x)*4+3])continue;
                    if(x/w>.55)wet++;if(x/w<.5)dry++;}return {wet,dry}}""")
                    if pixels["wet"]:
                        break
                    pg.wait_for_timeout(100)
                assert pixels["wet"] > 0 and pixels["dry"] == 0, pixels
                mark(
                    f"Rendered scene motion: {pixels['wet']} nontransparent pixels over the collection grid; zero pixels in the protected left half."
                )
                pg.screenshot(path=str(out / "rain-grid.png"))
                dlg.get_by_role("button", name="关闭动效").click()
                expect(dlg.locator("canvas")).not_to_be_visible()
                # Actual native end, no seek shortcut, no chaining or forced navigation.
                expect(sound).to_be_visible(timeout=14500)
                assert pg.locator("audio").evaluate("a=>a.ended && a.paused")
            pg.keyboard.press("Escape")
            expect(plate).to_be_focused()
            if pg.get_by_role("button", name="阅读工具", exact=True).count():
                pg.get_by_role("button", name="阅读工具", exact=True).click()
            pg.get_by_role("button", name="设置", exact=True).click()
            pg.get_by_role("button", name="收起声景入口").click()
            pg.keyboard.press("Escape")
            assert quiet.count() == 0
            assert [s.strip() for s in body.all_text_contents()] == [
                s.strip() for s in source.decode().splitlines() if s.strip()
            ]
            assert not [
                u for u in req if u.startswith(("https:", "http:"))
            ] and pg.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            pg.screenshot(path=str(out / f"quiet-{w}.png"))
            c.close()
            mark(
                f"Offline {w}px, reduce={reduced}: reader chose sound, picture motion stayed independent, focus and exact text survived; no external requests."
            )
        assert not errors and not external, (errors, external)
        (out / "report.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "chromium": browser.version,
                    "source_bytes": len(source),
                    "sha256": hashlib.sha256(source).hexdigest(),
                    "media": asset["sha256"],
                    "checks": notes,
                    "rating_limit": "Scripted browser/PCM checks. Not human listening or physical Safari.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        browser.close()


if __name__ == "__main__":
    main()
