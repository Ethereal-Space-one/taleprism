"""Exercise a fresh workbench and its ordinary offline reader via real Chromium.

Optional QA dependency: Playwright for Python (install chromium or pass --chromium).
First build frontend, sync backend. This creates only a new temporary data directory.
The output folder must be new. No user files, model calls or network services.
"""

import argparse
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright
from studio_first_chapter_cases import first_chapter, inspect_placed

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def assert_no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (
        page.url
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chromium", help="Browser executable, or use installed Playwright Chromium"
    )
    parser.add_argument(
        "--backend-python", default=str(ROOT / "backend/.venv/bin/python")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = (ROOT / "samples/last-light/source.txt").read_bytes()
    artwork = ROOT / "samples/last-light/arrival-v1.png"
    report = {
        "passed": False,
        "source_sha256": sha(source),
        "checks": [],
        "host_system": platform.system(),
        "host_machine": platform.machine(),
        "limits": "Scripted creator using a real desktop browser. Narrow touch viewport is emulated; no physical phone or independent human art review.",
    }

    def mark(text):
        report["checks"].append(text)
        print(text, flush=True)

    with tempfile.TemporaryDirectory(prefix="taleprism-studio-check-") as store:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        env = {
            **os.environ,
            "STORYGAL_DATA_DIR": store,
            "PYTHONPATH": str(ROOT / "backend/src"),
            "DEEPSEEK_API_KEY": "",
            "OPENAI_API_KEY": "",
        }
        with (out / "server.log").open("w") as log:
            svc = subprocess.Popen(
                [
                    args.backend_python,
                    "-m",
                    "uvicorn",
                    "storygal.app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                env=env,
                cwd=ROOT,
                stdout=log,
                stderr=log,
            )
            try:
                for _ in range(120):
                    try:
                        with urllib.request.urlopen(url + "/api/health", timeout=0.5):
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError(
                        "Isolated workbench did not start; see server.log"
                    )
                with sync_playwright() as pw:
                    b = pw.chromium.launch(executable_path=args.chromium, headless=True)
                    report["browser"] = b.version
                    ctx = b.new_context(
                        viewport={"width": 1280, "height": 900}, accept_downloads=True
                    )
                    errors = []
                    external = []
                    ctx.on(
                        "page",
                        lambda pg: pg.on(
                            "pageerror", lambda err: errors.append(str(err))
                        ),
                    )
                    ctx.on(
                        "request",
                        lambda req: (
                            external.append(req.url)
                            if req.url.startswith(("http:", "https:"))
                            and not req.url.startswith(url + "/")
                            else None
                        ),
                    )
                    pg = ctx.new_page()
                    pg.set_default_timeout(10000)
                    report["author_first_chapter"] = first_chapter(b, url, out)
                    pg.goto(url)
                    pg.get_by_role(
                        "link", name="用自己的图文开始", exact=True
                    ).first.click()
                    pg.get_by_label("原文输入方式").select_option("file")
                    pg.get_by_label("原文 TXT 文件").set_input_files(
                        {
                            "name": "末班灯.txt",
                            "mimeType": "text/plain",
                            "buffer": source,
                        }
                    )
                    pg.get_by_label("原文权利状态").select_option("authorized")
                    pg.get_by_role("checkbox", name="插图", exact=True).check()
                    pg.get_by_role("button", name="新建项目，开始制作").click()
                    pg.get_by_label("插图文件").wait_for()
                    current = parse_qs(urlsplit(pg.url).query)["studio"][0]
                    assert (
                        current != "new"
                        and ctx.request.get(
                            url + "/api/projects/" + current + "/source"
                        ).body()
                        == source
                    )
                    pg.reload()
                    pg.get_by_label("插图文件").wait_for()
                    mark(
                        f"New project and reload: exact {len(source):,} original bytes, no sample download."
                    )
                    pg.get_by_label("插图文件").set_input_files(artwork)
                    pg.get_by_label("图片来源与许可").fill(
                        "公开示例《末班灯》，Taleprism samples/last-light/arrival-v1.png，MIT；来源与生成记录见 samples/last-light/PROVENANCE.md。"
                    )
                    pg.get_by_role("button", name="上传为候选图").click()
                    pg.get_by_role("button", name="接受这张底图").wait_for()
                    place = pg.get_by_role("button", name="放置静图")
                    expect(place).to_be_disabled()
                    pg.get_by_role("button", name="接受这张底图").click()
                    pg.get_by_label("插图名称").fill("旧站台 · 斜雨")
                    pg.get_by_label("放在此段之后").select_option(index=2)
                    place.click()
                    director = pg.locator("details.motion-director")
                    expect(director).to_have_attribute("open", "")
                    review = director.get_by_role("checkbox")
                    expect(review).to_be_disabled()
                    mark(
                        "Loaded candidate needed its own acceptance and a real paragraph before static placement."
                    )
                    director.get_by_label("逐字原文依据", exact=False).fill(
                        "傍晚的雨斜着落进站台"
                    )
                    director.get_by_label("画面观察与保护范围", exact=False).fill(
                        "雨只落在右侧海面、铁轨及临轨湿地，避开站灯、屋檐、林遥与陈伯。"
                    )
                    svg = director.locator(".motion-director-map svg")

                    def polygon(points):
                        svg.scroll_into_view_if_needed()
                        box = svg.bounding_box()
                        for x, y in points:
                            svg.click(
                                position={"x": x * box["width"], "y": y * box["height"]}
                            )
                        director.get_by_role("button", name="闭合并加入范围").click()

                    polygon(
                        [
                            (0.82, 0.26),
                            (0.91, 0.19),
                            (0.974, 0.03),
                            (0.993, 0.03),
                            (0.993, 0.98),
                            (0.92, 0.98),
                            (0.845, 0.73),
                            (0.807, 0.56),
                        ]
                    )
                    director.get_by_role("button", name="标接雨湿地").click()
                    polygon(
                        [
                            (0.83, 0.7),
                            (0.85, 0.73),
                            (0.915, 0.956),
                            (0.884, 0.95),
                            (0.846, 0.816),
                        ]
                    )
                    rings = director.get_by_role("slider").last
                    rings.focus()
                    rings.press("Home")
                    rings.press("ArrowRight")
                    rings.press("ArrowRight")
                    rings.press("ArrowRight")
                    queued = director.get_by_role("button", name="纳入章节草稿")
                    expect(queued).to_be_enabled()
                    export = pg.get_by_role("button", name="导出独立阅读器")
                    expect(export).to_be_disabled()
                    queued.click()
                    save = pg.get_by_role("button", name="保存章节编排")
                    save.click()
                    expect(export).to_be_enabled()
                    pg.reload()
                    expect(review).not_to_be_checked()
                    read_state = ctx.request.get(
                        f"{url}/api/projects/{current}/reader"
                    ).json()
                    assert (
                        read_state["config"]["illustrations"][0]["motion"]["reviewed"]
                        is False
                    )
                    mark(
                        "Unreviewed saved draft stays static after reload; pending edits blocked export."
                    )
                    inspect_placed(pg, ctx, url, current, reviewed=False)
                    director.get_by_role("button", name="打开动效对照").click()
                    motion = director.get_by_role("button", name="开启动效")
                    expect(motion).to_have_attribute("aria-pressed", "false")
                    motion.click()
                    preview = director.locator(
                        ".motion-director-preview .reader-image-viewport"
                    )
                    preview.scroll_into_view_if_needed()
                    progress = director.get_by_role("progressbar")
                    pg.wait_for_function(
                        "document.querySelector('.motion-director progress').value >= 1"
                    )
                    expect(review).to_be_disabled()
                    pg.evaluate("scrollTo(0,0)")
                    pg.wait_for_timeout(300)
                    partial = progress.evaluate("p => p.value")
                    pg.wait_for_timeout(1250)
                    assert progress.evaluate("p => p.value") == partial
                    preview.scroll_into_view_if_needed()
                    expect(review).to_be_enabled(timeout=35000)
                    assert progress.evaluate("p => p.value") == 8
                    pixels = sample_overlay(preview.locator("canvas"))
                    assert pixels["inside"] > 0 and pixels["protected"] == 0, pixels
                    director.locator(".motion-director-comparison").screenshot(
                        path=str(out / "creator-comparison.png")
                    )
                    review.check()
                    queued.click()
                    save.click()
                    expect(export).to_be_enabled()
                    mark(
                        "Real canvas: eight visible rendered seconds, offscreen time paused, compare/attest/save. Protected subjects stayed clear."
                    )
                    report["author_canvas"] = pixels
                    inspect_placed(pg, ctx, url, current, reviewed=True)
                    mark(
                        "Proof desk: pending motion stayed static; accepted clip rendered on real image, reduced motion suppressed it; gallery/captions obeyed the byte boundary."
                    )
                    export.click()
                    link = pg.get_by_role("link", name="下载阅读器")
                    with pg.expect_download() as down:
                        link.click(timeout=30000)
                    archive = out / "studio-reader.zip"
                    down.value.save_as(archive)
                    with zipfile.ZipFile(archive) as z:
                        assert z.testzip() is None
                        assert z.read("storygal-source/original.txt") == source
                        content = json.loads(z.read("reader.json"))
                        assert (
                            content["config"]["illustrations"][0]["motion"]["reviewed"]
                            is True
                        )
                        z.extractall(out / "extracted")
                    subprocess.run(
                        [
                            sys.executable,
                            str(ROOT / "tools/verify_package.py"),
                            str(out / "extracted"),
                        ],
                        check=True,
                    )
                    pg.get_by_text("备份可编辑工程", exact=True).click()
                    with pg.expect_download() as editable:
                        pg.get_by_role("button", name="下载工程 ZIP").click()
                    editable.value.save_as(out / "studio-project.zip")
                    restored = ctx.request.post(
                        url + "/api/project-bundles",
                        multipart={
                            "file": {
                                "name": "studio-project.zip",
                                "mimeType": "application/zip",
                                "buffer": (out / "studio-project.zip").read_bytes(),
                            }
                        },
                    )
                    assert restored.status == 201, restored.text()
                    copy_id = restored.json()["id"]
                    assert copy_id != current
                    assert (
                        ctx.request.get(
                            url + "/api/projects/" + copy_id + "/source"
                        ).body()
                        == source
                    )
                    copy = ctx.new_page()
                    copy.goto(url + "/?studio=" + copy_id)
                    expect(copy.locator("details.motion-director")).to_be_visible()
                    expect(
                        copy.locator("details.motion-director").get_by_role("checkbox")
                    ).to_be_checked()
                    copy.close()
                    mark(
                        "Reader exported; editable ZIP restored into a second project in studio view with identical source and reviewed motion."
                    )
                    assert not external, external
                    report["creator_external_requests"] = external
                    ctx.close()
                    for mobile, reduced in [(False, False), (True, True)]:
                        ctx = b.new_context(
                            viewport={
                                "width": 390 if mobile else 1280,
                                "height": 844 if mobile else 900,
                            },
                            has_touch=mobile,
                            is_mobile=mobile,
                            reduced_motion="reduce" if reduced else "no-preference",
                            offline=True,
                        )
                        page = ctx.new_page()
                        reqs = []
                        page.on(
                            "request",
                            lambda req, requests=reqs: requests.append(req.url),
                        )
                        page.on("pageerror", lambda err: errors.append(str(err)))
                        page.goto((out / "extracted/index.html").as_uri())
                        # Manual mode: reviewed motion is available but not running.
                        page.get_by_role("button", name="安静阅读", exact=True).click()
                        plate = page.get_by_role("button", name="放大插图：旧站台")
                        page.get_by_label("连续阅读正文").wait_for()
                        assert_no_overflow(page)
                        plate.scroll_into_view_if_needed()
                        expect(plate.locator("img")).to_be_visible()
                        assert not page.locator("canvas").count(), (
                            "inline plate animated"
                        )
                        plate.click()
                        btn = page.get_by_role("button", name="开启动效")
                        expect(btn).to_have_attribute("aria-pressed", "false")
                        canvas = page.locator("dialog[open] canvas")
                        assert not canvas.is_visible()
                        if reduced:
                            expect(btn).to_be_disabled()
                            page.screenshot(path=str(out / "reader-narrow-reduced.png"))
                        else:
                            btn.click()
                            expect(canvas).to_be_visible()
                            for _ in range(20):
                                m = sample_overlay(canvas)
                                if m["inside"] > 0:
                                    break
                                page.wait_for_timeout(100)
                            assert m["inside"] > 0 and m["protected"] == 0, m
                            report["reader_canvas"] = m
                            page.screenshot(path=str(out / "reader-desktop.png"))
                            page.emulate_media(reduced_motion="reduce")
                            expect(canvas).to_be_hidden()
                            expect(btn).to_be_disabled()
                            page.emulate_media(reduced_motion="no-preference")
                            expect(btn).to_be_enabled()
                            expect(btn).to_have_attribute("aria-pressed", "false")
                        page.get_by_role("button", name="关闭面板", exact=True).click()
                        assert not any(
                            r.startswith(("https:", "http:")) for r in reqs
                        ), reqs
                        ctx.close()
                    assert not errors, errors
                    mark(
                        "Extracted file://, network offline: opened first passage, expanded plate static, opted in, runtime reduction stopped it, narrow touch + reduced-motion stayed static; zero HTTP(S) requests/page errors."
                    )
                    b.close()
            finally:
                svc.terminate()
                svc.wait(timeout=10)
                (out / "check.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2)
                )
    report["passed"] = True
    (out / "check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


def sample_overlay(canvas):
    return canvas.evaluate("""c => {
      const {width:w,height:h}=c;
      const a=c.getContext('2d').getImageData(0,0,w,h).data;
      let inside=0,protectedPixels=0;
      for(let y=0;y<h;y++)for(let x=0;x<w;x++){
        if(!a[(y*w+x)*4+3])continue;
        if(x/w>.78)inside++;
        if(x/w<.7)protectedPixels++;
      }
      return {width:w,height:h,inside,protected:protectedPixels}
    }""")


if __name__ == "__main__":
    main()
