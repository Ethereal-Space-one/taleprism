"""Browser cases for check_studio_browser.py; no existing project, credentials or publisher."""

from __future__ import annotations

import json
import time
import zipfile
from urllib.parse import parse_qs, urlsplit
from pathlib import Path

from playwright.sync_api import expect


def first_chapter(browser, base, out):
    source = (
        "雾醒来以前，轮渡站还没有人。\n细雨在车票上落下。\n乘客翻开票根，看见了蓝鸢。"
    )
    before = time.monotonic()
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844}, accept_downloads=True
    )
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base)
    page.get_by_role("link", name="用自己的图文开始", exact=True).first.click()
    page.get_by_text("第一次做？从自己的第一章到可分享读本", exact=True).click()
    expect(page.get_by_text("粘贴一章你有权分享的原文", exact=False)).to_be_visible()
    page.get_by_label("作品标题").fill("渡口手记")
    page.get_by_label("粘贴自己的原文").fill(source)
    options = page.get_by_role("group", name="这次想做什么？（可选）")
    for name in ["插图", "朗读", "声景"]:
        expect(options.get_by_role("checkbox", name=name, exact=True)).not_to_be_checked()
    trial = options.get_by_role("checkbox", name="插图", exact=True)
    trial.check()
    trial.uncheck()
    finish = page.get_by_role("button", name="只保留原文，直接试读与导出")
    finish.click()
    assert (
        "studio=new" in page.url
    )  # browser validation: rights intentionally not defaulted
    page.get_by_label("原文权利状态").select_option("owned")
    finish.click()
    page.get_by_text("段落试演与防剧透校对", exact=True).click()
    studio = page.locator(".passage-proof")
    key = parse_qs(urlsplit(page.url).query)["studio"][0]
    path = f"{base}/api/projects/{key}/reader"
    old = ctx.request.get(path).json()
    old_sound = ctx.request.get(path + "/soundscapes").json()
    studio.get_by_label("试演原文段落").select_option("1")
    expect(studio.locator("blockquote")).to_have_text(source.splitlines()[1])
    studio.get_by_role("button", name="局部动效", exact=True).click()
    expect(studio.get_by_text("本段没有落点插图", exact=False)).to_be_visible()
    studio.get_by_role("button", name="声景", exact=True).click()
    sound = studio.get_by_label("同段声景试听")
    sound.evaluate("a => a.play()")
    page.wait_for_function(
        "document.querySelector('.proof-choice audio').currentTime > 0.15"
    )
    studio.get_by_role("button", name="留白", exact=True).click()
    assert not studio.locator("audio").count()
    studio.get_by_label("读者检查位置").select_option("before")
    expect(studio.locator(".proof-review")).to_contain_text(source.splitlines()[0])
    expect(studio.locator(".proof-review")).not_to_contain_text(source.splitlines()[1])
    studio.get_by_label("可选：检查尚不应透露的名字或短语").fill("蓝鸢")
    expect(studio.get_by_role("status")).to_contain_text("未发现逐字匹配")
    studio.get_by_label("试演原文段落").select_option("2")
    expect(studio.get_by_role("status")).to_contain_text("未发现逐字匹配")
    studio.get_by_label("读者检查位置").select_option("after")
    expect(studio.get_by_role("status")).to_contain_text("已读原文")
    assert ctx.request.get(path).json() == old
    assert ctx.request.get(path + "/soundscapes").json() == old_sound
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.get_by_role("button", name="导出独立阅读器").click()
    with page.expect_download() as download:
        page.get_by_role("link", name="下载阅读器").click(timeout=30000)
    saved = out / "first-chapter-reader.zip"
    download.value.save_as(saved)
    with zipfile.ZipFile(saved) as z:
        assert (
            z.testzip() is None
            and z.read("storygal-source/original.txt") == source.encode()
        )
        packed = json.loads(z.read("reader.json"))
        assert not packed["media"]  # preview rain and editorial terms did not travel
        received = out / "first-chapter-recipient"
        z.extractall(received)
    other = browser.new_context(offline=True)
    reader = other.new_page()
    net = []
    other.on(
        "request",
        lambda r: net.append(r.url) if r.url.startswith(("https:", "http:")) else None,
    )
    reader.goto((received / "index.html").as_uri())
    reader.get_by_role("button", name="开始阅读").click()
    expect(reader.get_by_text(source.splitlines()[0], exact=True).first).to_be_visible()
    assert not net and not errors
    elapsed = round(time.monotonic() - before, 2)
    other.close()
    studio.get_by_label("试演原文段落").select_option("1")
    studio.get_by_role("button", name="声景", exact=True).click()
    studio.get_by_role("button", name="在这个段落编辑声景").click()
    expect(page.get_by_label("声景对应的原文段落")).to_have_value(
        str(old["paragraphs"][1]["byte_start"])
    )
    assert ctx.request.get(path + "/soundscapes").json() == old_sound
    panel = page.locator(".passage-soundscape")
    panel.get_by_label("原文依据", exact=True).fill("细雨")
    panel.get_by_role("button", name="生成待审声景").click()
    accept = panel.get_by_role("button", name="已对照原文，采用此声景")
    expect(accept).to_be_disabled()
    studio.get_by_role("button", name="声景", exact=True).click()
    expect(studio.get_by_text("试听样音：", exact=False)).to_be_visible()
    # This is a synthetic fixture for state transitions, not a human judgement of sound quality.
    panel.get_by_label("试听待审声景").evaluate("a => a.play()")
    expect(accept).to_be_enabled(timeout=30000)
    accept.click()
    expect(studio.get_by_text("试听本段已采用的声景。", exact=True)).to_be_visible()
    adopted = ctx.request.get(path + "/soundscapes").json()
    actual = next(t for t in adopted["takes"] if t["status"] == "accepted")
    expect(studio.get_by_label("同段声景试听")).to_have_attribute("src", actual["url"])
    studio.get_by_label("可选：检查尚不应透露的名字或短语").fill("细雨")
    expect(studio.get_by_role("status")).to_contain_text("声音标签")
    studio.get_by_label("读者检查位置").select_option("before")
    expect(studio.get_by_role("status")).to_contain_text("未发现逐字匹配")
    expect(studio.get_by_label("试听段落声景")).to_have_count(0)
    studio.get_by_role("button", name="留白", exact=True).click()
    assert ctx.request.get(path + "/soundscapes").json() == adopted
    cover = studio.get_by_role("region", name="卷首校样")
    expect(cover).to_contain_text("没有设置封面图")
    expect(cover).to_contain_text("把章名、副标题和封面图一起看")
    expect(cover).to_contain_text("有意预告不等于剧透")
    v = ctx.request.get(path).json()["revision"]
    reply = ctx.request.post(
        path + "/assets",
        multipart={"revision": str(v), "kind": "cover", "license_text": "repo fixture", "file": Path(__file__).resolve().parents[1] / "samples/last-light/arrival-v1.png"},
    )
    assert reply.ok, reply.text()
    state = ctx.request.get(path).json()
    aid = next(a["id"] for a in state["assets"] if a["kind"] == "cover")
    reply = ctx.request.patch(path + "/assets/" + aid, data={"revision": state["revision"], "status": "accepted"})
    assert reply.ok, reply.text()
    state = ctx.request.get(path).json()
    cfg = state["config"] | {
        "revision": state["revision"],
        "cover_asset_id": aid,
        "subtitle": "最后一班船",
    }
    reply = ctx.request.patch(path, data=cfg)
    assert reply.ok, reply.text()
    page.reload()
    page.get_by_text("段落试演与防剧透校对", exact=True).click()
    for moment in ["before", "after"]:
        studio.get_by_label("读者检查位置").select_option(moment)
        graphic = cover.get_by_role("img", name="渡口手记章节封面")
        expect(graphic).to_have_attribute("src", path.removeprefix(base) + "/assets/" + aid)
        expect(graphic).to_be_visible()
        expect(cover.get_by_text("最后一班船", exact=True)).to_be_visible()
        graphic.evaluate("(img) => img.decode()")
    page.route("**/reader/assets/" + aid, lambda route: route.abort())
    page.reload()
    page.get_by_text("段落试演与防剧透校对", exact=True).click()
    expect(cover).to_contain_text("已选封面图无法显示，不能视为已校对。")
    # Multi-select is routing only and survives a reload; it does not adopt or generate.
    another = ctx.new_page()
    another.goto(base + "/?studio=new")
    another.get_by_label("作品标题").fill("只勾选，不制作素材")
    another.get_by_label("粘贴自己的原文").fill(source)
    another.get_by_label("原文权利状态").select_option("owned")
    another.get_by_role("checkbox", name="声景", exact=True).check()
    another.get_by_role("checkbox", name="插图", exact=True).check()
    another.get_by_role("checkbox", name="朗读", exact=True).check()
    expect(another.get_by_text("先做声景，其他选项可在制作台接着做。")).to_be_visible()
    another.get_by_role("button", name="新建项目，开始制作").click()
    expect(another.get_by_text("这次想试：声景、插图、朗读", exact=False)).to_be_visible()
    assert parse_qs(urlsplit(another.url).query)["lane"] == ["sound"]
    another.reload()
    expect(another.get_by_text("这次想试：声景、插图、朗读", exact=False)).to_be_visible()
    another.get_by_role("button", name="朗读 →", exact=True).click()
    assert parse_qs(urlsplit(another.url).query)["lane"] == ["voice"]
    key = parse_qs(urlsplit(another.url).query)["studio"][0]
    data = ctx.request.get(f"{base}/api/projects/{key}/reader/content").json()
    assert data["media"] == {} and data["config"]["illustrations"] == []
    assert ctx.request.get(f"{base}/api/projects/{key}/reader/soundscapes").json()["takes"] == []
    another.get_by_role("button", name="导出独立阅读器").click()
    with another.expect_download() as selected_download:
        another.get_by_role("link", name="下载阅读器").click(timeout=30000)
    selected = out / "selected-without-assets.zip"
    selected_download.value.save_as(selected)
    with zipfile.ZipFile(selected) as z:
        assert z.read("storygal-source/original.txt") == source.encode()
        content = json.loads(z.read("reader.json"))
        assert content["media"] == {} and "plan" not in content
    assert not errors
    ctx.close()
    return {
        "scripted_seconds_from_home_to_clean_offline_recipient": elapsed,
        "independent_novice_timing": "not measured",
        "checks": [
            "own UTF-8 source exact; missing rights cannot advance",
            "all choices off by default; toggled-off choice still exports text-only",
            "multi-select resumes routing; unfinished choices do not block text-only export",
            "same passage, quiet / real WAV / no motion fallback",
            "preview and handoff never stage or adopt",
            "future phrase before and after",
            "pending excluded, accepted audio visible only when reached, quiet comparison does not withdraw it",
            "narrow viewport",
            "title, subtitle and cover read together before and after; missing image disclosed",
            "download, unpack, offline recipient, zero external requests",
        ],
    }


