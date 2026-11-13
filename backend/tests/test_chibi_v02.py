"""Public bootstrap integrity and Chibi's editable, portable v0.2 showcase."""

import copy
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import build_chibi_demo as builder
from chibi_source import (
    digest,
    encoded,
    preflight,
    read_zip,
    verify_content,
    verify_inventory,
)


def inventory(files):
    files = {k: v for k, v in files.items() if k != "storygal-delivery.json"}
    files["storygal-delivery.json"] = encoded(
        {
            "schema_version": 1,
            "export_id": "test-only",
            "files": {n: {"bytes": len(b), "sha256": digest(b)} for n, b in files.items()},
        }
    )
    return files


@pytest.fixture
def tiny(tmp_path):
    # Deliberately has Unicode indentation, which bytes.strip() does not remove.
    raw = "甲。\n　　乙。".encode()
    media = {
        "figure-id": {
            "id": "figure-id",
            "type": "figure",
            "sha256": digest(b"fixture"),
            "url": "./media/figure-id.png",
            "sample_key": "test-person",
        }
    }
    content = {
        "project": {"id": "public-work", "sha256": digest(raw), "canonical_sha256": digest(raw)},
        "characters": {"character": {"name": "测试角色"}},
        "config": {"illustrations": [{"id": "shot"}], "presentations": []},
        "presentations": [],
        "map": {"phases": []},
        "media": media,
        "blocks": [
            {"byte_start": 0, "byte_end": 6, "text": "甲。", "audio": [], "runs": []},
            {
                "byte_start": 13,
                "byte_end": 19,
                "text": "乙。",
                "audio": [],
                "runs": [
                    {
                        "byte_start": 13,
                        "byte_end": 19,
                        "text": "乙。",
                        "take_id": None,
                        "speaker_id": None,
                    }
                ],
            },
        ],
    }
    files = inventory(
        {
            "reader.json": encoded(content),
            "storygal-source/original.txt": raw,
            "storygal-source/source.utf8.txt": raw,
            "media/figure-id.png": b"fixture",
        }
    )
    archive = builder.pack(files)
    recipe = {
        "source_archive": {"sha256": digest(archive)},
        "source_sha256": digest(raw),
        "public_work_id": "public-work",
        "expected": {
            "illustrations": 1,
            "characters": 1,
            "portraits": 1,
            "presentations": 0,
            "map_phases": 0,
            "media": 1,
        },
        "plan": {"shots": [{"id": "shot"}]},
    }
    recipe_raw = encoded(recipe)
    review = {
        "format": "taleprism-chibi-visual-review",
        "version": 1,
        "reviewer": "assistant",
        "creator_final_art_review": "pending",
        "source_archive_sha256": digest(archive),
        "recipe_sha256": digest(recipe_raw),
        "dependencies": {n: digest(b) for n, b in files.items() if n != "storygal-delivery.json"},
        "images": [
            {
                "asset_id": "figure-id",
                "sha256": digest(b"fixture"),
                "sample_key": "test-person",
                "inspection": "合成测试记录，不构成真实图片检查。",
            }
        ],
        "shots": {"shot": "合成测试记录，只用于校验完整性流程。"},
    }
    source, rp, vp = [tmp_path / name for name in ("input.zip", "recipe.json", "review.json")]
    source.write_bytes(archive)
    rp.write_bytes(recipe_raw)
    vp.write_bytes(encoded(review))
    return source, rp, vp, files, recipe, review


def test_preflight_accepts_unicode_indentation_and_reads_once(tiny):
    source, rp, vp, files, *_ = tiny
    result = preflight(source, rp, vp)
    assert result[2] == files
    source.write_bytes(b"changed after verification")
    assert result[2]["storygal-source/original.txt"].decode() == "甲。\n　　乙。"


