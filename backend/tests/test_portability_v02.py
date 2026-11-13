"""Optional samples cannot break ordinary projects; model status stays truthful and private."""

import io
import json
import os
import shutil
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from storygal import app as app_module
from storygal import llm, reader, reader_export
from storygal.app import create_app

ROOT = Path(__file__).resolve().parents[2]
TEXT = "第一章 夜雨\n林遥说：「等一会儿。」\n雨停了。".encode()


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "load_env", lambda *_: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name in list(os.environ):
        if name.startswith("STORYGAL_LLM_") or name in {
            "DEEPSEEK_API_KEY",
            "DeepSeek_ApiKeyN",
            "deepseek-apin",
            "OPENAI_API_KEY",
        }:
            monkeypatch.delenv(name)


@pytest.fixture
def portable(monkeypatch, tmp_path):
    root = tmp_path / "source-only"
    (root / "frontend/dist/assets").mkdir(parents=True)
    (root / "frontend/dist/index.html").write_text("<html><head></head><body></body></html>")
    (root / "frontend/dist/assets/app.js").write_text("/* isolated exporter fixture */")
    (root / "tools").mkdir()
    shutil.copyfile(ROOT / "tools/verify_package.py", root / "tools/verify_package.py")
    for module in [reader, reader_export, app_module]:
        monkeypatch.setattr(module, "REPO", root)
    client = TestClient(create_app(tmp_path / "private-data"))
    return client, root


