"""Replay the stanza/quotation audit with real exported readers in offline Chromium.

Requires built frontend, synced backend, and Python Playwright. No active user projects.
"""

import argparse
import json
import tempfile
import time
import zipfile
from io import BytesIO
from itertools import pairwise
from pathlib import Path

from check_passage_voice import ROOT, server
from playwright.sync_api import expect, sync_playwright

LINES = [
    "岸上无声𠮷。",
    "　　船在第二行停下。",
    "",
    "第三行独成一节。",
    "    最后一行缩进四格。",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend-python", default=str(ROOT / "backend/.venv/bin/python"))
    ap.add_argument("--chromium")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    proofs = []
    with (
        tempfile.TemporaryDirectory(prefix="taleprism-spacing-") as temp,
        server(args.backend_python, Path(temp), out) as url,
        sync_playwright() as pw,
    ):
        browser = pw.chromium.launch(executable_path=args.chromium)
        for encoding, separator, prefix in [
            ("utf-8", "\r\n", "\ufeff"),
            ("gb18030", "\n", ""),
        ]:
            source = prefix + separator.join(LINES) + separator
            raw = source.encode(encoding)
            studio = browser.new_context()
            req = studio.request.post(
                url + "/api/projects",
                multipart={
                    "file": {
                        "name": "潮间.txt",
                        "mimeType": "text/plain",
                        "buffer": raw,
                    },
                    "rights_status": "owned",
                },
            )
            assert req.status == 201, req.text()
            base = url + "/api/projects/" + req.json()["id"]
            assert studio.request.post(base + "/reader/exports").status == 202
            for _ in range(100):
                job = studio.request.get(base + "/jobs").json()[0]
                if job["state"] not in ("queued", "running", "pending"):
                    break
                time.sleep(0.1)
            assert job["state"] == "completed", job
            saved = studio.request.get(url + job["result"]["download_url"])
            project = out / encoding
            with zipfile.ZipFile(BytesIO(saved.body())) as z:
                assert (
                    z.read("storygal-source/original.txt") == raw
                    and z.testzip() is None
                )
                z.extractall(project)
            studio.close()
            ctx = browser.new_context(
                offline=True, viewport={"width": 800, "height": 780}
            )
            pg = ctx.new_page()
            errors, net = [], []
            pg.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            pg.on(
                "request",
                lambda r, net=net: (
                    net.append(r.url) if r.url.startswith(("http:", "https:")) else None
                ),
            )
            pg.goto((project / "index.html").as_uri())
            pg.get_by_role("button", name="开始阅读").click()
            ps = pg.locator(".reader-paragraph-text")
            assert ps.all_text_contents() == [x for x in LINES if x]
            offsets = ps.evaluate_all("ps=>ps.map(p=>p.getBoundingClientRect().top)")
            d = [round(b - a, 2) for a, b in pairwise(offsets)]
            assert abs(d[0] - d[2]) < 1 and abs(d[1] - 2 * d[0]) < 2, d
            assert ps.first.evaluate("p => getComputedStyle(p).textIndent") == "0px"

            # A deterministic native DOM selection, matching a drag over the text.
            # Source spans deliberately exclude optional pictures and controls.
            def select(pg=pg):
                pg.locator("[data-source-start]").first.evaluate("""e=>{
                  const spans=document.querySelectorAll('[data-source-start]'), s=getSelection(), r=new Range();
                  r.setStart(spans[0].firstChild,0); const last=spans[spans.length-1].firstChild;
                  r.setEnd(last,last.length);s.removeAllRanges();s.addRange(r);
                  e.dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));
                }""")
                pg.get_by_role("button", name="保存原文摘录").click()
                pg.wait_for_timeout(350)
                return pg.evaluate(
                    "Object.entries(localStorage).filter(([k])=>k.startsWith('storygal-reader:')).map(([,v])=>JSON.parse(v))[0].marks.at(-1).text"
                )

            expected = separator.join(LINES)
            assert select() == expected
            pg.get_by_role("button", name="阅读工具", exact=True).click()
            pg.get_by_role("button", name="设置", exact=True).click()
            pg.get_by_label("文字排版").select_option("composed")
            pg.keyboard.press("Escape")
            expect(pg.locator(".uses-original-lines")).to_have_count(0)
            assert ps.first.evaluate("p => getComputedStyle(p).textIndent") != "0px"
            assert select() == expected
            pg.reload()
            pg.get_by_role("button", name="开始阅读").click()
            expect(pg.locator(".uses-original-lines")).to_have_count(0)
            pg.get_by_role("button", name="阅读工具", exact=True).click()
            pg.get_by_role("button", name="收藏", exact=True).click()
            marks = pg.get_by_role("button", name="摘录 ·", exact=False)
            expect(marks).to_have_count(2)
            assert (
                marks.first.text_content()
                .replace("\r\n", "\n")
                .endswith("\n".join(LINES))
            )
            assert not net and not errors, (net, errors)
            proofs.append(
                {
                    "encoding": encoding,
                    "source_bytes": len(raw),
                    "source_exact": True,
                    "line_top_deltas": d,
                    "quoted_bytes": len(expected.encode()),
                    "two_modes_and_reload_exact": True,
                }
            )
            ctx.close()
        (out / "report.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "chromium": browser.version,
                    "checks": proofs,
                    "no_external_requests": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print((out / "report.json").read_text(), flush=True)
        browser.close()


if __name__ == "__main__":
    main()