def test_wrong_public_archive_fails_before_rebuild(tiny, tmp_path, monkeypatch):
    source, rp, vp, *_ = tiny
    monkeypatch.setattr(builder, "RECIPE", rp)
    monkeypatch.setattr(builder, "REVIEW", vp)
    monkeypatch.setattr(builder, "rebuild", lambda *args: pytest.fail("must not create a project"))
    source.write_bytes(b"unreviewed input")
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="固定"):
        builder.build(source, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "recipe",
        "source_review",
        "dependencies_missing",
        "dependencies_extra",
        "dependency_hash",
        "image_missing",
        "image_hash",
        "image_notes",
        "shot_missing",
        "shot_notes",
        "creator_approval",
    ],
)
def test_review_cannot_be_replayed_against_changed_inputs(tiny, mutation):
    source, rp, vp, _, _, review = tiny
    if mutation == "recipe":
        rp.write_bytes(rp.read_bytes() + b" ")
    elif mutation == "source_review":
        review["source_archive_sha256"] = "0" * 64
    elif mutation == "dependencies_missing":
        review["dependencies"].pop("storygal-source/original.txt")
    elif mutation == "dependencies_extra":
        review["dependencies"]["unknown.png"] = "0" * 64
    elif mutation == "dependency_hash":
        review["dependencies"]["media/figure-id.png"] = "0" * 64
    elif mutation == "image_missing":
        review["images"] = []
    elif mutation == "image_hash":
        review["images"][0]["sha256"] = "0" * 64
    elif mutation == "image_notes":
        review["images"][0]["inspection"] = " " * 20
    elif mutation == "shot_missing":
        review["shots"] = {}
    elif mutation == "shot_notes":
        review["shots"]["shot"] = " " * 20
    else:
        review["creator_final_art_review"] = "passed"
    vp.write_bytes(encoded(review))
    with pytest.raises(ValueError):
        preflight(source, rp, vp)


@pytest.mark.parametrize("mutation", ["missing", "extra", "hash", "bytes", "version"])
def test_internal_inventory_is_independently_verified(tiny, mutation):
    files = copy.deepcopy(tiny[3])
    if mutation == "missing":
        files.pop("reader.json")
    elif mutation == "extra":
        files["unexpected.txt"] = b"unexpected"
    else:
        manifest = json.loads(files["storygal-delivery.json"])
        if mutation == "hash":
            manifest["files"]["reader.json"]["sha256"] = "0" * 64
        elif mutation == "bytes":
            manifest["files"]["reader.json"]["bytes"] += 1
        else:
            manifest["schema_version"] = 99
        files["storygal-delivery.json"] = encoded(manifest)
    with pytest.raises(ValueError):
        verify_inventory(files)


@pytest.mark.parametrize("mutation", ["source", "block", "run", "media", "audio", "identity"])
def test_content_verifies_source_offsets_identity_and_no_audio(tiny, mutation):
    files = copy.deepcopy(tiny[3])
    content = json.loads(files["reader.json"])
    if mutation == "source":
        files["storygal-source/original.txt"] += b"!"
    elif mutation == "block":
        content["blocks"][1]["text"] = "改。"
    elif mutation == "run":
        content["blocks"][1]["runs"][0]["byte_end"] -= 1
    elif mutation == "media":
        content["media"]["figure-id"]["url"] = "https://untrusted.invalid/a.png"
    elif mutation == "audio":
        files["private.wav"] = b"private recording"
    else:
        content["project"]["id"] = "different-public-work"
    files["reader.json"] = encoded(content)
    with pytest.raises(ValueError):
        verify_content(files, tiny[4])


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a\\b", "a//b"])
def test_zip_paths_never_escape_or_alias(name):
    with pytest.raises(ValueError):
        read_zip(builder.pack({name: b"ignored"}))


def test_duplicate_zip_entry_is_rejected():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("duplicate.txt", b"1")
        with pytest.warns(UserWarning):
            archive.writestr("duplicate.txt", b"2")
    with pytest.raises(ValueError, match="重复"):
        read_zip(stream.getvalue())


def test_inline_data_preserves_the_same_public_identity():
    previous = {"project": {"id": "new-local-id"}}
    content = {"project": {"id": "stable-public-id"}}
    files = {"reader-data.js": b'window.__STORYGAL_DATA__ = {"project":{"id":"new-local-id"}};'}
    builder.sync_reader_data(files, previous, content)
    assert b"stable-public-id" in files["reader-data.js"]
    assert b"new-local-id" not in files["reader-data.js"]
    with pytest.raises(ValueError, match="格式未知"):
        builder.sync_reader_data({"reader-data.js": b"unknown format"}, previous, content)


def test_recorded_recipe_is_source_bound_and_has_real_shared_scene():
    from storygal.production import Plan

    recipe_raw = builder.RECIPE.read_bytes()
    recipe = json.loads(recipe_raw)
    review = json.loads(builder.REVIEW.read_bytes())
    assert review["recipe_sha256"] == digest(recipe_raw)
    assert review["creator_final_art_review"] == "pending"
    assert len(review["images"]) == 27
    assert len(review["dependencies"]) == 30
    plan = Plan.model_validate(recipe["plan"]).model_dump()
    assert len(plan["shots"]) == 12 and len(plan["scenes"]) == 9
    water = [s for s in plan["shots"] if s["continuity"]["scene_id"] == "chibi-waterfront"]
    assert [s["id"] for s in water] == [
        "river-overlook",
        "huanggai-departure",
        "caocao-watch",
        "fire-panorama",
    ]
    assert all(s["status"] == "draft" and not s["continuity_check"] for s in plan["shots"])
    assert len({s["continuity"]["changes"] for s in water}) == 4
    assert recipe["source_archive"]["file"] == "taleprism-v0.1.0-chibi-reader.zip"
    assert review["asset_edits"] == []


