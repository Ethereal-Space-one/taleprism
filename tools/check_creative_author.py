"""Exercise the three author decisions in the real UI, with synthetic local text only."""

import argparse
import json
import tempfile
from pathlib import Path

from check_passage_voice import ROOT, server
from playwright.sync_api import expect, sync_playwright


def run(backend, chromium, out):
    sample = ROOT / "examples/reading-lab/proof-strip"
    plan = json.loads((sample / "edition.json").read_text())
    out.mkdir(parents=True, exist_ok=False)
    with (
        tempfile.TemporaryDirectory() as tmp,
        server(backend, Path(tmp), out) as base,
        sync_playwright() as pw,
    ):
        browser = pw.chromium.launch(executable_path=chromium)
        context = browser.new_context(viewport={"width": 820, "height": 880})
        page = context.new_page()
        page.set_default_timeout(10000)
        bad = []
        page.on("pageerror", lambda exc: bad.append(str(exc)))
        page.on(
            "request",
            lambda r: (
                bad.append(r.url)
                if (
                    r.url.startswith(("http:", "https:"))
                    and not r.url.startswith(base + "/")
                )
                or r.url.endswith("/creative/propose")
                else None
            ),
        )
        page.goto(base + "/?studio=new")
        page.get_by_label("作品标题").fill(plan["title"])
        page.get_by_label("粘贴自己的原文").fill((sample / "source.txt").read_text())
        page.get_by_label("原文权利状态").select_option("owned")
        page.get_by_role("button", name="只保留原文，直接试读与导出").click()
        port = page.locator(".creative-desk")
        port.locator(":scope > summary").click()
        hide = port.locator(".creative-import").first
        hide.locator("summary").click()

        def submit(lens):
            port.get_by_role(
                "button",
                name={"sound": "声音", "image": "影像", "presentation": "呈现方式"}[
                    lens
                ],
                exact=True,
            ).click()
            port.get_by_label("导入本篇提案 JSON").set_input_files(
                str(sample / (lens + ".json"))
            )
            expect(port.get_by_role("region", name="候选提案")).to_be_visible()

        from urllib.parse import parse_qs, urlsplit

        pid = parse_qs(urlsplit(page.url).query)["studio"][0]
        api = base + "/api/projects/" + pid + "/reader"

        def saved():
            return context.request.get(api + "/content").json()

        submit("sound")
        port.get_by_role("button", name="制成待审试听，不采用").click()
        port.get_by_role("button", name="去试听这一段").click()
        assert not any(b.get("soundscape") for b in saved()["blocks"])
        ad = page.get_by_role("button", name="已对照原文，采用此声景")
        expect(ad).to_be_disabled()
        player = page.get_by_label("试听待审声景", exact=True)
        player.evaluate("a=>a.play()")
        expect(ad).to_be_enabled(timeout=20000)
        ad.click()
        expect(page.get_by_text("已采用", exact=False).first).to_be_visible()
        submit("image")
        port.get_by_text("上传有权使用的候选图", exact=True).click()
        port.get_by_label("候选图文件").set_input_files(str(sample / "plate.png"))
        port.get_by_label("来源与许可").fill(plan["credit"])
        port.get_by_role("button", name="保存候选图，不放置").click()
        accept = port.get_by_role("button", name="已看过这张图，接受底图")
        expect(accept).to_be_enabled()
        assert not saved()["config"]["illustrations"]
        accept.click()
        port.get_by_label("读者看见的图名").fill(plan["caption"])
        port.get_by_label("画面替代文字").fill(plan["alt"])
        port.get_by_role("button", name="采用静图，放在第 3 段后").click()
        expect(port.get_by_text("不会覆盖它", exact=False)).to_be_visible()
        submit("presentation")
        adopt = port.get_by_role("button", name="采用这处回声折页")
        expect(adopt).to_be_disabled()
        port.get_by_text("试翻折页：读到第 5 段时", exact=True).click()
        adopt.click()
        expect(port.get_by_role("button", name="这处折页已采用")).to_be_disabled()
        content = saved()
        assert content["config"]["echo_fold"] == {
            k: json.loads((sample / "presentation.json").read_text())["proposal"][k]
            for k in ("earlier", "later")
        }
        assert len(content["config"]["illustrations"]) == 1
        assert [
            i + 1 for i, b in enumerate(content["blocks"]) if b.get("soundscape")
        ] == [6]
        page.screenshot(path=str(out / "author.png"))
        withdrawal = port.locator(".creative-withdraw")
        withdrawal.locator("summary").click()
        withdrawal.get_by_role("button", name="从作品撤下这处折页").click()
        expect(withdrawal).to_have_count(0)
        content = saved()
        assert not content["config"].get("echo_fold") and len(content["media"]) == 2
        assert not bad, bad
        browser.close()
        print(
            "UI-only author path: 3 independent imports; full audition then adoption; actual image review then placement; preview, adopt & withdraw fold without disturbing other media. Zero provider/external requests."
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backend-python", default=str(ROOT / "backend/.venv/bin/python"))
    p.add_argument("--chromium")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    run(args.backend_python, args.chromium, args.output)
