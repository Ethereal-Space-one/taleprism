"""Fresh studio projects use the same immutable source and reader review model."""

import io
import json
import zipfile

from fastapi.testclient import TestClient
from PIL import Image

from storygal.app import create_app


def test_studio_source_candidate_acceptance_and_anchored_static_placement(tmp_path):
    client = TestClient(create_app(tmp_path))
    raw = "  第一段的微雨落在窗外。\r\n第二段里她打开了门。".encode("gb18030")

    def create(studio=False):
        response = client.post(
            "/api/projects",
            files={"file": ("自作.TXT", raw)},
            data={"rights_status": "owned", **({"single_plate_studio": "true"} if studio else {})},
        )
        assert response.status_code == 201
        return response.json()

    old, project = create(), create(True)
    assert old["id"] != project["id"] and "single_plate_studio" not in old
    prefix = "/api/projects/" + project["id"]
    assert client.get(prefix).json()["single_plate_studio"] is True
    assert client.get(prefix + "/source").content == raw
    base = prefix + "/reader"
    png = io.BytesIO()
    Image.new("RGB", (53, 31), "#766655").save(png, "PNG")
    asset = client.post(
        base + "/assets",
        files={"file": ("self-drawn.png", png.getvalue())},
        data={"revision": 0, "kind": "scene", "license_text": "test fixture"},
    ).json()
    assert asset["status"] == "pending"
    state = client.get(base).json()
    assert not state["config"]["illustrations"]
    assert client.get(base + "/assets/" + asset["id"]).status_code == 200
    assert (
        client.patch(
            base + "/assets/" + asset["id"],
            json={"revision": state["revision"], "status": "accepted"},
        ).status_code
        == 200
    )
    config = {
        **state["config"],
        "reading_layout": "illustrated",
        "illustrations": [
            {
                "id": "studio-first-illustration",
                "after_byte": state["paragraphs"][1]["byte_end"],
                "image_asset_id": asset["id"],
                "title": "一幅静图",
                "motion": None,
            }
        ],
    }
    # Never rebase a stale placement over a later review/edit.
    assert client.patch(base, json={**config, "revision": state["revision"]}).status_code == 409
    revision = client.get(base).json()["revision"]
    assert client.patch(base, json={**config, "revision": revision}).status_code == 200
    content = client.get(base + "/content").json()
    plate = content["config"]["illustrations"][0]
    assert "motion" in plate and plate["motion"] is None
    assert content["media"][plate["image_asset_id"]]["status"] == "accepted"
    assert plate["after_byte"] == content["blocks"][1]["byte_end"]
    assert client.get("/api/projects/" + old["id"] + "/reader").json()["assets"] == []
    restarted = TestClient(create_app(tmp_path))
    assert restarted.get(prefix).json()["single_plate_studio"] is True
    assert restarted.get(base).json()["config"]["illustrations"][0] == plate

    # Import is always a new project. A restoration preserves the entry for
    # the studio, not a new attestation. Exercise static and draft directions.
    receiver = TestClient(create_app(tmp_path / "receiver"))

    def roundtrip():
        package = client.get(prefix + "/bundle")
        assert package.status_code == 200, package.text[:200]
        with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
            packed = json.loads(archive.read("project.json"))
        assert packed["version"] == 3 and packed["project"]["single_plate_studio"] is True
        response = receiver.post(
            "/api/project-bundles", files={"file": ("project.zip", package.content)}
        )
        assert response.status_code == 201, response.text
        meta = response.json()
        assert meta["id"] != project["id"] and meta["single_plate_studio"] is True
        restored = "/api/projects/" + meta["id"]
        assert receiver.get(restored + "/source").content == raw
        assert (
            receiver.get(restored + "/reader/assets/" + asset["id"]).content
            == client.get(base + "/assets/" + asset["id"]).content
        )
        assert (
            receiver.get(restored + "/reader/content").json()["config"]
            == client.get(base + "/content").json()["config"]
        )
        return receiver.get(restored + "/reader").json()["config"]["illustrations"][0]

    assert roundtrip()["motion"] is None
    direction = {
        "version": 1,
        "effect": "rain-wet-ground",
        "image_sha256": asset["sha256"],
        "source_sha256": project["canonical_sha256"],
        "width": asset["width"],
        "height": asset["height"],
        "after_byte": plate["after_byte"],
        "evidence": "第一段的微雨落在窗外",
        "note": "这里只是未复核的测试范围。",
        "reviewed": False,
        "areas": [[[0, 0], [0.8, 0], [0.2, 0.6]]],
        "ground": [],
        "drops": 20,
        "rings": 0,
    }
    config["illustrations"][0]["motion"] = direction
    revision = client.get(base).json()["revision"]
    assert client.patch(base, json={**config, "revision": revision}).status_code == 200
    assert roundtrip()["motion"] == direction


def test_ordinary_legacy_and_malformed_studio_bundle_markers(tmp_path):
    from test_reader_motion import repack

    source = TestClient(create_app(tmp_path / "source"))
    receiver = TestClient(create_app(tmp_path / "receiver"))
    project = source.post(
        "/api/projects",
        files={"file": ("plain.txt", b"ordinary source")},
        data={"rights_status": "owned"},
    ).json()
    bundle = source.get("/api/projects/" + project["id"] + "/bundle")
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        doc = json.loads(archive.read("project.json"))
        assert doc["version"] == 2 and "single_plate_studio" not in doc["project"]

    def restore(blob):
        return receiver.post("/api/project-bundles", files={"file": ("project.zip", blob)})

    for version in (1, 2):
        ordinary = restore(repack(bundle.content, lambda d, v=version: d.update(version=v)))
        assert ordinary.status_code == 201, ordinary.text
        assert "single_plate_studio" not in ordinary.json()
    count = len(receiver.get("/api/projects").json())

    def marked(version, value):
        def update(doc):
            doc["version"] = version
            doc["project"]["single_plate_studio"] = value

        return repack(bundle.content, update)

    for value in (False, "true", 1, None, []):
        bad = restore(marked(3, value))
        assert bad.status_code == 400 and "元数据" in bad.text
    assert restore(repack(bundle.content, lambda doc: doc.update(version=3))).status_code == 400
    assert restore(marked(1, True)).status_code == 400
    assert restore(marked(2, True)).status_code == 400
    assert len(receiver.get("/api/projects").json()) == count
