"""Creator directions survive portable readers without becoming art approval."""

import copy
import io
import json
import math
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from storygal import app as app_module
from storygal import reader, reader_export
from storygal.app import create_app
from storygal.reader_api import Configuration
from storygal.text import sha256

ROOT = Path(__file__).resolve().parents[2]
RAW = (
    "第一章 潮雨\n"
    "雨点落进院里的水洼，石阶边亮着灯。\n"
    "江水撞向低矮的堤岸，白色水花退了回去。\n"
    "最后一行是还未发生的告别。"
).encode()
POLYGON = [[0.1, 0.4], [0.8, 0.4], [0.9, 0.95], [0.1, 0.95]]


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "load_env", lambda *_: None)
    root = tmp_path / "public-source"
    from reader_build_fixture import fake_reader_build

    fake_reader_build(root)
    (root / "frontend/dist/assets").mkdir(parents=True)
    (root / "frontend/dist/index.html").write_text("<html><head></head><body></body></html>")
    (root / "frontend/dist/assets/app.js").write_text("/* isolated, offline export fixture */")
    (root / "tools").mkdir()
    for name in ("verify_package.py", "reader_launcher.py", "reader_launcher.command"):
        shutil.copyfile(ROOT / "tools" / name, root / "tools" / name)
    for module in (reader, reader_export, app_module):
        monkeypatch.setattr(module, "REPO", root)
    c = TestClient(create_app(tmp_path / "data"))
    response = c.post(
        "/api/projects", files={"file": ("潮雨.txt", RAW)}, data={"rights_status": "owned"}
    )
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    r = c.app.state.reader
    output = io.BytesIO()
    Image.new("RGB", (120, 80), "navy").save(output, "PNG")
    asset = r.upload(pid, r.load(pid)[0], output.getvalue(), "scene", "synthetic fixture, owned")
    r.accept(pid, r.load(pid)[0], asset["id"], "accepted")
    asset = r.state_assets(pid)[0]
    _, config = r.load(pid)
    config["reading_layout"] = "illustrated"
    config["illustrations"] = [
        {
            "id": "rain-court",
            "after_byte": r.blocks(pid)[2]["byte_end"],
            "image_asset_id": asset["id"],
            "title": "潮雨",
            "description": "合成测试图，无美术质量承诺。",
        }
    ]
    return c, pid, r, asset, config


def motion(project, effect="rain-wet-ground", reviewed=False):
    _, _, _, asset, config = project
    result = {
        "version": 1,
        "effect": effect,
        "image_sha256": asset["sha256"],
        "source_sha256": sha256(RAW),
        "width": 120,
        "height": 80,
        "after_byte": config["illustrations"][0]["after_byte"],
        "evidence": "雨点落进院里的水洼",
        "note": "创作者只核对标记区域，保留人物和原图不动。",
        "reviewed": reviewed,
    }
    if effect == "rain-wet-ground":
        result.update(
            areas=[copy.deepcopy(POLYGON)], ground=[copy.deepcopy(POLYGON)], drops=48, rings=8
        )
    else:
        result.update(
            evidence="江水撞向低矮的堤岸",
            water=[copy.deepcopy(POLYGON)],
            bank=[[0.1, 0.9], [0.4, 0.7], [0.9, 0.5]],
            hits=[{"x": 0.4, "phase": 0.2, "length": 7.1, "gain": 1.0}],
        )
    return result


def save(project, config):
    c, pid, r, _, _ = project
    return c.patch(f"/api/projects/{pid}/reader", json={"revision": r.load(pid)[0], **config})


def with_motion(project, direction):
    config = copy.deepcopy(project[-1])
    config["illustrations"][0]["motion"] = direction
    return config


def repack(raw, change):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    doc = json.loads(files["project.json"])
    change(doc)
    files["project.json"] = json.dumps(doc, ensure_ascii=False).encode()
    manifest = json.loads(files["manifest.json"])
    manifest["files"]["project.json"] = sha256(files["project.json"])
    files["manifest.json"] = json.dumps(manifest).encode()
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return result.getvalue()