def inspect_placed(page, ctx, base, key, reviewed):
    path = f"{base}/api/projects/{key}/reader"
    state = ctx.request.get(path).json()
    plate = state["config"]["illustrations"][0]
    index = next(
        i
        for i, p in enumerate(state["paragraphs"])
        if p["byte_end"] == plate["after_byte"]
    )
    proof = page.locator(".passage-proof")
    proof.locator("summary").click()
    proof.get_by_label("试演原文段落").select_option(str(index))
    proof.get_by_role("button", name="局部动效", exact=True).click()
    audit = proof.locator(".proof-review")
    term = plate["title"]
    proof.get_by_label("可选：检查尚不应透露的名字或短语").fill(term)
    expect(audit.get_by_role("status")).to_contain_text("已解锁画卷标题")
    proof.get_by_label("读者检查位置").select_option("before")
    assert not audit.locator("figure").count()
    expect(audit.get_by_role("status")).not_to_contain_text("已解锁画卷标题")
    play = proof.get_by_role("button", name="试演已复核动效", exact=True)
    if reviewed:
        play.click()
        proof.locator(".proof-plate").scroll_into_view_if_needed()
        expect(proof.locator("canvas")).to_be_visible()
        page.emulate_media(reduced_motion="reduce")
        expect(proof.locator("canvas")).to_be_hidden()
        page.emulate_media(reduced_motion="no-preference")
    else:
        assert not play.count()
        expect(proof.get_by_text("没有可播放的已复核动效", exact=False)).to_be_visible()
    proof.locator("summary").click()
    assert ctx.request.get(path).json() == state