def test_legacy_output_is_protected(tmp_path):
    with pytest.raises(ValueError, match="历史发布"):
        builder.build(tmp_path / "no-input.zip", ROOT / ".release/chibi-demo")


@pytest.fixture(scope="module")
def real_build(tmp_path_factory):
    source = Path(
        os.environ.get(
            "TALEPRISM_CHIBI_SOURCE",
            ROOT / ".release/chibi-demo/taleprism-v0.1.0-chibi-reader.zip",
        )
    )
    if not source.is_file():
        pytest.skip("optional pinned public v0.1.0 Chibi ZIP; no private sample required")
    if not (ROOT / "frontend/dist/index.html").is_file():
        pytest.skip("build the reader frontend before full public integration")
    out = tmp_path_factory.mktemp("public-chibi")
    record = builder.build(source, out)
    return source, out, record


def test_full_public_rebuild_preserves_source_media_choreography_and_bookmark_keys(real_build):
    source, out, record = real_build
    old = read_zip(source.read_bytes())
    old_content = json.loads(old["reader.json"])
    reader_item = next(a for a in record["artifacts"] if a["kind"] == "reader")
    new = read_zip((out / reader_item["file"]).read_bytes())
    verify_inventory(new)
    content = json.loads(new["reader.json"])
    assert record["version"] == "0.2.0"
    assert content["project"]["id"] == old_content["project"]["id"]
    assert content["project"]["canonical_sha256"] == old_content["project"]["canonical_sha256"]
    assert content["blocks"] == old_content["blocks"]
    assert content["presentations"] == old_content["presentations"]
    assert content["map"] == old_content["map"]
    assert [p["id"] for p in content["config"]["illustrations"]] == [
        p["id"] for p in old_content["config"]["illustrations"]
    ]
    assert new["storygal-source/original.txt"] == old["storygal-source/original.txt"]
    for asset in content["media"].values():
        assert new[asset["url"][2:]] == old[asset["url"][2:]]
    assert record["creator_final_art_review"] == "pending"
    assert (out / "chibi-demo-manifest.json").is_file()
    for artifact in record["artifacts"]:
        raw = (out / artifact["file"]).read_bytes()
        assert len(raw) == artifact["bytes"] and digest(raw) == artifact["sha256"]


def test_editable_public_project_contains_no_speech_and_scoped_checks_survive_import(
    real_build, tmp_path
):
    from fastapi.testclient import TestClient

    from storygal.app import create_app

    _, out, record = real_build
    item = next(a for a in record["artifacts"] if a["kind"] == "project")
    raw = (out / item["file"]).read_bytes()
    files = read_zip(raw)
    doc = json.loads(files["project.json"])
    assert doc["records"]["speech_takes"] == []
    assert doc["states"]["speech_states"]["data"] == {"profiles": {}, "lines": {}}
    assert not any(n.startswith("audio/") for n in files)
    with TestClient(create_app(tmp_path / "consumer")) as client:
        response = client.post("/api/project-bundles", files={"file": ("public.zip", raw)})
        assert response.status_code == 201, response.text
        assert response.json()["restore_issues"] == []
        pid = response.json()["id"]
        assert pid != record["public_work_id"]
        production = client.app.state.production
        revision, plan = production.load(pid)
        assert all(s["continuity_check"]["status"] == "passed" for s in plan["shots"])
        assert all(
            s["continuity_check"]["basis"]["source_sha256"] == record["source_sha256"]
            for s in plan["shots"]
        )
        response = client.post(
            f"/api/projects/{pid}/production/river-overlook/continuity-check",
            json={
                "revision": revision,
                "decision": "revoked",
                "reviewer": "assistant",
                "notes": "自动回归：撤销水域母镜头，验证依赖检查不会绕过。",
            },
        )
        assert response.status_code == 200, response.text
        shots = production.load(pid)[1]["shots"]
        assert all(
            s["continuity_check"]["status"] != "passed"
            for s in shots
            if s["continuity"]["scene_id"] == "chibi-waterfront"
        )
        assert all(
            s["continuity_check"]["status"] == "passed"
            for s in shots
            if s["continuity"]["scene_id"] != "chibi-waterfront"
        )
        client.post(f"/api/projects/{pid}/reader/exports")
        assert client.app.state.store.jobs(pid)[0]["state"] == "failed"
        assert client.app.state.delivery.state(pid)["records"] == []