@pytest.mark.parametrize("effect", ["rain-wet-ground", "wave-impact-backwash"])
@pytest.mark.parametrize("reviewed", [False, True])
def test_api_source_exact_motion_survives_content_and_reopen(project, effect, reviewed):
    c, pid, r, asset, _ = project
    direction = motion(project, effect, reviewed)
    config = with_motion(project, direction)
    response = save(project, config)
    assert response.status_code == 200, response.text
    assert r.load(pid)[1] == config
    content = c.get(f"/api/projects/{pid}/reader/content")
    assert content.status_code == 200, content.text
    assert content.json()["config"] == config
    assert content.json()["preview"] is False  # A motion draft does not block static reading.
    assert r.state_assets(pid)[0]["status"] == asset["status"] == "accepted"
    reopened = TestClient(create_app(r.store.root))
    assert reopened.get(f"/api/projects/{pid}/reader").json()["config"] == config
    assert c.get(f"/api/projects/{pid}/source").content == RAW


@pytest.mark.parametrize(
    "mode", ["omitted", "static", "rain-draft", "rain", "shore-draft", "shore"]
)
def test_backup_restore_and_standalone_export_preserve_motion_contract(project, tmp_path, mode):
    c, pid, _r, asset, config = project
    if mode == "static":
        config = with_motion(project, None)
    elif mode != "omitted":
        effect = "wave-impact-backwash" if mode.startswith("shore") else "rain-wet-ground"
        config = with_motion(project, motion(project, effect, not mode.endswith("draft")))
    assert save(project, config).status_code == 200
    response = c.get(f"/api/projects/{pid}/bundle")
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        doc = json.loads(archive.read("project.json"))
        assert doc["version"] == 2
        assert doc["states"]["reader_states"]["data"] == config
    restored = TestClient(create_app(tmp_path / "restored"))
    response = restored.post(
        "/api/project-bundles", files={"file": ("project.zip", response.content)}
    )
    assert response.status_code == 201, response.text
    new_pid = response.json()["id"]
    assert restored.get(f"/api/projects/{new_pid}/reader").json()["config"] == config
    assert restored.get(f"/api/projects/{new_pid}/source").content == RAW
    assert restored.post(f"/api/projects/{new_pid}/reader/exports").status_code == 202
    job = restored.get(f"/api/projects/{new_pid}/jobs").json()[0]
    assert job["state"] == "completed", job
    result = restored.get(job["result"]["download_url"])
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        content = json.loads(archive.read("reader.json"))
        expected = copy.deepcopy(config)
        direction = expected["illustrations"][0].get("motion")
        if direction:
            author_note = direction.pop("note").encode()
            assert all(author_note not in archive.read(name) for name in archive.namelist())
            if mode.endswith("draft"):
                expected["illustrations"][0]["motion"] = None
            else:
                direction.pop("evidence")
                direction["playback_only"] = True
        assert content["config"] == expected
        assert content["preview"] is False
        assert content["media"][asset["id"]]["width"] == 120
        assert content["media"][asset["id"]]["height"] == 80
        assert content["media"][asset["id"]]["url"] == f"./media/{asset['id']}.png"
        assert sha256(archive.read(f"media/{asset['id']}.png")) == asset["sha256"]
        assert archive.read("storygal-source/original.txt") == RAW
        assert archive.read("storygal-source/source.utf8.txt") == RAW


@pytest.mark.parametrize("mode", ["omitted", "static"])
def test_configuration_serialization_preserves_absence_vs_null(project, mode):
    config = copy.deepcopy(project[-1])
    if mode == "static":
        config["illustrations"][0]["motion"] = None
    parsed = Configuration(revision=0, **config).model_dump(exclude={"revision"})
    assert parsed == config
    assert ("motion" in parsed["illustrations"][0]) == (mode == "static")


