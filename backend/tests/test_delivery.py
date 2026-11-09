import json
import subprocess
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

from storygal import exporter
from storygal.app import create_app
from storygal.delivery import REVIEW_CHECKS


@pytest.fixture
def setup(tmp_path):
    app = create_app(tmp_path)
    client = TestClient(app)
    raw = "孔明曰：「東風。」\n周瑜曰：「火攻。」".encode()
    pid = client.post(
        "/api/projects", files={"file": ("delivery.txt", raw)}, data={"rights_status": "local_test"}
    ).json()["id"]
    return client, pid, raw


def export(client, pid):
    assert client.post(f"/api/projects/{pid}/exports").status_code == 202
    return client.get(f"/api/projects/{pid}/jobs").json()[0]


def test_readiness_warnings_and_corrupt_source(setup):
    c, pid, _ = setup
    result = c.get(f"/api/projects/{pid}/delivery").json()
    assert result["ready"] and len(result["warnings"]) == 2
    path = c.app.state.store.project_dir(pid) / "source.utf8.txt"
    path.chmod(0o644)
    path.write_bytes(b"bad")
    r = c.get(f"/api/projects/{pid}/delivery")
    assert r.status_code == 200
    assert not r.json()["ready"]
    assert "哈希" in r.json()["checks"][0]["detail"]


def test_package_independent_check_and_tamper_detection(setup, tmp_path):
    c, pid, raw = setup
    job = export(c, pid)
    assert job["state"] == "completed", job
    root = tmp_path / "extracted"
    archive = c.app.state.store.project_dir(pid) / "exports" / (job["id"] + ".zip")
    with zipfile.ZipFile(archive) as z:
        z.extractall(root)
    proc = subprocess.run(
        [sys.executable, str(root / "verify_package.py")], capture_output=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["files"] == job["result"]["file_count"]
    assert (root / "storygal-source/original.txt").read_bytes() == raw
    (root / "game/scene/start.txt").write_text("changed", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(root / "verify_package.py")], capture_output=True, check=False
    )
    assert proc.returncode != 0 and "start.txt" in proc.stderr.decode()


def test_unpublished_paths_are_never_served(setup):
    c, pid, _ = setup
    store = c.app.state.store
    eid = store.start_job(pid)
    directory = store.project_dir(pid) / "exports" / eid
    directory.mkdir(parents=True)
    (directory / "index.html").write_text("incomplete")
    directory.with_suffix(".zip").write_bytes(b"incomplete")
    for url in [f"/play/{pid}/{eid}/index.html", f"/api/projects/{pid}/exports/{eid}/download"]:
        assert c.get(url).status_code == 404
    store.finish_job(eid, error="failed")
    assert c.get(f"/play/{pid}/{eid}/index.html").status_code == 404


def test_zip_failure_cleans_everything_and_can_retry(setup, monkeypatch):
    c, pid, _ = setup
    original = exporter.zipfile.ZipFile

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(exporter.zipfile, "ZipFile", fail)
    failed = export(c, pid)
    assert failed["state"] == "failed"
    assert list((c.app.state.store.project_dir(pid) / "exports").iterdir()) == []
    monkeypatch.setattr(exporter.zipfile, "ZipFile", original)
    assert export(c, pid)["state"] == "completed"


def test_change_during_export_is_not_published(setup, monkeypatch):
    c, pid, raw = setup
    original = exporter.shutil.copy2
    changed = False

    def copy_and_change(source, destination, *args, **kwargs):
        nonlocal changed
        result = original(source, destination, *args, **kwargs)
        if not changed:
            changed = True
            visual = c.app.state.visual
            visual.settings(pid, visual.state(pid)["revision"], "ink", 4)
        return result

    monkeypatch.setattr(exporter.shutil, "copy2", copy_and_change)
    job = export(c, pid)
    assert job["state"] == "failed" and "状态" in job["error"]
    assert list((c.app.state.store.project_dir(pid) / "exports").iterdir()) == []
    assert c.get(f"/api/projects/{pid}/source").content == raw


def test_review_record_is_explicit_and_bound_to_current_export(setup):
    c, pid, _ = setup
    job = export(c, pid)
    url = f"/api/projects/{pid}/exports/{job['id']}/review"
    assert c.post(url, json={"checks": {"end": True}}).status_code == 400
    checks = {key: True for key in REVIEW_CHECKS}
    r = c.post(url, json={"checks": checks, "notes": "测试复核记录"})
    assert r.status_code == 200, r.text
    assert r.json()["archive_sha256"] == job["result"]["archive_sha256"]
    assert c.get(f"/api/projects/{pid}/delivery").json()["records"][0]["export_id"] == job["id"]
    archive = c.app.state.store.project_dir(pid) / "exports" / (job["id"] + ".zip")
    original = archive.read_bytes()
    archive.write_bytes(original + b"changed")
    assert c.get(job["result"]["download_url"]).status_code == 400
    assert c.post(url, json={"checks": checks}).status_code == 400
    archive.write_bytes(original)
    v = c.app.state.visual
    v.settings(pid, v.state(pid)["revision"], "ink", 4)
    assert c.get(f"/api/projects/{pid}/delivery").json()["stale"]
    assert c.post(url, json={"checks": checks}).status_code == 409
    assert c.get(job["result"]["play_url"]).status_code == 200


def test_restart_recovers_only_interrupted_tasks_and_lock_protects_live_work(setup):
    c, pid, raw = setup
    store = c.app.state.store
    completed = export(c, pid)
    with TestClient(c.app):
        eid = store.start_job(pid)
        parent = store.project_dir(pid) / "exports"
        (parent / (eid + ".partial")).mkdir()
        (parent / (eid + ".zip.partial")).write_bytes(b"partial")
        with pytest.raises(RuntimeError, match="正在运行"), TestClient(create_app(store.root)):
            pass
        assert next(j for j in store.jobs(pid) if j["id"] == eid)["state"] == "running"
    with TestClient(create_app(store.root)) as restarted:
        job = next(j for j in store.jobs(pid) if j["id"] == eid)
        assert job["state"] == "failed" and "中断" in job["error"]
        assert not (parent / (eid + ".partial")).exists()
        assert not (parent / (eid + ".zip.partial")).exists()
        assert restarted.get(completed["result"]["play_url"]).status_code == 200
        assert restarted.get(f"/api/projects/{pid}/source").content == raw
