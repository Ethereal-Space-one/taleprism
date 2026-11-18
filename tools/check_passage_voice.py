"""A real first author brings text + voice to a new workbench, then reads offline.

Build frontend and sync backend first. Requires Python Playwright plus Chromium.
Use --verse to exercise exact spaced verse and a public subtitle. Both modes use
only generated test audio and their own temporary project store.
"""

import argparse
import contextlib
import hashlib
import json
import math
import os
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
import wave
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@contextlib.contextmanager
def server(python, path, out):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = str(sock.getsockname()[1])
    url = "http://127.0.0.1:" + port
    with (out / "server.log").open("w") as log:
        proc = subprocess.Popen(
            [
                python,
                "-m",
                "uvicorn",
                "storygal.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                port,
            ],
            stdout=log,
            stderr=log,
            cwd=ROOT,
            env={
                **os.environ,
                "STORYGAL_DATA_DIR": str(path / "store"),
                "PYTHONPATH": str(ROOT / "backend/src"),
                "OPENAI_API_KEY": "",
                "DEEPSEEK_API_KEY": "",
            },
        )
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url + "/api/health", timeout=0.5):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Isolated service did not start")
            yield url
        finally:
            proc.terminate()
            proc.wait(timeout=10)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend-python", default=str(ROOT / "backend/.venv/bin/python"))
    ap.add_argument("--chromium")
    ap.add_argument("--verse", action="store_true")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    checks = []
    subtitle = ""

    def mark(s):
        checks.append(s)
        print(s, flush=True)

    with tempfile.TemporaryDirectory(prefix="taleprism-passage-") as tmp:
        work = Path(tmp)
        title, caption = "独立朗读测试", "试印条"
        source = (
            "横刻留青线， 一纸分深浅。 斜光移半格， 重叠见前痕。"
            if args.verse
            else "原文在这里。可以静静读完，也可以听一段。"
        ).encode()
        subtitle = "校样说明：用空格分隔相等的短句。" if args.verse else ""
        credit = "自制合成测试音（非朗读），用于验证本地播放。"
        art_credit, alt = "Taleprism MIT 几何测试图。", "五个不同颜色的矩形排成一行。"
        audio, art = (
            work / "qa.wav",
            ROOT / "examples/reading-lab/proof-strip/plate.png",
        )
        with wave.open(str(audio), "wb") as w:
            w.setparams((1, 2, 24000, 0, "NONE", ""))
            w.writeframes(
                b"".join(
                    struct.pack(
                        "<h", int(3000 * math.sin(2 * math.pi * 220 * i / 24000))
                    )
                    for i in range(48000)
                )
            )
        with server(args.backend_python, work, out) as url, sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=args.chromium)
            ctx = browser.new_context(
                viewport={"width": 1100, "height": 850}, accept_downloads=True
            )
            page = ctx.new_page()
            errs, net = [], []
            page.on(
                "pageerror",
                lambda e: (errs.append(str(e)), print("Page error:", e, flush=True)),
            )
            ctx.on(
                "request",
                lambda r: (
                    net.append(r.url)
                    if r.url.startswith(("http:", "https:"))
                    and not r.url.startswith(url + "/")
                    else None
                ),
            )
            page.goto(url)
            page.get_by_role("link", name="用自己的图文开始", exact=True).first.click()
            page.get_by_label("原文输入方式").select_option("file")
            page.get_by_label("原文 TXT 文件").set_input_files(
                {"name": title + ".txt", "mimeType": "text/plain", "buffer": source}
            )
            page.get_by_label("原文权利状态").select_option("local_test")
            page.get_by_role("button", name="新建项目，先配朗读").click()
            select = page.get_by_label("朗读对应的原文段落")
            select.select_option(index=1)
            project = parse_qs(urlparse(page.url).query)["studio"][0]
            base = url + "/api/projects/" + project
            assert ctx.request.get(base + "/source").body() == source
            expect(page.get_by_label("朗读原文")).to_have_text(source.decode())
            page.get_by_label("选择本机录音").set_input_files(audio)
            page.get_by_label("录音来源与使用许可").fill(credit)
            page.get_by_label("在阅读包中公开上面整条").check()
            page.get_by_role("button", name="存为待审录音").click()
            audition = page.get_by_label("试听待审段落朗读")
            audition.wait_for()
            accept = page.get_by_role("button", name="已对照原文，采用此朗读")
            expect(accept).to_be_disabled()
            assert (
                not ctx.request.get(base + "/reader/content")
                .json()["blocks"][0]
                .get("narration")
            )
            audition.evaluate("a => a.play()")
            expect(accept).to_be_enabled(timeout=125000)
            accept.click()
            page.get_by_label("已采用的段落朗读").wait_for()
            mark(
                "Fresh project, image-free path, exact source; pending silence, full native playback and deliberate acceptance."
            )

            if subtitle:
                # An edition note, not poem text or a project-name trigger in
                # the reader. Use the ordinary editable/public subtitle field.
                studio_url = page.url
                page.get_by_role("link", name="返回完整工作台").click()
                page.get_by_role("button", name="独立阅读器与导出").click()
                page.get_by_text("编辑封面、场景与人物", exact=True).click()
                page.get_by_label("副标题", exact=True).fill(subtitle)
                with page.expect_response(
                    lambda r: r.url == base + "/reader" and r.request.method == "PATCH"
                ) as saved:
                    page.get_by_role("button", name="保存阅读器配置").click()
                assert saved.value.ok, saved.value.text()
                assert (
                    ctx.request.get(base + "/reader").json()["config"]["subtitle"]
                    == subtitle
                )
                page.goto(studio_url)
                page.get_by_label("已采用的段落朗读").wait_for()

            def export(name):
                button = page.get_by_role("button", name="导出独立阅读器")
                expect(button).to_be_enabled()
                link = page.get_by_role("link", name="下载阅读器")
                old = link.get_attribute("href") if link.count() else None
                button.click()
                expect(link).to_be_visible(timeout=40000)
                if old:
                    expect(link).not_to_have_attribute("href", old, timeout=40000)
                with page.expect_download() as d:
                    link.click()
                zpath = out / (name + ".zip")
                d.value.save_as(zpath)
                extracted = out / name
                with zipfile.ZipFile(zpath) as z:
                    assert z.testzip() is None
                    assert z.read("storygal-source/original.txt") == source
                    content = json.loads(z.read("reader.json"))
                    assert credit in z.read("RIGHTS.txt").decode()
                    assert content["schema_version"] == 4
                    assert content["config"]["subtitle"] == subtitle
                    cue = content["blocks"][0]["narration"]
                    media = content["media"][cue["id"]]
                    assert (
                        media["credit"] == credit
                        and media["origin"] == "paragraph_narration"
                    )
                    assert content["blocks"][0]["text"] == source.decode()
                    assert sum(x.endswith(".wav") for x in z.namelist()) == 1
                    z.extractall(extracted)
                return extracted

            first = export("voice-only")

            def offline(folder, width, mobile, illustrated):
                context = browser.new_context(
                    offline=True,
                    viewport={"width": width, "height": 844},
                    reduced_motion="reduce" if mobile else "no-preference",
                    has_touch=mobile,
                    is_mobile=mobile,
                )
                pg = context.new_page()

                def stable_focus(trigger):
                    expect(trigger).to_be_focused()
                    # Scroll restoration runs in rAF. A fleeting focus on the
                    # opener immediately after Close is not a successful return.
                    pg.evaluate(
                        "() => new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(ok)))"
                    )
                    expect(trigger).to_be_focused()

                pg.on("pageerror", lambda e: errs.append(str(e)))
                requests = []
                pg.on("request", lambda r: requests.append(r.url))
                pg.goto((folder / "index.html").as_uri())
                # Reflow equivalent to 400%/short landscape. Desktop chromium
                # emulation is not a claim to cover physical assistive devices.
                for w, h in ((320, 256), (390, 260)):
                    pg.set_viewport_size({"width": w, "height": h})
                    title_node = pg.get_by_role("heading", level=1)
                    expect(title_node).to_be_visible()
                    if subtitle:
                        expect(pg.locator(".reader-cover-subtitle")).to_have_text(
                            subtitle
                        )
                    assert pg.evaluate("""() => {
                        const box = (s) => document.querySelector(s).getBoundingClientRect();
                        const head = box('.reader-cover-header'), copy = box('.reader-cover-copy');
                        const link = box('.reader-cover-header a');
                        return head.top >= 0 && head.bottom <= copy.top &&
                          box('.reader-cover-copy h1').top >= head.bottom &&
                          !!document.elementFromPoint(link.x + link.width / 2, link.y + link.height / 2)?.closest('.reader-cover-header a') &&
                          document.documentElement.scrollWidth === innerWidth
                    }""")
                    about = pg.get_by_role("button", name="素材与说明")
                    about.press("Enter")
                    expect(pg.get_by_label("段落朗读来源")).to_contain_text(credit)
                    pg.keyboard.press("Escape")
                    stable_focus(about)
                    pg.evaluate("window.scrollTo(0,0)")
                pg.set_viewport_size({"width": width, "height": 844})
                pg.get_by_role("button", name="素材与说明").click()
                expect(pg.get_by_label("段落朗读来源")).to_contain_text(credit)
                pg.keyboard.press("Escape")
                pg.get_by_role("button", name="开始阅读").click()
                doc = pg.get_by_label("连续阅读正文")
                expect(doc).to_be_visible()
                assert (
                    pg.locator(".reader-paragraph-text").first.text_content()
                    == source.decode()
                )
                assert not pg.locator(".reader-stage").count()
                assert doc.bounding_box()["width"] >= width * 0.90
                assert not [r for r in requests if r.split("?")[0].endswith(".wav")]
                assert pg.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                if illustrated and args.verse:
                    for check_width in (320, 390):
                        pg.set_viewport_size({"width": check_width, "height": 844})
                        # Read actual glyph rects to ensure source-separated couplets
                        # stay together, rather than asserting only a CSS setting.
                        shown = pg.locator("[data-source-start]").first.evaluate(
                            """e=>{const n=e.firstChild, lines=new Map();
                            for(let i=0;i<n.length;i++){const r=new Range();r.setStart(n,i);r.setEnd(n,i+1);
                            const y=r.getBoundingClientRect().top;lines.set(y,(lines.get(y)||'')+n.textContent[i]);}
                            return [...lines.values()].map(s=>s.trim())}"""
                        )
                        parts = source.decode().split(" ")
                        assert shown == [" ".join(parts[:2]), " ".join(parts[2:])], (
                            shown
                        )
                    pg.set_viewport_size({"width": width, "height": 844})
                if illustrated:
                    img = doc.get_by_role("img", name=alt)
                    expect(img).to_be_visible()
                    assert img.evaluate("e => e.complete && e.naturalWidth > 0")
                    assert not pg.locator("canvas").count()
                    trigger = pg.get_by_role(
                        "button", name="放大插图：" + caption, exact=True
                    )
                    trigger.press("Enter")
                    expect(pg.get_by_role("dialog")).to_be_visible()
                    pg.keyboard.press("Escape")
                    stable_focus(trigger)
                main_voice = pg.get_by_role(
                    "button", name="听这一段：第 1 段", exact=True
                )
                cue = json.loads((folder / "reader.json").read_text())["blocks"][0][
                    "narration"
                ]
                expect(main_voice).to_have_accessible_description(
                    f"朗读时长约 {math.ceil(cue['duration'])} 秒"
                )
                before = doc.evaluate("e=>e.scrollTop")
                pg.get_by_role("button", name="听这一段").click()
                for _ in range(45):
                    if pg.locator("audio").evaluate("e=>e.currentTime") > 0.15:
                        break
                    pg.wait_for_timeout(100)
                else:
                    raise AssertionError("Audio did not advance on an actual clock")
                pg.get_by_role("button", name="暂停朗读").click()
                assert pg.locator("audio").evaluate("a=>a.paused")
                pg.get_by_role("button", name="继续朗读").click()
                pg.get_by_role("button", name="停止朗读").press("Enter")
                stable_focus(main_voice)
                expect(pg.get_by_role("button", name="听这一段")).to_be_visible()
                assert abs(before - doc.evaluate("e=>e.scrollTop")) < 4
                assert not pg.get_by_text("已到本卷结尾。").count()
                assert not pg.get_by_role("navigation", name="阅读工具栏").count()
                pg.get_by_role("button", name="阅读工具", exact=True).click()
                settings = pg.get_by_role("button", name="设置", exact=True)
                settings.press("Enter")
                if illustrated:
                    gallery = pg.get_by_role(
                        "button", name="本章画卷 · 1 幅", exact=True
                    )
                    gallery.press("Enter")
                    expect(pg.get_by_role("dialog", name="本章画卷")).to_be_visible()
                    pg.keyboard.press("Escape")
                    stable_focus(gallery)
                pg.get_by_role("button", name="收起段落朗读入口").click()
                pg.keyboard.press("Escape")
                stable_focus(settings)
                assert not pg.get_by_role("button", name="听这一段").count()
                assert (
                    pg.locator(".reader-paragraph-text").first.text_content()
                    == source.decode()
                )
                assert not [r for r in requests if r.startswith(("http:", "https:"))]
                context.close()
                mark(
                    f"file:// offline {width}px: full-width text, explicit play/pause/resume/stop/hide, accessible duration, "
                    f"320×256/390×260 cover reflow, keyboard panel returns, no HTTP; plate={illustrated}."
                )

            offline(first, 1000, False, False)
            page.get_by_role("button", name="添加插图或返回底图制作").click()
            page.get_by_label("插图文件").set_input_files(art)
            page.get_by_label("图片来源与许可").fill(art_credit)
            page.get_by_role("button", name="上传为候选图").click()
            page.get_by_role("button", name="接受这张底图").click()
            page.get_by_label("插图名称").fill(caption)
            page.get_by_label("插图替代文字（可选）").fill(alt)
            page.get_by_label("放在此段之后").select_option(index=1)
            page.get_by_role("button", name="放置静图").click()
            page.locator("details.motion-director").wait_for()
            combined = export("reader")
            offline(combined, 390, True, True)
            page.get_by_text("备份可编辑工程", exact=True).click()
            with page.expect_download() as d:
                page.get_by_role("button", name="下载工程 ZIP").click()
            d.value.save_as(out / "project.zip")
            restored = ctx.request.post(
                url + "/api/project-bundles",
                multipart={
                    "file": {
                        "name": "project.zip",
                        "mimeType": "application/zip",
                        "buffer": (out / "project.zip").read_bytes(),
                    }
                },
            )
            assert restored.status == 201, restored.text()
            other = url + "/api/projects/" + restored.json()["id"]
            assert other != base and ctx.request.get(other + "/source").body() == source
            copied = ctx.request.get(other + "/reader/content").json()
            assert (
                copied["media"][copied["blocks"][0]["narration"]["id"]]["credit"]
                == credit
            )
            assert copied["config"]["illustrations"][0]["description"] == alt
            assert copied["config"]["subtitle"] == subtitle
            mark(
                "Editable backup restored with identical source, accepted reading and credit, illustration description, and cover subtitle."
            )
            assert not errs and not net, (errs, net)
            (out / "report.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "browser": browser.version,
                        "source_bytes": len(source),
                        "source_sha256": hashlib.sha256(source).hexdigest(),
                        "checks": checks,
                        "creator_external_requests": net,
                        "page_errors": errs,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            browser.close()


if __name__ == "__main__":
    main()