RAIN_INVALID = [
    ("version", 0),
    ("version", True),
    ("version", "1"),
    ("effect", "camera-pan"),
    ("script", "alert('no executable values')"),
    ("width", 0),
    ("width", "120"),
    ("width", 120.0),
    ("width", True),
    ("height", 8193),
    ("after_byte", -1),
    ("after_byte", "12"),
    ("source_sha256", "A" * 64),
    ("image_sha256", "wrong"),
    ("evidence", "短"),
    ("evidence", " " * 8),
    ("evidence", "  短  " * 3),
    ("note", "短"),
    ("note", "a" * 301),
    ("note", " " * 12),
    ("note", "a a a a a"),
    ("note", "😀" * 4),
    ("note", "\ufeff" * 8),
    ("reviewed", 1),
    ("reviewed", "true"),
    ("areas", []),
    ("areas", [POLYGON] * 9),
    ("ground", []),
    ("ground", [POLYGON] * 9),
    ("ground", [[[0, 0], [0.5, 0.5], [1, 1]]]),
    ("ground", [[[0, 0], [1, 1], [0, 1], [0.8, 0]]]),
    ("areas", [[[0, 0], [1, 0]]]),
    ("areas", [[[0, 0], [1, 0], [1, 1], [0, 0]]]),
    ("areas", [[[0, 0], [0.5, 0.5], [1, 1]]]),
    ("areas", [[[0, 0], [1, 1], [0, 1], [0.8, 0]]]),
    ("areas", [[[0, 0], [0.8, 0], [0.4, 0], [0.8, 1], [0, 1]]]),
    ("areas", [[[0, 0], [1, 0], [0.5, 0], [1, 1], [0, 1]]]),
    ("areas", [[[0, 0], [1e-10, 0], [1, 1], [0, 1]]]),
    ("areas", [[[0, 0], [1, 0], [1, 1e-10]]]),
    ("areas", [[[0, 0, 0], [1, 0], [1, 1]]]),
    ("areas", [[[0, 0], [1.01, 0], [1, 1]]]),
    ("areas", [[[0, 0], [-0.01, 1], [1, 1]]]),
    ("areas", [[[0, 0], ["1", 0], [1, 1]]]),
    ("areas", [[[0, 0], [True, 0], [1, 1]]]),
    ("areas", [[None, [1, 0], [1, 1]]]),
    ("areas", [[{"x": 0, "y": 0}, [1, 0], [1, 1]]]),
    (
        "areas",
        [
            [
                [(1 + math.cos(i * math.tau / 65)) / 2, (1 + math.sin(i * math.tau / 65)) / 2]
                for i in range(65)
            ]
        ],
    ),
]


@pytest.mark.parametrize("field,value", RAIN_INVALID)
def test_api_rejects_unsafe_or_unbounded_rain_without_mutation(project, field, value):
    _, pid, r, _, _ = project
    direction = motion(project)
    direction[field] = value
    before = r.load(pid)
    response = save(project, with_motion(project, direction))
    assert response.status_code == 422, response.text
    assert r.load(pid) == before
    # The presentation layer validates internal calls independently of FastAPI.
    with pytest.raises(ValueError):
        r.save(pid, before[0], with_motion(project, direction))
    assert r.load(pid) == before


SHORE_INVALID = [
    ("bank", []),
    ("bank", [[0.4, 0.8]]),
    ("bank", [[0.4, 0.8], [0.4, 0.3]]),
    ("bank", [[0.8, 0.8], [0.2, 0.3]]),
    ("bank", [[0, 0]] * 65),
    ("bank", [[0, 0], [1, 2]]),
    ("hits", []),
    ("hits", [{"x": 0.4, "phase": 0, "length": 8, "gain": 1}] * 7),
    ("hits", [{"x": 0.01, "phase": 0, "length": 8, "gain": 1}]),
    ("hits", [{"x": 0.4, "phase": 8.1, "length": 8, "gain": 1}]),
    ("hits", [{"x": 0.4, "phase": -0.1, "length": 8, "gain": 1}]),
    ("hits", [{"x": 0.4, "phase": 0, "length": 6.4, "gain": 1}]),
    ("hits", [{"x": 0.4, "phase": 0, "length": 21, "gain": 1}]),
    ("hits", [{"x": 0.4, "phase": 0, "length": 8, "gain": 1.31}]),
    ("hits", [{"x": 0.4, "phase": 0, "length": 8, "gain": -0.1}]),
    ("hits", [{"x": 0.4, "phase": 0, "length": 8, "gain": 1, "url": "no"}]),
    ("water", [[[0, 0], [1, 1], [0, 1], [0.8, 0]]]),
    ("areas", [POLYGON]),
]