def upload(c):
    response = c.post(
        "/api/projects", files={"file": ("ordinary.txt", TEXT)}, data={"rights_status": "owned"}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_no_samples_full_edit_restore_and_reader_export(portable, tmp_path):
    c, root = portable
    assert not (root / "samples").exists()
    pid = upload(c)
    r = c.app.state.reader
    state = c.get(f"/api/projects/{pid}/reader").json()
    assert state["chibi_sample"] is False
    png = io.BytesIO()
    Image.new("RGB", (40, 40), "navy").save(png, "PNG")
    asset = r.upload(pid, state["revision"], png.getvalue(), "scene", "Test fixture, owned")
    r.accept(pid, r.load(pid)[0], asset["id"], "accepted")
    rev, config = r.load(pid)
    config["title"] = "普通工程更新"
    config["scenes"] = [
        {
            "id": "night",
            "title": "夜雨",
            "start_byte": 0,
            "asset_id": asset["id"],
            "character_ids": [],
        }
    ]
    response = c.patch(f"/api/projects/{pid}/reader", json={"revision": rev, **config})
    assert response.status_code == 200, response.text
    assert c.get(f"/api/projects/{pid}/reader/content").json()["map"] is None
    assert c.get(f"/api/projects/{pid}/source").content == TEXT
    archive = c.get(f"/api/projects/{pid}/bundle")
    assert archive.status_code == 200, archive.text[:300]
    restored = TestClient(create_app(tmp_path / "restored"))
    response = restored.post(
        "/api/project-bundles", files={"file": ("project.zip", archive.content)}
    )
    assert response.status_code == 201, response.text
    new_pid = response.json()["id"]
    assert restored.get(f"/api/projects/{new_pid}/reader").json()["config"] == config
    assert restored.get(f"/api/projects/{new_pid}/source").content == TEXT
    response = restored.post(f"/api/projects/{new_pid}/reader/exports")
    assert response.status_code == 202
    job = restored.get(f"/api/projects/{new_pid}/jobs").json()[0]
    assert job["state"] == "completed", job
    bundle = restored.get(job["result"]["download_url"]).content
    with zipfile.ZipFile(io.BytesIO(bundle)) as z:
        assert z.read("storygal-source/original.txt") == TEXT
        content = json.loads(z.read("reader.json"))
        assert content["map"] is None and content["config"]["title"] == "普通工程更新"
        assert "".join(b["text"] for b in content["blocks"]) == TEXT.decode().replace("\n", "")
        assert len(content["media"]) == 1
    assert len(restored.get("/api/projects").json()) == 1
    reopened = TestClient(create_app(restored.app.state.store.root))
    assert reopened.get(f"/api/projects/{new_pid}/reader/content").status_code == 200
    # Existing asset rejection and removal remain editable without a sample file.
    other = restored.app.state.reader
    rev, config = other.load(new_pid)
    config["scenes"] = []
    other.save(new_pid, rev, config)
    other.accept(new_pid, other.load(new_pid)[0], asset["id"], "rejected")
    assert restored.get(f"/api/projects/{new_pid}/reader/content").status_code == 200


@pytest.mark.parametrize(
    "endpoint",
    [
        "reader/sample",
        "reader/choreography/sample",
        "reader/choreography/expanded-sample",
        "reader/choreography/second-sample",
        "reader/narrative/sample",
    ],
)
def test_chibi_actions_explain_missing_text_without_mutation(portable, endpoint):
    c, _ = portable
    pid = upload(c)
    before = c.app.state.reader.load(pid)
    response = c.post(f"/api/projects/{pid}/{endpoint}", json={"revision": before[0]})
    assert response.status_code == 400
    assert "缺少赤壁样例原文" in response.json()["detail"]
    assert c.app.state.reader.load(pid) == before
    assert c.app.state.reader.state_assets(pid) == []


def test_missing_sample_create_is_actionable(portable):
    c, _ = portable
    for name in ["chibi", "last-light"]:
        response = c.post("/api/samples/" + name)
        assert response.status_code == 400
        assert "样例原文" in response.json()["detail"]
    assert c.get("/api/projects").json() == []


@pytest.mark.parametrize("map_bytes", [None, b"{invalid", b"{}", b"null"])
def test_chibi_map_missing_or_invalid_fails_only_when_selected(portable, map_bytes):
    c, root = portable
    sample = root / "samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt"
    sample.parent.mkdir(parents=True)
    sample.write_bytes(TEXT)
    if map_bytes is not None:
        path = root / "samples/reader/chibi-map.json"
        path.parent.mkdir()
        path.write_bytes(map_bytes)
    pid = upload(c)
    r = c.app.state.reader
    assert r.is_chibi(pid)
    rev, config = r.load(pid)
    r.save(pid, rev, config)
    assert r.content(pid)["map"] is None
    before = r.load(pid)
    config["map_profile"] = "chibi"
    response = c.patch(f"/api/projects/{pid}/reader", json={"revision": before[0], **config})
    assert response.status_code == 400
    assert "地图素材缺失或损坏" in response.json()["detail"]
    assert r.load(pid) == before


def test_health_identifies_instance_workspace_and_data(portable, tmp_path):
    c, root = portable
    health = c.get("/api/health").json()
    assert health["version"] == "0.2.0" and c.app.version == "0.2.0"
    assert health["service"] == "taleprism"
    assert health == c.get("/api/health").json()
    same = TestClient(create_app(c.app.state.store.root)).get("/api/health").json()
    other = TestClient(create_app(tmp_path / "other-data")).get("/api/health").json()
    assert health["data_id"] == same["data_id"] != other["data_id"]
    assert health["workspace_id"] == same["workspace_id"] == other["workspace_id"]
    assert health["instance_id"] != same["instance_id"]
    assert str(root) not in json.dumps(health)


@pytest.mark.parametrize(
    ("base", "provider"),
    [
        ("https://api.deepseek.com", "DeepSeek"),
        ("https://api.openai.com/v1/", "OpenAI"),
        ("https://gateway.example/v1", "OpenAI-compatible"),
        ("http://127.0.0.1:12345/v1", "OpenAI-compatible"),
    ],
)
def test_model_status_and_mock_request_use_actual_config(portable, monkeypatch, base, provider):
    c, _ = portable
    monkeypatch.setenv("STORYGAL_LLM_API_KEY", "test-private-key")
    monkeypatch.setenv("STORYGAL_LLM_BASE_URL", base)
    monkeypatch.setenv("STORYGAL_LLM_MODEL", "chosen/model-02")
    status = c.get("/api/llm/status")
    assert status.json() == llm.configuration() | {"configured": True}
    assert status.json()["provider"] == provider
    assert status.json()["base_url"] == base.rstrip("/")
    assert "test-private-key" not in status.text

    def reply(request):
        body = json.loads(request.content)
        assert str(request.url) == base.rstrip("/") + "/chat/completions"
        assert body["model"] == "chosen/model-02"
        assert ("thinking" in body) == (provider == "DeepSeek")
        assert request.headers["authorization"] == "Bearer test-private-key"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"characters":[],"speakers":[]}'},
                    }
                ]
            },
        )

    assert llm.analyze({}, transport=httpx.MockTransport(reply))[0]["characters"] == []


