"""Fixed sample fetch boundaries and a fully local, isolated editing-copy flow."""

import hashlib
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from storygal import guided_sample as sample
from storygal.app import create_app


def transport(monkeypatch, handler):
    client = httpx.Client
    settings = []

    def mocked(**kwargs):
        settings.append(kwargs)
        return client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(sample.httpx, "Client", mocked)
    return settings


def pin(monkeypatch, raw):
    """Test-only pin injection, never an app setting or request parameter."""
    monkeypatch.setattr(sample, "ARCHIVE_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(sample, "_spec", lambda: {"title": "isolated sample"})


def minimal_bundle(tmp_path):
    app = create_app(tmp_path / "seed")
    project = app.state.store.create(
        "完整原文。\n这是一份练习。".encode(), "练习.txt", "owned", "utf-8"
    )
    return app.state.bundles.export(project["id"])


def test_published_catalog_matches_code_pin():
    spec = sample._spec()
    assert spec["download_url"] == sample.ARCHIVE_URL
    assert spec["sha256"] == sample.ARCHIVE_SHA256
    assert spec["file"] == sample.ARCHIVE_FILE


def test_fixed_download_hash_redirect_and_client_boundaries(monkeypatch):
    raw = b"pinned bytes"
    pin(monkeypatch, raw)
    urls = []

    def respond(request):
        urls.append(str(request.url))
        assert not request.headers.get("authorization")
        assert request.headers["accept-encoding"] == "identity"
        if len(urls) == 1:
            return httpx.Response(
                302, headers={"location": "https://release-assets.githubusercontent.com/fixed.zip"}
            )
        return httpx.Response(200, content=raw)

    settings = transport(monkeypatch, respond)
    assert sample._download() == raw
    assert urls == [sample.ARCHIVE_URL, "https://release-assets.githubusercontent.com/fixed.zip"]
    assert settings[0]["follow_redirects"] is False
    assert settings[0]["trust_env"] is False


@pytest.mark.parametrize(
    "url",
    [
        "http://release-assets.githubusercontent.com/a",
        "https://evil.invalid/a",
        "https://release-assets.githubusercontent.com.evil.invalid/a",
        "https://127.0.0.1/a",
        "https://user:password@release-assets.githubusercontent.com/a",
        "https://release-assets.githubusercontent.com:444/a",
    ],
)
def test_rejects_untrusted_redirect_before_request(monkeypatch, url):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": url})

    transport(monkeypatch, respond)
    with pytest.raises(ValueError, match="重定向"):
        sample._download()
    assert len(requests) == 1


def test_redirect_count_is_bounded(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://objects.githubusercontent.com/a"})

    transport(monkeypatch, respond)
    with pytest.raises(ValueError, match="重定向"):
        sample._download()
    assert len(requests) == sample.MAX_REDIRECTS + 1


@pytest.mark.parametrize(
    "headers,raw,reason",
    [
        ({"content-length": "25000001"}, b"", "大小"),
        ({"content-length": "invalid"}, b"", "大小"),
        ({}, b"wrong content", "校验"),
    ],
)
def test_length_and_digest_fail_closed(monkeypatch, headers, raw, reason):
    transport(monkeypatch, lambda _: httpx.Response(200, headers=headers, content=raw))
    with pytest.raises(ValueError, match=reason):
        sample._download()


def test_streamed_limit_without_content_length(monkeypatch):
    monkeypatch.setattr(sample, "MAX_ARCHIVE_BYTES", 8)
    transport(monkeypatch, lambda _: httpx.Response(200, content=b"too many bytes"))
    with pytest.raises(ValueError, match="大小"):
        sample._download()


def test_download_deadline(monkeypatch):
    times = iter([0, sample.DOWNLOAD_SECONDS + 1])
    monkeypatch.setattr(sample.time, "monotonic", lambda: next(times))
    transport(monkeypatch, lambda _: pytest.fail("deadline must stop before request"))
    with pytest.raises(ValueError, match="超时"):
        sample._download()


def test_cache_is_hash_checked_and_opens_new_copies(tmp_path, monkeypatch):
    raw = minimal_bundle(tmp_path)
    pin(monkeypatch, raw)
    calls = []
    monkeypatch.setattr(sample, "_download", lambda: calls.append(True) or raw)
    app = create_app(tmp_path / "workspace")
    original = app.state.store.create("不能改动的原作。".encode(), "原作.txt", "owned", "utf-8")
    client = TestClient(app)
    assert client.get("/api/samples/last-light/guided").json()["cached"] is False
    first = client.post("/api/samples/last-light/guided")
    assert first.status_code == 201, first.text
    second = client.post("/api/samples/last-light/guided")
    assert second.status_code == 201, second.text
    assert first.json()["id"] != second.json()["id"] != original["id"]
    assert first.json()["guided_shot_id"] == "negotiation"
    assert calls == [True]
    assert client.get("/api/samples/last-light/guided").json()["cached"] is True
    assert app.state.store.get(original["id"]) == original
    assert (
        client.get(f"/api/projects/{original['id']}/source").content == "不能改动的原作。".encode()
    )
    cached = next((app.state.store.root / "sample-cache").glob("*.zip"))
    cached.write_bytes(b"corrupted cache")
    assert client.get("/api/samples/last-light/guided").json()["cached"] is False
    assert client.post("/api/samples/last-light/guided").status_code == 201
    assert calls == [True, True]


def test_fetch_failure_does_not_create_or_modify_projects(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    client = TestClient(app)
    original = app.state.store.create("保留我的原文。".encode(), "原作.txt", "owned", "utf-8")

    def failed():
        raise ValueError("公开样例校验未通过。" + sample.FALLBACK)

    monkeypatch.setattr(sample, "_download", failed)
    response = client.post("/api/samples/last-light/guided", json={"url": "https://evil.invalid"})
    assert response.status_code == 400
    assert "手动导入与原文练习" in response.json()["detail"]
    assert app.state.store.list_projects() == [original]


@pytest.mark.content_pack
@pytest.mark.skipif(
    not os.environ.get("TALEPRISM_TEST_LAST_LIGHT_ARCHIVE"), reason="optional local full sample"
)
def test_complete_local_sample_keeps_all_media_and_plan(tmp_path, monkeypatch):
    raw = Path(os.environ["TALEPRISM_TEST_LAST_LIGHT_ARCHIVE"]).read_bytes()
    # Local rebuilt fixtures are not the published ZIP. Override pin only in this test.
    pin(monkeypatch, raw)
    monkeypatch.setattr(sample, "_download", lambda: raw)
    app = create_app(tmp_path)
    client = TestClient(app)
    response = client.post("/api/samples/last-light/guided")
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    production = client.get(f"/api/projects/{pid}/production").json()
    assert [s["id"] for s in production["plan"]["shots"]] == ["arrival", "negotiation", "recording"]
    assert len(production["plan"]["scenes"]) == 1
    reader = client.get(f"/api/projects/{pid}/reader").json()
    assert len(reader["assets"]) == 4
    assert len(reader["config"]["illustrations"]) == 3
    assert len(client.get(f"/api/projects/{pid}/review").json()["characters"]) == 3
    assert (
        client.get(f"/api/projects/{pid}/source").content
        == (sample.REPO / "samples/last-light/source.txt").read_bytes()
    )
    assert list((app.state.store.root / "sample-cache").glob("*.zip"))


@pytest.mark.content_pack
@pytest.mark.skipif(
    not os.environ.get("TALEPRISM_TEST_PINNED_LAST_LIGHT_ARCHIVE"),
    reason="optional exact public archive",
)
def test_exact_published_sample_opens_from_verified_cache(tmp_path, monkeypatch):
    raw = Path(os.environ["TALEPRISM_TEST_PINNED_LAST_LIGHT_ARCHIVE"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == sample.ARCHIVE_SHA256
    cache = tmp_path / "sample-cache" / f"last-light-{sample.ARCHIVE_SHA256}.zip"
    cache.parent.mkdir()
    cache.write_bytes(raw)
    monkeypatch.setattr(sample, "_download", lambda: pytest.fail("verified cache must be offline"))
    app = create_app(tmp_path)
    client = TestClient(app)
    assert client.get("/api/samples/last-light/guided").json()["cached"] is True
    response = client.post("/api/samples/last-light/guided")
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    plan = client.get(f"/api/projects/{pid}/production").json()["plan"]
    assert [shot["id"] for shot in plan["shots"]] == ["arrival", "negotiation", "recording"]
    assert len(plan["scenes"]) == 1
    reader = client.get(f"/api/projects/{pid}/reader").json()
    assert len(reader["assets"]) == 4
    assert len(reader["config"]["illustrations"]) == 3
    assert (
        client.get(f"/api/projects/{pid}/source").content
        == (sample.REPO / "samples/last-light/source.txt").read_bytes()
    )