@pytest.mark.parametrize("field,value", SHORE_INVALID)
def test_api_rejects_unsafe_or_unbounded_shore_without_mutation(project, field, value):
    _, pid, r, _, _ = project
    direction = motion(project, "wave-impact-backwash")
    direction[field] = value
    before = r.load(pid)
    response = save(project, with_motion(project, direction))
    assert response.status_code == 422, response.text
    with pytest.raises(ValueError):
        r.save(pid, before[0], with_motion(project, direction))
    assert r.load(pid) == before


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("effect", ["rain-wet-ground", "wave-impact-backwash"])
def test_nonfinite_values_fail_closed_in_api_and_direct_save(project, number, effect):
    c, pid, r, _, _ = project
    direction = motion(project, effect)
    if effect == "rain-wet-ground":
        direction["areas"][0][0][0] = number
    else:
        direction["hits"][0]["phase"] = number
    config = with_motion(project, direction)
    before = r.load(pid)
    with pytest.raises(ValueError):
        r.save(pid, before[0], config)
    response = c.patch(
        f"/api/projects/{pid}/reader",
        content=json.dumps({"revision": before[0], **config}),
        headers={"content-type": "application/json"},
    )
    assert response.status_code in {400, 422}, response.text
    assert r.load(pid) == before


@pytest.mark.parametrize(
    "binding",
    ["source", "image", "width", "height", "anchor", "early", "late", "future", "not-exact"],
)
@pytest.mark.parametrize("reviewed", [False, True])
def test_binding_or_context_transplant_rejected_even_for_drafts(project, binding, reviewed):
    _, pid, r, _, _ = project
    direction = motion(project, reviewed=reviewed)
    config = with_motion(project, direction)
    if binding == "source":
        direction["source_sha256"] = "0" * 64
    elif binding == "image":
        direction["image_sha256"] = "0" * 64
    elif binding == "width":
        direction["width"] += 1
    elif binding == "height":
        direction["height"] += 1
    elif binding == "anchor":
        direction["after_byte"] += 1
    elif binding == "early":
        config["illustrations"][0]["after_byte"] = r.blocks(pid)[0]["byte_end"]
    elif binding == "late":
        config["illustrations"][0]["after_byte"] = r.blocks(pid)[-1]["byte_end"]
    elif binding == "future":
        direction["evidence"] = "最后一行是还未发生的告别"
    else:
        direction["evidence"] = "雨點落進院裡的水窪"
    before = r.load(pid)
    response = save(project, config)
    assert response.status_code == 400, response.text
    assert r.load(pid) == before


@pytest.mark.parametrize("value", ["rain-wet-ground", 1, True, [], {"effect": "rain-wet-ground"}])
def test_no_legacy_prose_or_incomplete_candidate_coercion(project, value):
    _, pid, r, _, _ = project
    before = r.load(pid)
    response = save(project, with_motion(project, value))
    assert response.status_code == 422, response.text
    with pytest.raises(ValueError):
        r.save(pid, before[0], with_motion(project, value))
    assert r.load(pid) == before


def test_changing_image_rejects_old_direction_but_explicit_static_is_safe(project):
    _, pid, r, asset, _ = project
    config = with_motion(project, motion(project, reviewed=True))
    assert save(project, config).status_code == 200
    output = io.BytesIO()
    Image.new("RGB", (120, 80), "teal").save(output, "PNG")
    replacement = r.upload(pid, r.load(pid)[0], output.getvalue(), "scene", "synthetic replacement")
    config["illustrations"][0]["image_asset_id"] = replacement["id"]
    before = r.load(pid)
    assert save(project, config).status_code == 400
    assert r.load(pid) == before
    assert r.state_assets(pid)[0]["sha256"] == asset["sha256"]
    config["illustrations"][0]["motion"] = None
    assert save(project, config).status_code == 200
    assert r.content(pid)["config"]["illustrations"][0]["motion"] is None