def test_provider_override_and_legacy_local_key(portable, monkeypatch, tmp_path):
    c, _ = portable
    (tmp_path / ".zshrc").write_text('export DeepSeek_ApiKeyN="legacy-private-key"\n')
    assert llm.api_key() == "legacy-private-key"
    assert llm.status()["provider"] == "DeepSeek"
    monkeypatch.setenv("STORYGAL_LLM_BASE_URL", "https://models.example/v1")
    monkeypatch.setenv("STORYGAL_LLM_PROVIDER", "Example Cloud")
    status = c.get("/api/llm/status").json()
    assert status["provider"] == "Example Cloud" and status["configured"] is False
    monkeypatch.setenv("STORYGAL_LLM_API_KEY", "generic-private-key")
    assert llm.api_key() == "generic-private-key"
    assert "private-key" not in c.get("/api/llm/status").text


@pytest.mark.parametrize(
    "base",
    ["https://models.example/v1", "http://api.deepseek.com", "https://api.deepseek.com:8443"],
)
def test_legacy_key_is_unavailable_to_other_endpoints(portable, monkeypatch, base):
    c, _ = portable
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-legacy-key")
    monkeypatch.setenv("STORYGAL_LLM_BASE_URL", base)
    assert llm.status()["configured"] is False
    pid = upload(c)
    prefix = f"/api/projects/{pid}"
    plan = c.get(prefix + "/production").json()
    assert plan["model_configured"] is False
    assert c.post(prefix + "/analysis", json={"allow_remote": True}).status_code == 400
    assert c.post(prefix + "/production/generate", json={"revision": plan["revision"]}).status_code == 400
    assert c.get(prefix + "/jobs").json() == []

    def reject_request(_request):
        pytest.fail("No request should be sent without a credential for the configured provider")

    with pytest.raises(ValueError, match="STORYGAL_LLM_API_KEY"):
        llm.analyze({}, transport=httpx.MockTransport(reject_request))


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("STORYGAL_LLM_BASE_URL", "https://user:test-private-key@models.example/v1"),
        ("STORYGAL_LLM_BASE_URL", "https://models.example/v1?api_key=test-private-key"),
        ("STORYGAL_LLM_BASE_URL", "https://models.example/test-private-key"),
        ("STORYGAL_LLM_BASE_URL", "https://models.example/%74est-private-key"),
        ("STORYGAL_LLM_MODEL", "test-private-key"),
        ("STORYGAL_LLM_PROVIDER", "test-private-key"),
        ("STORYGAL_LLM_BASE_URL", "file:///private/local"),
        ("STORYGAL_LLM_BASE_URL", "http://[bad"),
    ],
)
def test_invalid_or_secret_config_never_leaks_or_creates_job(portable, monkeypatch, name, value):
    c, _ = portable
    monkeypatch.setenv("STORYGAL_LLM_API_KEY", "test-private-key")
    monkeypatch.setenv(name, value)
    status = c.get("/api/llm/status")
    assert status.status_code == 200 and status.json()["configured"] is False
    assert status.json()["error"]
    pid = upload(c)
    response = c.post(f"/api/projects/{pid}/analysis", json={"allow_remote": True})
    assert response.status_code == 400
    assert "test-private-key" not in response.text + status.text
    assert c.get(f"/api/projects/{pid}/jobs").json() == []


def test_generic_missing_key_message(portable):
    c, _ = portable
    pid = upload(c)
    response = c.post(f"/api/projects/{pid}/analysis", json={"allow_remote": True})
    assert response.status_code == 400
    assert "STORYGAL_LLM_API_KEY" in response.json()["detail"]
    assert c.get(f"/api/projects/{pid}/jobs").json() == []


def test_relative_data_configuration_is_rooted_in_workspace(portable, monkeypatch):
    _, root = portable
    monkeypatch.setenv("STORYGAL_DATA_DIR", "nested data")
    app = create_app()
    assert app.state.store.root == root / "nested data"
    assert TestClient(app).get("/api/health").json()["data_id"] == reader.sha256(
        str(root / "nested data").encode()
    )
