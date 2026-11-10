"""Recipe review replay must bind every uploaded byte before creating a client."""

import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
INPUTS = (
    "source.txt",
    "first.png",
    "second.png",
    "master.png",
    "opening.png",
    "ending.png",
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def builder():
    spec = importlib.util.spec_from_file_location(
        "recipe_review_builder", REPO / "tools/build_content_pack.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def recipe_path(tmp_path):
    root = tmp_path / "recipe"
    root.mkdir()
    (root / "source.txt").write_text(
        "第一章\n林遥穿着蓝衣，站在灯下。\n陈伯在灯下坐下记录。", encoding="utf-8"
    )
    for name, color in zip(INPUTS[1:], ["blue", "green", "tan", "yellow", "orange"]):
        Image.new("RGB", (80, 45), color).save(root / name)
    recipe = {
        "title": "合成回归样例",
        "subtitle": "仅用于测试",
        "source": "source.txt",
        "rights_status": "owned",
        "license": "synthetic test fixture",
        "style": "合成平色素材",
        "budget": 2,
        "cover": "cover",
        "background": "master",
        "characters": [
            {"name": "林遥", "description": "蓝衣", "portrait": "first.png"},
            {"name": "陈伯", "description": "记录者", "portrait": "second.png"},
            {"name": "小满", "description": "无参考图的角色"},
        ],
        "images": [
            {"key": "cover", "file": "master.png", "title": "封面", "kind": "cover"},
            {"key": "master", "file": "master.png", "title": "母版", "kind": "scene"},
            {"key": "opening", "file": "opening.png", "title": "开场", "kind": "scene"},
            {"key": "ending", "file": "ending.png", "title": "记录", "kind": "scene"},
        ],
        "dialogues": [],
        "shots": [],
        "scenes": [
            {
                "id": "station",
                "title": "灯下",
                "reference": "master",
                "layout": "一盏灯在人物上方",
                "objects": [{"id": "lamp", "name": "灯", "kind": "fixed", "home": "人物上方"}],
            }
        ],
        "continuity_review": "review.json",
    }
    for shot_id, marker, actor in [
        ("opening", "林遥穿着蓝衣", "林遥"),
        ("ending", "陈伯在灯下坐下记录", "陈伯"),
    ]:
        recipe["shots"].append(
            {
                "id": shot_id,
                "title": shot_id,
                "marker": marker,
                "image": shot_id,
                "moment": marker,
                "evidence": marker,
                "framing": "灯下平视固定机位",
                "avoid": "开场不得提前出现记录动作",
                "actors": [{"character": actor, "visible_action": marker}],
                "continuity": {
                    "scene_id": "station",
                    "method": "reuse",
                    "camera": "平视固定机位",
                    "changes": "人物动作依原文改变，灯保持不动",
                    "states": [
                        {"object_id": "lamp", "visibility": "visible", "position": "人物上方"}
                    ],
                },
            }
        )
    path = root / "recipe.json"
    write_json(path, recipe)
    hashes = {name: digest((root / name).read_bytes()) for name in INPUTS}
    write_json(
        root / "review.json",
        {
            "date": "2026-11-09",
            "reviewer": "assistant",
            "recipe_sha256": digest(path.read_bytes()),
            "images": {image["file"]: hashes[image["file"]] for image in recipe["images"]},
            "dependencies": hashes,
            "notes": {
                s["id"]: "合成回归样例检查记录，不构成真实美术确认。" for s in recipe["shots"]
            },
            "final_user_art_review": "pending",
        },
    )
    return path


def reject_before_client(builder, path, tmp_path, match):
    before = {p.name: p.read_bytes() for p in path.parent.iterdir()}

    def no_client(**_kwargs):
        pytest.fail("Invalid review must fail before constructing a client or creating a project")

    destination = tmp_path / "output" / "project.zip"
    with pytest.raises(ValueError, match=match):
        builder.build(path, "http://unused.invalid", destination, client_factory=no_client)
    assert not destination.parent.exists()
    assert {p.name: p.read_bytes() for p in path.parent.iterdir()} == before


@pytest.mark.parametrize("name", INPUTS)
def test_changed_dependency_fails_before_client(builder, recipe_path, tmp_path, name):
    path = recipe_path.parent / name
    if name == "source.txt":
        path.write_bytes(path.read_bytes().replace("蓝衣".encode(), "红衣".encode()))
    else:
        Image.new("RGB", (80, 45), "red").save(path)
    reject_before_client(builder, recipe_path, tmp_path, "检查失效.*" + name)


@pytest.mark.parametrize("name", INPUTS)
def test_missing_dependency_fails_before_client(builder, recipe_path, tmp_path, name):
    (recipe_path.parent / name).unlink()
    reject_before_client(builder, recipe_path, tmp_path, "无法读取.*" + name)


@pytest.mark.parametrize("name", INPUTS)
def test_missing_dependency_hash_requires_upgrade(builder, recipe_path, tmp_path, name):
    path = recipe_path.parent / "review.json"
    review = json.loads(path.read_text())
    del review["dependencies"][name]
    write_json(path, review)
    reject_before_client(builder, recipe_path, tmp_path, "重新核对并升级")


@pytest.mark.parametrize("name", INPUTS)
def test_tampered_dependency_hash_fails_before_client(builder, recipe_path, tmp_path, name):
    path = recipe_path.parent / "review.json"
    review = json.loads(path.read_text())
    review["dependencies"][name] = "0" * 64
    write_json(path, review)
    reject_before_client(builder, recipe_path, tmp_path, "检查失效.*" + name)


@pytest.mark.parametrize("hash_value", [None, "", "invalid", 123, [], {}])
def test_malformed_hash_is_not_accepted(builder, recipe_path, tmp_path, hash_value):
    path = recipe_path.parent / "review.json"
    review = json.loads(path.read_text())
    review["dependencies"]["source.txt"] = hash_value
    write_json(path, review)
    reject_before_client(builder, recipe_path, tmp_path, "哈希无效")


@pytest.mark.parametrize("field", ["dependencies", "recipe_sha256", "images"])
def test_old_or_incomplete_review_is_not_silently_upgraded(builder, recipe_path, tmp_path, field):
    path = recipe_path.parent / "review.json"
    review = json.loads(path.read_text())
    del review[field]
    write_json(path, review)
    message = "重新核对并升级" if field == "dependencies" else "重新核对"
    reject_before_client(builder, recipe_path, tmp_path, message)


@pytest.mark.parametrize("case", ["extra_dependency", "image_hash", "recipe", "review_missing"])
def test_other_stale_records_fail_before_client(builder, recipe_path, tmp_path, case):
    path = recipe_path.parent / "review.json"
    review = json.loads(path.read_text())
    if case == "extra_dependency":
        review["dependencies"]["unused.png"] = "0" * 64
        write_json(path, review)
    elif case == "image_hash":
        review["images"]["master.png"] = "0" * 64
        write_json(path, review)
    elif case == "recipe":
        recipe_path.write_bytes(recipe_path.read_bytes() + b"\n")
    else:
        path.unlink()
    reject_before_client(builder, recipe_path, tmp_path, "检查失效")


@pytest.fixture
def local_app(tmp_path, monkeypatch):
    # Importing storygal.app creates a default app: isolate it and bypass .env reads too.
    from storygal import llm, settings

    monkeypatch.setenv("STORYGAL_DATA_DIR", str(tmp_path / "default-app"))
    monkeypatch.setattr(settings, "load_env", lambda _path: None)
    monkeypatch.setattr(llm, "api_key", lambda: "")
    from storygal import app as app_module
    from storygal import exporter, reader_export

    monkeypatch.setattr(app_module, "load_env", lambda _path: None)
    monkeypatch.setattr(exporter, "api_key", lambda: "")
    monkeypatch.setattr(reader_export, "api_key", lambda: "")

    def no_network(*_args, **_kwargs):
        pytest.fail("Recipe regression tests must never use network transport")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    return app_module.create_app(tmp_path / "work")


@pytest.mark.parametrize("change_after_preflight", [False, True])
def test_reviewed_rebuild_uses_checked_bytes_and_preserves_review(
    builder, recipe_path, tmp_path, local_app, change_after_preflight
):
    from fastapi.testclient import TestClient

    original = {name: (recipe_path.parent / name).read_bytes() for name in INPUTS}
    review_raw = (recipe_path.parent / "review.json").read_bytes()
    review = json.loads(review_raw)

    def factory(**_kwargs):
        if change_after_preflight:
            for name in INPUTS:
                (recipe_path.parent / name).write_bytes(b"replaced after validation")
            recipe_path.write_bytes(b"replaced after validation")
        return TestClient(local_app)

    destination = tmp_path / "result.zip"
    report = builder.build(recipe_path, "http://testserver", destination, client_factory=factory)
    assert report["art_review"] == "pending_user_review"
    assert report["export"]["state"] == "completed"
    with zipfile.ZipFile(destination) as archive:
        assert archive.read("original.txt") == original["source.txt"]
    client = TestClient(local_app)
    prefix = "/api/projects/" + report["project_id"]
    assert client.get(prefix + "/source").content == original["source.txt"]
    plan = client.get(prefix + "/production").json()["plan"]
    assert len(plan["shots"]) == 2
    for shot in plan["shots"]:
        assert shot["continuity_check"]["reviewer"] == review["reviewer"]
        assert shot["continuity_check"]["notes"] == review["notes"][shot["id"]]
    for asset in local_app.state.review.state(report["project_id"])["assets"]:
        with Image.open(local_app.state.review.asset_path(report["project_id"], asset["id"])) as im:
            assert im.getpixel((0, 0))[:3] in {(0, 0, 255), (0, 128, 0)}
    assert len(client.get(prefix + "/reader").json()["config"]["illustrations"]) == 2
    assert client.get(prefix + "/delivery").json()["records"] == []
    assert (recipe_path.parent / "review.json").read_bytes() == review_raw

    # Existing project formats remain readable; the new gate only controls recipe replay.
    with zipfile.ZipFile(destination) as archive:
        files = {n: archive.read(n) for n in archive.namelist() if n != "manifest.json"}
    for version in (1, 2):
        project = json.loads(files["project.json"])
        project["version"] = version
        files["project.json"] = json.dumps(project).encode()
        manifest = {
            "format": "storygal-project-inventory",
            "version": 1,
            "files": {n: digest(raw) for n, raw in files.items()},
        }
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
            archive.writestr("manifest.json", json.dumps(manifest))
        restored = client.post(
            "/api/project-bundles", files={"file": ("project.zip", raw.getvalue())}
        )
        assert restored.status_code == 201, restored.text
        assert (
            client.get(f"/api/projects/{restored.json()['id']}/source").content
            == original["source.txt"]
        )


def test_recipe_without_continuity_scenes_keeps_legacy_build_support(
    builder, recipe_path, tmp_path, local_app
):
    from fastapi.testclient import TestClient

    recipe = json.loads(recipe_path.read_text())
    del recipe["scenes"]
    del recipe["continuity_review"]
    for shot in recipe["shots"]:
        del shot["continuity"]
    write_json(recipe_path, recipe)
    (recipe_path.parent / "review.json").unlink()
    report = builder.build(
        recipe_path,
        "http://testserver",
        tmp_path / "legacy.zip",
        client_factory=lambda **_kwargs: TestClient(local_app),
    )
    plan = (
        TestClient(local_app).get(f"/api/projects/{report['project_id']}/production").json()["plan"]
    )
    assert all(shot["continuity_check"] is None for shot in plan["shots"])
    assert report["art_review"] == "pending_user_review"
