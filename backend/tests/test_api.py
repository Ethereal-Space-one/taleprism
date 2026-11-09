import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from storygal.app import create_app
from storygal.exporter import REPO


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path))


DEFAULT_TEXT = "　　周瑜曰：「你好。」\r\n　　孔明笑。".encode()


def upload(client, raw=DEFAULT_TEXT, **fields):
    return client.post(
        "/api/projects",
        files={"file": ("test.txt", raw)},
        data={"rights_status": "local_test", **fields},
    )


def test_upload_persistence_and_original_bytes(client):
    raw = b"\xef\xbb\xbf" + "　　赤壁\r\n\t孔明曰：「東風。」".encode()
    response = upload(client, raw)
    assert response.status_code == 201
    project = response.json()
    project_id = project["id"]
    assert client.get(f"/api/projects/{project_id}/source").content == raw
    data = client.get(f"/api/projects/{project_id}/text").json()
    assert "".join(s["text"] for s in data["spans"]).encode() == raw
    assert "".join(u["text"] for u in data["units"]) == "赤壁孔明曰：「東風。」"
    assert client.post(f"/api/projects/{project_id}/verify").json()["span_coverage"] is True
    reopened = TestClient(create_app(client.app.state.store.root))
    assert reopened.get("/api/projects").json()[0] == project


def test_upload_validation_and_path_safety(client):
    assert upload(client, b" ").status_code == 400
    assert upload(client, b"text", rights_status="bad").status_code == 400
    assert client.get("/api/projects/not-a-uuid").status_code == 404
    assert (
        client.post(
            "/api/projects", files={"file": ("x.pdf", b"pdf")}, data={"rights_status": "owned"}
        ).status_code
        == 400
    )
    project = upload(client).json()
    assert client.get(f"/play/{project['id']}/bad/index.html").status_code == 404


def test_hash_tampering_blocks_export(client):
    project_id = upload(client).json()["id"]
    path = client.app.state.store.project_dir(project_id) / "source.utf8.txt"
    path.chmod(0o644)
    path.write_bytes(b"tampered")
    assert client.post(f"/api/projects/{project_id}/verify").status_code == 400
    client.post(f"/api/projects/{project_id}/exports")
    job = client.get(f"/api/projects/{project_id}/jobs").json()[0]
    assert job["state"] == "failed"
    assert "哈希" in job["error"]


@pytest.mark.skipif(
    not (REPO / "engine/webgal-4.6.5/index.html").exists(), reason="run fetch_engine.sh"
)
def test_special_characters_parse_export_and_download(client):
    tricky = r"原文 : ; , . | -next -evil.wav {name} [词](注音) \\ \; \\{x} none 😀 <script>alert(1)</script>"
    project_id = upload(client, tricky.encode()).json()["id"]
    assert client.post(f"/api/projects/{project_id}/exports").status_code == 202
    job = client.get(f"/api/projects/{project_id}/jobs").json()[0]
    assert job["state"] == "completed", job
    result = job["result"]
    assert result["checks"]["parser"]["passed"] is True
    assert result["checks"]["render"] == "not_run"
    assert client.get(result["play_url"]).status_code == 200
    downloaded = client.get(result["download_url"])
    assert downloaded.status_code == 200
    archive = client.app.state.store.project_dir(project_id) / "exports" / (job["id"] + ".zip")
    with zipfile.ZipFile(archive) as z:
        assert z.read("storygal-source/original.txt") == tricky.encode()
        manifest = json.loads(z.read("storygal-manifest.json"))
        assert "".join(u["text"] for u in manifest["units"]) == tricky
        assert "LICENSE-WebGAL-MPL-2.0.txt" in z.namelist()
        assert b"SGTEXT_" in z.read("assets/index-CC7KTie-.js")


def test_gb18030_input(client):
    raw = "　　赤壁之战，孔明曰：「东风。」".encode("gb18030")
    response = upload(client, raw, encoding="gb18030")
    assert response.status_code == 201
    project_id = response.json()["id"]
    assert client.get(f"/api/projects/{project_id}/source").content == raw
    assert client.post(f"/api/projects/{project_id}/verify").json()["encoding_roundtrip"] is True
