"""Walk real Reader ZIPs built from the two public Reading Lab fixtures offline.

Use --static-reader and --motion-reader with reader.zip from check_creative_edition
and check_soundscape_browser respectively. Does not override browser autoplay.
"""

import argparse
import json
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from reissue_autoplay import inspect_story, loadzip


def check(browser, book, folder, width, quiet=False, reduce=False, muted=False):
    ctx = browser.new_context(
        viewport={"width": width, "height": 844 if width < 700 else 800},
        has_touch=width < 700,
        reduced_motion="reduce" if reduce else "no-preference",
        offline=True,
    )
    ctx.add_init_script("""window.observed={play:[]};
        addEventListener('playing',e=>{if(e.target.tagName==='AUDIO')
          observed.play.push(e.target.currentSrc.split('/').pop())},true);""")
    page = ctx.new_page()
    errors, external = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on(
        "request",
        lambda r: (
            external.append(r.url) if r.url.startswith(("http:", "https:")) else None
        ),
    )
    page.goto((folder / "index.html").as_uri())
    start = page.get_by_role(
        "button", name="安静阅读" if quiet else "开始阅读 →", exact=True
    )
    start.wait_for()
    # Real unactivated cover: only a read of DOM text, no JS evaluation or click.
    assert not page.locator(
        "audio[src],canvas.reader-inline-motion,.reader-echo-leaf"
    ).count()
    start.click()
    if muted:
        page.get_by_role("button", name="全部静音", exact=True).click()
    if quiet:
        page.get_by_role("button", name="继续自动演绎", exact=True).wait_for()
    root = page.locator(".reader-scroll")
    bounds = root.bounding_box()
    page.mouse.move(
        bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] * 0.57
    )
    page.wait_for_timeout(750)
    assert not page.locator(".reader-echo-leaf").count(), (
        "future reference revealed at start"
    )
    events, pixels, dry, max_clock, fold = [], 0, 0, 0, ""
    for i in range(100):
        snap = page.evaluate("""() => {const a=document.querySelector('audio'), c=document.querySelector('canvas.reader-inline-motion:not([hidden])');
            let wet=0,dry=0;if(c){const p=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
            for(let i=3;i<p.length;i+=4)if(p[i])((i-3)/4%c.width<c.width/2)?dry++:wet++}
            const root=document.querySelector('.reader-scroll');
            return [observed.play,wet,dry,a&&!a.paused?a.currentTime:0,document.querySelector('.reader-echo-leaf blockquote')?.textContent||'',root.scrollTop,root.scrollHeight-root.clientHeight]}""")
        events = snap[0]
        pixels = max(pixels, snap[1])
        dry = max(dry, snap[2])
        max_clock = max(max_clock, snap[3])
        fold = fold or snap[4]
        if (
            book == "rain-grid"
            and not (reduce or quiet)
            and pixels
            and max_clock > 0.08
        ):
            break
        if snap[5] >= snap[6] - 2 and i > 0:
            page.wait_for_timeout(1200)
            # Never scroll to reveal an effect. Either everything is observable
            # by the ordinary walk, or at the bottom the author chose silence.
            if (
                quiet
                or (book == "rain-grid" and (reduce or muted))
                or (book == "proof-strip" and fold and (muted or max_clock > 0.08))
            ):
                break
        page.mouse.wheel(0, 64)
        page.wait_for_timeout(430)
    assert not page.locator("dialog[open]").count() and dry == 0
    if quiet:
        assert not events and not pixels and not fold
    elif book == "rain-grid":
        assert not pixels if reduce else pixels > 0, (book, width, pixels)
        assert not events if muted else len(events) == 1 and max_clock > 0.08, (
            book,
            width,
            events,
            max_clock,
        )
    else:
        assert not pixels and fold == "先看边线"
        assert not events if muted else len(events) == 1 and max_clock > 0.08, (
            book,
            width,
            events,
            fold,
        )
    before = len(events)
    if not quiet:
        page.get_by_role("button", name="暂停自动演绎", exact=True).click()
        assert page.locator("audio").evaluate("a=>a.paused")
        assert not page.locator("canvas.reader-inline-motion:not([hidden])").count()
    # Reverse across already seen lines, then explicitly restore: no catch-up.
    page.mouse.wheel(0, -230)
    page.wait_for_timeout(500)
    page.get_by_role("button", name="继续自动演绎", exact=True).click()
    page.mouse.wheel(0, 800)
    page.wait_for_timeout(600)
    assert page.evaluate("observed.play.length") == before
    page.reload()
    resume = page.get_by_role("button", name=r"继续阅读 →", exact=True)
    if not resume.count():
        resume = page.get_by_role("button", name="开始阅读 →", exact=True)
    resume.click()
    page.wait_for_timeout(1150)
    assert (
        page.evaluate("observed.play.length") == 0
        and not page.locator(
            "canvas.reader-inline-motion:not([hidden]),.reader-echo-leaf"
        ).count()
    ), "restore replayed an encounter"
    if muted:
        assert page.get_by_role("button", name="取消静音", exact=True).count() == 1
    assert not errors and not external, (errors, external)
    print(
        json.dumps(
            {
                "edition": book,
                "width": width,
                "quiet": quiet,
                "muted": muted,
                "reduce": reduce,
                "play": events,
                "native_playhead": round(max_clock, 2),
                "wet_pixels": pixels,
                "protected_pixels": dry,
                "fold": fold,
                "silence_on_restore": True,
                "http_requests": len(external),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    ctx.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--static-reader", type=Path, required=True)
    p.add_argument("--motion-reader", type=Path, required=True)
    p.add_argument("--chromium")
    p.add_argument("--case", type=int)
    a = p.parse_args()
    with tempfile.TemporaryDirectory() as t, sync_playwright() as pw:
        samples = Path(__file__).resolve().parents[1] / "examples/reading-lab"
        for k, path in (
            ("rain-grid", a.motion_reader),
            ("proof-strip", a.static_reader),
        ):
            files, _ = loadzip(path.read_bytes())
            inspect_story(files)
            assert (
                files["storygal-source/original.txt"]
                == (samples / k / "source.txt").read_bytes()
            )
            for rel, raw in files.items():
                dest = Path(t) / k / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
        b = pw.chromium.launch(
            executable_path=a.chromium, ignore_default_args=["--mute-audio"]
        )
        print("Browser", b.version, flush=True)
        cases = [
            ("rain-grid", 390, False, False, False),
            ("proof-strip", 390, False, False, False),
            ("rain-grid", 1260, False, True, False),
            ("proof-strip", 1260, False, False, True),
            ("rain-grid", 390, True, False, False),
            ("proof-strip", 390, True, False, False),
        ]
        for i, (book, width, quiet, reduce, muted) in enumerate(cases):
            if a.case is None or i == a.case:
                check(b, book, Path(t) / book, width, quiet, reduce, muted)
        b.close()


if __name__ == "__main__":
    main()