def test_motion_attestation_never_accepts_pending_image(project):
    _, pid, r, asset, _ = project
    r.accept(pid, r.load(pid)[0], asset["id"], "pending")
    config = with_motion(project, motion(project, reviewed=True))
    assert save(project, config).status_code == 200
    assert r.state_assets(pid)[0]["status"] == "pending"
    with pytest.raises(ValueError, match="尚未接受"):
        r.content(pid, strict=True)


@pytest.mark.parametrize(
    "bad", ["source", "image", "dimension", "anchor", "future", "geometry", "extra", "nonfinite"]
)
def test_import_rechecks_bindings_and_shapes_before_atomic_restore(project, bad):
    c, pid, r, _, _ = project
    assert save(project, with_motion(project, motion(project, reviewed=True))).status_code == 200
    response = c.get(f"/api/projects/{pid}/bundle")
    assert response.status_code == 200, response.text

    def tamper(doc):
        plate = doc["states"]["reader_states"]["data"]["illustrations"][0]
        direction = plate["motion"]
        if bad == "source":
            direction["source_sha256"] = "0" * 64
        elif bad == "image":
            direction["image_sha256"] = "0" * 64
        elif bad == "dimension":
            direction["width"] = 121
            doc["records"]["reader_assets"][0]["width"] = 121  # Forged metadata cannot fix it.
        elif bad == "anchor":
            plate["after_byte"] = r.blocks(pid)[-1]["byte_end"]
        elif bad == "future":
            direction["evidence"] = "最后一行是还未发生的告别"
        elif bad == "geometry":
            direction["areas"] = [[[0, 0], [1, 1], [0, 1], [0.8, 0]]]
        elif bad == "extra":
            direction["javascript"] = "no"
        else:
            direction["areas"][0][0][0] = float("nan")

    before = c.get("/api/projects").json()
    altered = repack(response.content, tamper)
    result = c.post("/api/project-bundles", files={"file": ("bad.zip", altered)})
    assert result.status_code == 400, result.text
    assert c.get("/api/projects").json() == before


@pytest.mark.parametrize("version", [1, 2])
def test_old_bundle_without_motion_remains_readable(project, version):
    c, pid, r, _, config = project
    assert save(project, config).status_code == 200
    archive = c.get(f"/api/projects/{pid}/bundle").content
    archive = repack(archive, lambda doc: doc.update(version=version))
    response = c.post("/api/project-bundles", files={"file": ("old.zip", archive)})
    assert response.status_code == 201, response.text
    plate = r.load(response.json()["id"])[1]["illustrations"][0]
    assert "motion" not in plate


def test_legacy_or_forged_dimension_metadata_cannot_override_actual_image(project):
    c, pid, r, asset, _ = project
    with r.store.db() as db:
        old = dict(asset)
        old.pop("width")
        old.pop("height")
        r.review.put(db, "reader_assets", pid, old)
    state = c.get(f"/api/projects/{pid}/reader").json()
    assert (state["assets"][0]["width"], state["assets"][0]["height"]) == (120, 80)
    with r.store.db() as db:
        old.update(width=999, height=999)
        r.review.put(db, "reader_assets", pid, old)
    config = with_motion(project, motion(project))
    assert save(project, config).status_code == 200
    content = r.content(pid, strict=True)
    assert (content["media"][asset["id"]]["width"], content["media"][asset["id"]]["height"]) == (
        120,
        80,
    )
    with r.store.db() as db:
        saved = r.review.item(db, "reader_assets", pid, asset["id"])
    assert saved["width"] == 999  # Read-only hydration does not rewrite historical records.


@pytest.mark.parametrize("reviewed", [False, True])
def test_production_reapply_preserves_identical_direction(project, reviewed):
    _, pid, r, asset, _ = project
    production = project[0].app.state.production
    shot = {
        "id": "court",
        "title": "潮水",
        "after_byte": project[-1]["illustrations"][0]["after_byte"],
        "image_asset_id": asset["id"],
        "moment": "浪花退回水面之后",
        "evidence": "江水撞向低矮的堤岸",
        "framing": "固定视角，只显露原文已发生的水面",
        "avoid": "不提前出现告别的人物",
    }
    production.save(pid, 0, sha256(RAW), {"budget": 1, "shots": [shot]}, approve="court")
    production.apply(pid, production.load(pid)[0], r.load(pid)[0])
    revision, config = r.load(pid)
    direction = motion(project, reviewed=reviewed)
    config["illustrations"][0]["motion"] = direction
    r.save(pid, revision, config)
    before = r.load(pid)[1]
    production.apply(pid, production.load(pid)[0], r.load(pid)[0])
    assert r.load(pid)[1] == before
    assert r.load(pid)[1]["illustrations"][0]["motion"] == direction


