"""A marginal quotation must not become prose, evidence, or a hidden author note."""

import copy
import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reader_build_fixture import fake_reader_build

from storygal import reader_export
from storygal.app import create_app
from storygal.reader_echo import validate_echo_fold
from storygal.text import sha256

ROOT = Path(__file__).resolve().parents[2]
RAW = "\ufeff　纸船上写着「稍候」。\r\n\r\n风把灯吹灭。\n　她终于放开了船。\n水声还在。".encode()
PAIR = {
    "earlier": {"paragraph": 1, "quote": "「稍候」"},
    "later": {"paragraph": 3, "quote": "放开了船"},
}


@pytest.fixture
def project(tmp_path, monkeypatch):
    # Backend packaging tests inspect data, not the JS runtime (also tested in a browser).
    public = tmp_path / "build"
    fake_reader_build(public)
    (public / "tools").mkdir()
    for name in ["verify_package.py", "reader_launcher.py", "reader_launcher.command"]:
        shutil.copy2(ROOT / "tools" / name, public / "tools" / name)
    monkeypatch.setattr(reader_export, "REPO", public)
    client = TestClient(create_app(tmp_path / "store"))
    made = client.post(
        "/api/projects", files={"file": ("纸船.txt", RAW)}, data={"rights_status": "owned"}
    )
    assert made.status_code == 201, made.text
    pid = made.json()["id"]
    return client, pid, f"/api/projects/{pid}"


def save(c, base, pair):
    state = c.get(base + "/reader").json()
    return c.patch(
        base + "/reader", json={**state["config"], "revision": state["revision"], "echo_fold": pair}
    )


def archived(r, name):
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        return z.read(name)


def tamper(r, update):
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        files = {name: z.read(name) for name in z.namelist()}
    doc = json.loads(files["project.json"])
    update(doc)
    files["project.json"] = json.dumps(doc, ensure_ascii=False).encode()
    manifest = json.loads(files["manifest.json"])
    manifest["files"]["project.json"] = sha256(files["project.json"])
    files["manifest.json"] = json.dumps(manifest).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    return out.getvalue()


def test_fold_only_is_a_real_export_and_restorable_project(project):
    c, pid, base = project
    original = c.get(base + "/reader/content").json()
    assert "echo_fold" not in original["config"] and original["schema_version"] == 2
    assert save(c, base, PAIR).is_success
    preview = c.get(base + "/reader/content").json()
    assert original["blocks"] == preview["blocks"]
    assert preview["config"]["echo_fold"] == PAIR and preview["schema_version"] == 6
    assert not preview["media"]
    response = c.get(base + "/exports/compatibility")
    assert [item["field"] for item in response.json()["losses"]] == ["echo_fold"]
    assert c.post(base + "/exports").status_code == 400  # no silent WebGAL omission

    backup = c.get(base + "/bundle")
    assert backup.is_success, backup.text
    assert json.loads(archived(backup, "project.json"))["version"] == 7
    restored = c.post("/api/project-bundles", files={"file": ("paper.zip", backup.content)})
    assert restored.status_code == 201, restored.text
    new = restored.json()["id"]
    assert new != pid and c.get(f"/api/projects/{new}/source").content == RAW
    newbase = f"/api/projects/{new}"
    assert c.get(newbase + "/reader/content").json()["config"]["echo_fold"] == PAIR

    assert c.post(newbase + "/reader/exports").status_code == 202
    job = c.get(newbase + "/jobs").json()[0]
    assert job["state"] == "completed", job
    package = c.get(job["result"]["download_url"])
    story = json.loads(archived(package, "reader.json"))
    html = archived(package, "index.html").decode()
    inline = json.loads(
        html.split('id="taleprism-story" type="application/json">', 1)[1].split("</script>")[0]
    )
    assert inline == story
    assert story["config"]["echo_fold"] == PAIR
    assert story["schema_version"] == 6 and story["blocks"] == original["blocks"]
    assert archived(package, "storygal-source/original.txt") == RAW
    assert save(c, base, None).is_success
    assert "echo_fold" not in c.get(base + "/reader/content").json()["config"]
    assert json.loads(archived(c.get(base + "/bundle"), "project.json"))["version"] == 2


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(version=2),
        lambda d: d["states"]["reader_states"]["data"].pop("echo_fold"),
        lambda d: d["states"]["reader_states"]["data"]["echo_fold"].update(rationale="私稿"),
        lambda d: d["states"]["reader_states"]["data"]["echo_fold"]["later"].update(
            quote="不在原文中"
        ),
        lambda d: d["states"]["reader_states"]["data"]["echo_fold"]["earlier"].update(
            paragraph=True
        ),
    ],
)
def test_tampered_backup_does_not_publish(project, change):
    c, _, base = project
    assert save(c, base, PAIR).is_success
    backup = c.get(base + "/bundle")
    before = c.get("/api/projects").json()
    response = c.post(
        "/api/project-bundles", files={"file": ("changed.zip", tamper(backup, change))}
    )
    assert response.status_code == 400
    assert c.get("/api/projects").json() == before


@pytest.mark.parametrize(
    ("side", "field", "value"),
    [
        ("earlier", "paragraph", "1"),
        ("earlier", "paragraph", True),
        ("earlier", "paragraph", 0),
        ("later", "paragraph", 4),
        ("later", "paragraph", 2),
        ("later", "paragraph", 30),
        ("earlier", "quote", " "),
        ("earlier", "quote", "　"),
        ("earlier", "quote", "稍后"),
        ("later", "quote", "放开了船。 "),
        ("later", "rationale", "写进读者版的批注"),
    ],
)
def test_save_rejects_invalid_without_incrementing_revision(project, side, field, value):
    c, _, base = project
    bad = copy.deepcopy(PAIR)
    bad[side][field] = value
    assert save(c, base, bad).status_code in (400, 422)
    assert c.get(base + "/reader").json()["revision"] == 0


def test_unique_even_with_overlaps_unicode_cap_and_chapter_boundary():
    def check(text, quote, heading=False):
        return validate_echo_fold(
            {
                "earlier": {"paragraph": 1, "quote": quote},
                "later": {"paragraph": 3, "quote": "灯。"},
            },
            [{"text": text}, {"text": "风。", "heading": heading}, {"text": "灯。"}],
        )

    assert check("😀" * 160, "😀" * 160)
    with pytest.raises(ValueError):
        check("😀" * 161, "😀" * 161)
    with pytest.raises(ValueError):
        check("aaa", "aa")
    with pytest.raises(ValueError):
        check("同一行。", "同一行", True)


@pytest.mark.parametrize(
    "corrupted",
    [
        dict(PAIR, rationale="私下的制作意见"),
        dict(PAIR, earlier={"paragraph": 1, "quote": "并不存在"}),
    ],
)
def test_corrupt_saved_data_cannot_leak_into_reader_or_editable_exports(project, corrupted):
    c, pid, base = project
    assert save(c, base, PAIR).is_success
    store = c.app.state.store
    with store.db() as db:
        config = json.loads(
            db.execute("SELECT data FROM reader_states WHERE project_id=?", (pid,)).fetchone()[0]
        )
        config["echo_fold"] = corrupted
        db.execute("UPDATE reader_states SET data=? WHERE project_id=?", (json.dumps(config), pid))
    preview = c.get(base + "/reader/content")
    assert preview.status_code == 400 and "私下" not in preview.text
    assert c.get(base + "/bundle").status_code == 400
    assert c.post(base + "/reader/exports").status_code == 202
    assert c.get(base + "/jobs").json()[0]["state"] == "failed"