@pytest.mark.parametrize("change", ["image", "anchor"])
@pytest.mark.parametrize("static", [False, True])
def test_production_changed_binding_requires_direction_removal_but_keeps_static(
    project, change, static
):
    _, pid, r, asset, _ = project
    production = project[0].app.state.production
    shot = {
        "id": "court",
        "title": "潮水",
        "after_byte": project[-1]["illustrations"][0]["after_byte"],
        "image_asset_id": asset["id"],
        "moment": "浪花退回水面之后",
        "evidence": "江水撞向低矮的堤岸",
        "framing": "固定视角，只显露原文已发生的水面",
        "avoid": "不提前出现告别的人物",
    }
    production.save(pid, 0, sha256(RAW), {"budget": 1, "shots": [shot]}, approve="court")
    production.apply(pid, production.load(pid)[0], r.load(pid)[0])
    revision, config = r.load(pid)
    config["illustrations"][0]["motion"] = None if static else motion(project, reviewed=True)
    r.save(pid, revision, config)
    if change == "image":
        output = io.BytesIO()
        Image.new("RGB", (120, 80), "teal").save(output, "PNG")
        replacement = r.upload(
            pid, r.load(pid)[0], output.getvalue(), "scene", "synthetic new image"
        )
        shot["image_asset_id"] = replacement["id"]
    else:
        shot.update(after_byte=r.blocks(pid)[-1]["byte_end"], evidence=r.blocks(pid)[-1]["text"])
    production.save(
        pid, production.load(pid)[0], sha256(RAW), {"budget": 1, "shots": [shot]}, approve="court"
    )
    before = r.load(pid)
    if static:
        production.apply(pid, production.load(pid)[0], before[0])
        result = r.load(pid)[1]["illustrations"][0]
        assert result["motion"] is None
        assert result["image_asset_id"] == shot["image_asset_id"]
        assert result["after_byte"] == shot["after_byte"]
    else:
        with pytest.raises(ValueError, match="移除旧动效"):
            production.apply(pid, production.load(pid)[0], before[0])
        assert r.load(pid) == before


@pytest.mark.parametrize("effect", ["rain-wet-ground", "wave-impact-backwash"])
def test_maximum_bounded_recipe_is_saveable(project, effect):
    direction = motion(project, effect)
    if effect == "rain-wet-ground":
        direction.update(areas=[POLYGON] * 8, ground=[POLYGON] * 8, drops=128, rings=16)
    else:
        direction.update(
            water=[POLYGON] * 8,
            bank=[[i / 63, 0.6] for i in range(64)],
            hits=[{"x": 0.4, "phase": 8, "length": 20, "gain": 1.3}] * 6,
        )
    response = save(project, with_motion(project, direction))
    assert response.status_code == 200, response.text


def test_image_pixel_budget_is_independent_of_dimension_bounds(project):
    direction = motion(project)
    direction.update(width=8192, height=8192)
    response = save(project, with_motion(project, direction))
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "field",
    [
        "version",
        "image_sha256",
        "source_sha256",
        "width",
        "height",
        "after_byte",
        "evidence",
        "note",
        "reviewed",
        "areas",
        "ground",
        "drops",
        "rings",
    ],
)
def test_motion_never_invents_missing_provenance_or_geometry(project, field):
    direction = motion(project)
    direction.pop(field)
    response = save(project, with_motion(project, direction))
    assert response.status_code == 422, response.text


def test_rainless_ground_is_not_inferred_when_ripples_are_disabled(project):
    direction = motion(project)
    direction.update(ground=[], rings=0)
    response = save(project, with_motion(project, direction))
    assert response.status_code == 200, response.text
    assert project[2].content(project[1])["config"]["illustrations"][0]["motion"]["ground"] == []
