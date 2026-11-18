"""Editable recovery stays lossless while invalid references remain untrusted."""

import copy
import io
import json
import uuid
import wave
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_production_bundles import repack

from storygal import app as app_module
from storygal import bundles, llm, openai_speech, speech
from storygal.app import create_app
from storygal.reader_api import Configuration


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(app_module, "load_env", lambda *_: None)
    monkeypatch.setattr(llm, "api_key", lambda: "")
    monkeypatch.setattr(
        speech,
        "capabilities",
        lambda: {
            "provider": "macos-say",
            "model": "test-os",
            "version": 1,
            "format": "pcm",
            "voices": ["fixture"],
            "available": False,
        },
    )
    monkeypatch.setattr(
        openai_speech,
        "capabilities",
        lambda: {
            "provider": openai_speech.PROVIDER,
            "model": openai_speech.MODEL,
            "version": 1,
            "format": "pcm",
            "voices": openai_speech.VOICES,
            "available": False,
        },
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("No real synthesis in restore tests")

    monkeypatch.setattr(openai_speech, "render", forbidden)
    monkeypatch.setattr(speech, "render", forbidden)


@pytest.fixture
def project(tmp_path):
    c = TestClient(create_app(tmp_path / "source"))
    raw = "第一章 回家\n林遥说：「先听听您的想法。」\n雨慢慢停了。".encode()
    pid = c.post(
        "/api/projects", files={"file": ("test.txt", raw)}, data={"rights_status": "owned"}
    ).json()["id"]
    r, review = c.app.state.reader, c.app.state.review
    char = review.character(pid, review.state(pid)["revision"], "林遥", [], "")
    output = io.BytesIO()
    Image.new("RGBA", (40, 60), (0, 128, 128, 255)).save(output, "PNG")
    figure = review.upload_asset(
        pid,
        review.state(pid)["revision"],
        char["id"],
        output.getvalue(),
        "reference_and_figure",
        "synthetic fixture",
    )
    review.accept_asset(pid, review.state(pid)["revision"], figure["id"], "accepted", True)
    asset = r.upload(pid, r.load(pid)[0], output.getvalue(), "scene", "synthetic fixture")
    r.accept(pid, r.load(pid)[0], asset["id"], "accepted")
    config = Configuration(
        revision=0,
        title="测试",
        scenes=[
            {
                "id": "home",
                "title": "回家",
                "start_byte": 0,
                "asset_id": asset["id"],
                "character_ids": [char["id"]],
            }
        ],
        presentations=[
            {
                "id": "entrance",
                "scene_id": "home",
                "start_byte": 0,
                "kind": "dialogue",
                "image_asset_id": asset["id"],
                "cast": [
                    {"character_id": char["id"], "figure_asset_id": figure["id"], "slot": "left"}
                ],
            }
        ],
    ).model_dump(exclude={"revision"})
    r.save(pid, r.load(pid)[0], config)
    plan = {
        "budget": 1,
        "shots": [
            {
                "id": "conversation",
                "title": "倾听",
                "after_byte": r.blocks(pid)[1]["byte_end"],
                "moment": "等待回答",
                "evidence": "先听听您的想法",
                "framing": "近景",
                "avoid": "不能提前画出雨停",
                "image_asset_id": asset["id"],
                "actors": [{"character_id": char["id"]}],
            }
        ],
    }
    prod = c.app.state.production
    prod.save(pid, prod.load(pid)[0], c.app.state.store.get(pid)["canonical_sha256"], plan)
    return c, pid, char, asset, figure, raw


def restore(project, tmp_path):
    c, pid, *_ = project
    archive = c.get(f"/api/projects/{pid}/bundle")
    assert archive.status_code == 200, archive.text[:300]
    other = TestClient(create_app(tmp_path / str(uuid.uuid4())))
    response = other.post("/api/project-bundles", files={"file": ("project.zip", archive.content)})
    assert response.status_code == 201, response.text
    return other, response.json()


@pytest.mark.parametrize(
    "change", ["scene_character", "presentation_character", "plan_image", "figure"]
)
def test_restore_preserves_repairable_state_and_reports_issues(project, tmp_path, change):
    c, pid, char, asset, figure, raw = project
    r, review = c.app.state.reader, c.app.state.review
    if change == "presentation_character":
        rev, config = r.load(pid)
        config["scenes"][0]["character_ids"] = []
        r.save(pid, rev, config)
    if "character" in change:
        review.character(
            pid, review.state(pid)["revision"], "林遥", [], "", char["id"], "candidate"
        )
    elif change == "plan_image":
        r.accept(pid, r.load(pid)[0], asset["id"], "rejected")
    else:
        review.accept_asset(pid, review.state(pid)["revision"], figure["id"], "rejected", False)
    before = (r.load(pid), c.app.state.production.load(pid))
    other, imported = restore(project, tmp_path)
    new = imported["id"]
    assert imported["restore_issues"]
    assert other.app.state.reader.load(new) == before[0]
    assert other.app.state.production.load(new) == before[1]
    assert other.get(f"/api/projects/{new}/source").content == raw
    after_review = other.app.state.review.state(new)
    assert next(x for x in after_review["characters"] if x["id"] == char["id"])["status"] == (
        "candidate" if "character" in change else "confirmed"
    )
    content = other.get(f"/api/projects/{new}/reader/content").json()
    assert content["issues"] and content["preview"]
    with pytest.raises(ValueError):
        other.app.state.reader.content(new, strict=True)


def cloud_profile(project):
    c, pid, char, *_ = project
    s, review = c.app.state.speech, c.app.state.review
    did = review.state(pid)["dialogues"][0]["id"]
    review.assign(pid, review.state(pid)["revision"], [did], char["id"])
    result = c.patch(
        f"/api/projects/{pid}/speech/profiles/{char['id']}",
        json={
            "revision": s.load(pid)[0],
            "provider": openai_speech.PROVIDER,
            "voice": "cedar",
            "speed": 180,
            "instructions": "沉稳",
        },
    )
    assert result.status_code == 200, result.text
    return s, did


def test_cloud_profile_roundtrips_without_credentials(project, tmp_path):
    s, _ = cloud_profile(project)
    other, imported = restore(project, tmp_path)
    restored = other.app.state.speech.load(imported["id"])
    assert restored == s.load(project[1])
    assert next(iter(restored[1]["profiles"].values()))["model"] == openai_speech.MODEL


def test_historical_cloud_model_is_preserved_but_request_model_is_forbidden(project, tmp_path):
    s, _ = cloud_profile(project)
    c, pid, char, *_ = project
    result = c.patch(
        f"/api/projects/{pid}/speech/profiles/{char['id']}",
        json={
            "revision": s.load(pid)[0],
            "voice": "cedar",
            "speed": 180,
            "provider": openai_speech.PROVIDER,
            "model": "gpt-realtime-historical",
        },
    )
    assert result.status_code == 422
    s.mutate(
        pid,
        s.load(pid)[0],
        "test",
        lambda d: d["profiles"][char["id"]].update(
            model="gpt-realtime-historical",
        ),
    )
    other, imported = restore(project, tmp_path)
    assert other.app.state.speech.load(imported["id"]) == s.load(pid)


def test_cloud_wav_roundtrip_reuses_verified_audio_offline(project, tmp_path, monkeypatch):
    expected = cloud_take(project, monkeypatch)
    other, imported = restore(project, tmp_path)
    new = imported["id"]
    take = other.app.state.speech.state(new)["lines"][0]["segments"][0]["accepted"]
    assert take and take["imported"]
    assert other.get(take["url"]).content == expected
    assert take["model"] == take["profile"]["model"] == openai_speech.MODEL
    assert len(take["profile"]["instructions"]) == 2001
    assert other.app.state.reader.content(new, strict=True)["checks"]["source"]


def cloud_take(project, monkeypatch):
    s, did = cloud_profile(project)
    pid = project[1]
    s.profile(
        pid, s.load(pid)[0], project[2]["id"], "cedar", 180, openai_speech.PROVIDER, "沉" * 1000
    )
    s.line(pid, s.load(pid)[0], did, True, {}, "慢" * 1000)
    offline_caps = openai_speech.capabilities()
    monkeypatch.setattr(openai_speech, "capabilities", lambda: offline_caps | {"available": True})

    def synthetic(_text, _profile, target):
        with wave.open(str(target), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(24000)
            out.writeframes(b"\x10\x10" * 2400)
        return {}

    monkeypatch.setattr(openai_speech, "render", synthetic)
    s.synthesize(pid, did)
    segments = s.state(pid)["lines"][0]["segments"]
    s.accept(pid, s.load(pid)[0], did, {x["key"]: x["candidate"]["id"] for x in segments})
    expected = s.path(pid, segments[0]["candidate"]).read_bytes()
    monkeypatch.setattr(openai_speech, "capabilities", lambda: offline_caps)
    return expected


def assert_bad_bundle(project, tmp_path, mutate):
    c, pid, *_ = project
    raw = c.get(f"/api/projects/{pid}/bundle").content

    def corrupt(files):
        doc = json.loads(files["project.json"])
        mutate(doc)
        files["project.json"] = json.dumps(doc, ensure_ascii=False).encode()

    other = TestClient(create_app(tmp_path / "rejected"))
    response = other.post("/api/project-bundles", files={"file": ("bad.zip", repack(raw, corrupt))})
    assert response.status_code == 400, response.text
    assert other.get("/api/projects").json() == []
    assert not list((other.app.state.store.root / ".imports").glob("tmp*"))


@pytest.mark.parametrize(
    "failure",
    [
        "scene_character",
        "presentation_character",
        "figure",
        "figure_owner",
        "figure_type",
        "scene_image",
        "presentation_image",
        "image_type",
        "plan_character",
        "plan_image",
        "scene_anchor",
        "presentation_anchor",
        "plan_anchor",
        "dialogue",
        "reader_field",
        "speech_character",
        "speech_dialogue",
    ],
)
def test_restore_still_rejects_invalid_structure(project, tmp_path, failure):
    cloud_profile(project)

    def mutate(doc):
        config = doc["states"]["reader_states"]["data"]
        scene, presentation = config["scenes"][0], config["presentations"][0]
        shot = doc["states"]["production_states"]["data"]["shots"][0]
        foreign = str(uuid.uuid4())
        if failure == "scene_character":
            scene["character_ids"] = [foreign]
        elif failure == "presentation_character":
            presentation["cast"][0]["character_id"] = foreign
        elif failure == "figure":
            presentation["cast"][0]["figure_asset_id"] = foreign
        elif failure == "figure_owner":
            other_char = copy.deepcopy(doc["records"]["characters"][0])
            other_char.update(id=foreign, active_figure_id=None)
            doc["records"]["characters"].append(other_char)
            presentation["cast"][0]["character_id"] = foreign
        elif failure == "figure_type":
            doc["records"]["assets"][0]["kind"] = "reference"
        elif failure == "scene_image":
            scene["asset_id"] = foreign
        elif failure == "presentation_image":
            presentation["image_asset_id"] = foreign
        elif failure == "image_type":
            doc["records"]["reader_assets"][0]["kind"] = "cover"
        elif failure == "plan_character":
            shot["actors"][0]["character_id"] = foreign
        elif failure == "plan_image":
            shot["image_asset_id"] = foreign
        elif failure == "scene_anchor":
            scene["start_byte"] = 1
        elif failure == "presentation_anchor":
            presentation["start_byte"] = 1
        elif failure == "plan_anchor":
            shot["after_byte"] -= 1
        elif failure == "dialogue":
            doc["records"]["dialogues"][0]["text"] = "改写原文"
        elif failure == "reader_field":
            config["unknown"] = True
        elif failure == "speech_character":
            profiles = doc["states"]["speech_states"]["data"]["profiles"]
            profiles[foreign] = next(iter(profiles.values()))
        else:
            doc["states"]["speech_states"]["data"]["lines"][foreign] = {"selected": False}

    assert_bad_bundle(project, tmp_path, mutate)


@pytest.mark.parametrize(
    "failure",
    [
        "missing_model",
        "blank_model",
        "null_model",
        "model_type",
        "model_path",
        "unknown_field",
        "unknown_voice",
        "unknown_provider",
        "speed_type",
        "speed_range",
        "instructions",
    ],
)
def test_invalid_stored_cloud_profiles_are_not_silently_accepted(project, tmp_path, failure):
    cloud_profile(project)

    def mutate(doc):
        profile = next(iter(doc["states"]["speech_states"]["data"]["profiles"].values()))
        changes = {
            "blank_model": ("model", ""),
            "null_model": ("model", None),
            "model_type": ("model", 7),
            "model_path": ("model", "../bad"),
            "unknown_field": ("api_key", "synthetic-not-a-secret"),
            "unknown_voice": ("voice", "not-a-cloud-voice"),
            "unknown_provider": ("provider", "unknown"),
            "speed_type": ("speed", "180"),
            "speed_range": ("speed", 301),
            "instructions": ("instructions", "长" * 1001),
        }
        if failure == "missing_model":
            del profile["model"]
        else:
            key, value = changes[failure]
            profile[key] = value

    assert_bad_bundle(project, tmp_path, mutate)


@pytest.mark.parametrize("failure", ["model", "provider", "unknown_field", "reference", "text"])
def test_invalid_cloud_take_and_accepted_references_fail(project, tmp_path, monkeypatch, failure):
    cloud_take(project, monkeypatch)

    def mutate(doc):
        take = doc["records"]["speech_takes"][0]
        if failure == "model":
            take["model"] = "different-model"
        elif failure == "provider":
            take["provider"] = "macos-say"
        elif failure == "unknown_field":
            take["profile"]["extra"] = True
        elif failure == "text":
            take["text_sha256"] = "0" * 64
        else:
            line = next(iter(doc["states"]["speech_states"]["data"]["lines"].values()))
            line["accepted"][next(iter(line["accepted"]))] = str(uuid.uuid4())

    assert_bad_bundle(project, tmp_path, mutate)


@pytest.mark.parametrize("version", [1, 2])
def test_old_local_profile_and_reader_defaults_stay_readable(project, tmp_path, version):
    c, pid, char, *_ = project
    s = c.app.state.speech
    s.mutate(
        pid,
        s.load(pid)[0],
        "test",
        lambda d: d["profiles"].update(
            {
                char["id"]: {"voice": "historical-local-voice", "speed": 180},
            }
        ),
    )
    raw = c.get(f"/api/projects/{pid}/bundle").content

    def legacy(files):
        doc = json.loads(files["project.json"])
        doc["version"] = version
        config = doc["states"]["reader_states"]["data"]
        for key in ("presentations", "map_entries", "reading_layout", "illustrations"):
            config.pop(key, None)
        files["project.json"] = json.dumps(doc, ensure_ascii=False).encode()

    other = TestClient(create_app(tmp_path / "legacy"))
    result = other.post("/api/project-bundles", files={"file": ("old.zip", repack(raw, legacy))})
    assert result.status_code == 201, result.text
    new = result.json()["id"]
    assert other.get(f"/api/projects/{new}/source").content == project[-1]
    assert other.app.state.speech.load(new)[1] == s.load(pid)[1]
    assert other.app.state.reader.content(new, strict=True)["checks"]["source"]


def test_hash_mismatch_is_rejected_before_restore(project, tmp_path):
    c, pid, *_ = project
    raw = c.get(f"/api/projects/{pid}/bundle").content
    with zipfile.ZipFile(io.BytesIO(raw)) as original:
        files = {name: original.read(name) for name in original.namelist()}
    files["source.utf8.txt"] += "篡改".encode()
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    other = TestClient(create_app(tmp_path / "hash-rejected"))
    response = other.post("/api/project-bundles", files={"file": ("bad.zip", target.getvalue())})
    assert response.status_code == 400 and "哈希" in response.json()["detail"]
    assert other.get("/api/projects").json() == []


def test_preview_character_relaxation_never_allows_missing_ids(project):
    c, pid, *_ = project
    r = c.app.state.reader
    _, config = r.load(pid)
    config["scenes"][0]["character_ids"] = [str(uuid.uuid4())]
    with pytest.raises(ValueError, match="不存在"):
        r.validate(pid, config, check_characters=False)
    with pytest.raises(ValueError, match="不存在"):
        r.validate(pid, config, for_restore=True)


def test_reader_versions_include_production_revision_and_default_zero(project):
    c, pid, *_ = project
    r = c.app.state.reader
    with r.store.db() as db:
        assert r.version_state(db, pid)["production_revision"] == 1
        db.execute("DELETE FROM production_states WHERE project_id=?", (pid,))
        assert r.version_state(db, pid)["production_revision"] == 0
    assert r.content(pid)["versions"]["production_revision"] == 0


def test_preflight_reports_exact_inventory_without_reading_media(project, monkeypatch):
    c, pid, *_ = project
    archive = c.get(f"/api/projects/{pid}/bundle")
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        expected = {info.filename: info.file_size for info in z.infolist()}
    original_read = type(c.app.state.store.root).read_bytes

    def no_media_read(path):
        assert path.suffix not in {".png", ".wav", ".svg"}
        return original_read(path)

    monkeypatch.setattr(type(c.app.state.store.root), "read_bytes", no_media_read)
    response = c.get(f"/api/projects/{pid}/bundle/preflight")
    assert response.status_code == 200, response.text
    info = response.json()
    assert info["can_export"] and info["validation"] == "size_and_presence_only"
    assert info["uncompressed_bytes"] == sum(expected.values())
    assert info["members"] == len(expected)
    assert info["media_bytes"] == sum(size for name, size in expected.items() if "/" in name)
    assert info["largest_media"] and not info["missing_files"] and not info["errors"]
    assert info["limits"] == {
        "archive_bytes": 160_000_000,
        "uncompressed_bytes": 160_000_000,
        "members": 3000,
        "json_bytes": 5_000_000,
        "rows_per_table": 5000,
    }


@pytest.mark.parametrize("bound", ["bytes", "members", "json", "rows"])
def test_export_preflight_and_import_share_format_limits(project, monkeypatch, bound):
    c, pid, *_ = project
    archive = c.get(f"/api/projects/{pid}/bundle").content
    info = c.get(f"/api/projects/{pid}/bundle/preflight").json()
    if bound == "bytes":
        monkeypatch.setattr(bundles, "LIMIT", info["uncompressed_bytes"] - 1)
    elif bound == "members":
        monkeypatch.setattr(bundles, "MEMBER_LIMIT", info["members"] - 1)
    elif bound == "json":
        monkeypatch.setattr(bundles, "JSON_LIMIT", info["json_bytes"]["project.json"] - 1)
    else:
        monkeypatch.setattr(bundles, "ROW_LIMIT", 0)
    before = c.get("/api/projects").json()
    info = c.get(f"/api/projects/{pid}/bundle/preflight").json()
    assert not info["can_export"] and info["errors"]
    exported = c.get(f"/api/projects/{pid}/bundle")
    imported = c.post("/api/project-bundles", files={"file": ("old.zip", archive)})
    assert exported.status_code == imported.status_code == 400
    for error in info["errors"]:
        assert error in exported.json()["detail"]
        assert error in imported.json()["detail"]
    assert c.get("/api/projects").json() == before


def test_exact_format_boundaries_are_allowed():
    sizes = {"project.json": 5_000_000, "manifest.json": 5_000_000, "media": 150_000_000}
    sizes.update({f"file-{index}": 0 for index in range(2997)})
    assert len(sizes) == 3000 and sum(sizes.values()) == 160_000_000
    assert bundles.limit_errors(sizes, {"dialogues": [None] * 5000}) == []
    assert bundles.limit_errors(sizes | {"extra": 0})
    assert bundles.limit_errors(sizes | {"media": 150_000_001})
    assert bundles.limit_errors({"project.json": 5_000_001})
    assert bundles.limit_errors({}, {"dialogues": [None] * 5001})


def test_export_and_restore_at_exact_measured_limits(project, monkeypatch, tmp_path):
    c, pid, *_ = project
    info = c.get(f"/api/projects/{pid}/bundle/preflight").json()
    monkeypatch.setattr(bundles, "LIMIT", info["uncompressed_bytes"])
    monkeypatch.setattr(bundles, "MEMBER_LIMIT", info["members"])
    monkeypatch.setattr(bundles, "JSON_LIMIT", max(info["json_bytes"].values()))
    monkeypatch.setattr(bundles, "ROW_LIMIT", max(info["rows"].values()))
    assert c.get(f"/api/projects/{pid}/bundle/preflight").json()["can_export"]
    archive = c.get(f"/api/projects/{pid}/bundle")
    assert archive.status_code == 200, archive.text[:200]
    other = TestClient(create_app(tmp_path / "exact-limits"))
    restored = other.post("/api/project-bundles", files={"file": ("exact.zip", archive.content)})
    assert restored.status_code == 201, restored.text


def test_export_checks_zip_upload_size_not_just_uncompressed_size(project, monkeypatch):
    c, pid, *_ = project
    info = c.get(f"/api/projects/{pid}/bundle/preflight").json()
    # ZIP headers make a stored (uncompressed) ZIP larger than its file contents.
    original_zip = zipfile.ZipFile

    def stored_zip(file, mode="r", compression=zipfile.ZIP_STORED, **kwargs):
        return original_zip(file, mode, zipfile.ZIP_STORED, **kwargs)

    monkeypatch.setattr(bundles.zipfile, "ZipFile", stored_zip)
    monkeypatch.setattr(bundles, "LIMIT", info["uncompressed_bytes"] + 1)
    response = c.get(f"/api/projects/{pid}/bundle")
    assert response.status_code == 400, response.text
    assert "工程包超过" in response.json()["detail"]


def test_missing_or_corrupt_media_is_named_and_never_silently_skipped(project):
    c, pid, _, asset, *_ = project
    name = f"reader-assets/{asset['id']}.png"
    path = c.app.state.store.project_dir(pid) / name
    original = path.read_bytes()
    path.unlink()
    info = c.get(f"/api/projects/{pid}/bundle/preflight").json()
    assert not info["can_export"] and info["missing_files"] == [name]
    response = c.get(f"/api/projects/{pid}/bundle")
    assert response.status_code == 400 and name in response.json()["detail"]
    path.write_bytes(b"damaged")
    response = c.get(f"/api/projects/{pid}/bundle")
    assert response.status_code == 400 and name in response.json()["detail"]
    path.write_bytes(original)
    assert c.get(f"/api/projects/{pid}/bundle").status_code == 200


def test_import_names_missing_recorded_media_without_creating_project(project, tmp_path):
    c, pid, _, asset, *_ = project
    archive = c.get(f"/api/projects/{pid}/bundle").content
    name = f"reader-assets/{asset['id']}.png"
    damaged = repack(archive, lambda files: files.pop(name))
    other = TestClient(create_app(tmp_path / "missing-media"))
    response = other.post("/api/project-bundles", files={"file": ("missing.zip", damaged)})
    assert response.status_code == 400 and name in response.json()["detail"]
    assert other.get("/api/projects").json() == []


def test_export_refuses_structurally_unrestorable_state_without_publishing(project):
    c, pid, *_ = project
    c.get(f"/api/projects/{pid}/bundle/preflight")  # initialize the same snapshot defaults
    before = c.get("/api/projects").json()
    with c.app.state.store.db() as db:
        row = db.execute("SELECT data FROM reader_states WHERE project_id=?", (pid,)).fetchone()
        config = json.loads(row[0])
        config["scenes"][0]["character_ids"] = [str(uuid.uuid4())]
        db.execute("UPDATE reader_states SET data=? WHERE project_id=?", (json.dumps(config), pid))
    response = c.get(f"/api/projects/{pid}/bundle")
    assert response.status_code == 400 and "恢复校验" in response.json()["detail"]
    assert c.get("/api/projects").json() == before
    assert not list((c.app.state.store.root / ".imports").glob("tmp*"))


def test_isolated_image_audio_edit_and_second_restore_remain_lossless(
    project, tmp_path, monkeypatch
):
    c, pid, _, asset, _, raw = project
    audio = cloud_take(project, monkeypatch)
    original_image = (
        c.app.state.store.project_dir(pid) / f"reader-assets/{asset['id']}.png"
    ).read_bytes()
    original_plan = c.app.state.production.load(pid)
    first, imported = restore(project, tmp_path)
    new = imported["id"]
    assert first.app.state.production.load(new) == original_plan
    assert first.get(f"/api/projects/{new}/source").content == raw
    assert (
        first.app.state.store.project_dir(new) / f"reader-assets/{asset['id']}.png"
    ).read_bytes() == original_image
    take = first.app.state.speech.state(new)["lines"][0]["segments"][0]["accepted"]
    assert first.get(take["url"]).content == audio
    reader = first.app.state.reader
    rev, config = reader.load(new)
    config["title"] = "恢复后继续编辑"
    reader.save(new, rev, config)
    edited = first.get(f"/api/projects/{new}/bundle")
    assert edited.status_code == 200, edited.text[:200]
    second = TestClient(create_app(tmp_path / "second-restore"))
    result = second.post("/api/project-bundles", files={"file": ("edited.zip", edited.content)})
    assert result.status_code == 201, result.text
    final = result.json()["id"]
    assert second.app.state.reader.load(final) == reader.load(new)
    assert second.app.state.production.load(final) == original_plan
    assert second.get(f"/api/projects/{final}/source").content == raw
    assert (
        second.app.state.store.project_dir(final) / f"reader-assets/{asset['id']}.png"
    ).read_bytes() == original_image
    take = second.app.state.speech.state(final)["lines"][0]["segments"][0]["accepted"]
    assert second.get(take["url"]).content == audio


def test_player_packages_never_publish_authoring_records_even_for_accepted_audio(
    project, monkeypatch
):
    c, pid, char, _scene, figure, _raw = project
    base = f"/api/projects/{pid}"
    review = c.app.state.review
    rejected = review.character(
        pid, review.state(pid)["revision"], "旧候选", [], "PRIVATE_REJECTED"
    )
    review.character(
        pid,
        review.state(pid)["revision"],
        "旧候选",
        [],
        "PRIVATE_REJECTED",
        rejected["id"],
        "rejected",
    )
    expected = cloud_take(project, monkeypatch)
    accepted = c.app.state.speech.state(pid)["lines"][0]["segments"][0]["accepted"]
    secrets = [b"PRIVATE_REJECTED", *[s.encode() for s in ("沉" * 1000, "慢" * 1000)]]
    editable = c.get(base + "/bundle")
    with zipfile.ZipFile(io.BytesIO(editable.content)) as z:
        assert all(x in z.read("project.json") for x in secrets)
    for standalone in (True, False):
        params = (
            {}
            if standalone
            else {
                "simplified": "true",
                "reader_revision": c.get(base + "/exports/compatibility").json()["reader_revision"],
            }
        )
        job_id = c.post(
            base + ("/reader/exports" if standalone else "/exports"), params=params
        ).json()["job_id"]
        job = next(j for j in c.get(base + "/jobs").json() if j["id"] == job_id)
        assert job["state"] == "completed", job["error"]
        with zipfile.ZipFile(io.BytesIO(c.get(job["result"]["download_url"]).content)) as z:
            assert not any(x in z.read(n) for n in z.namelist() for x in secrets)
            if standalone:
                public = json.loads(z.read("reader.json"))
                assert "profile" not in public["media"][accepted["id"]]
                assert z.read(f"media/{accepted['id']}.wav") == expected
            else:
                public = json.loads(z.read("storygal-manifest.json"))
                assert public["checks"]["parser"]["passed"]
                assert not ({"speech", "review", "visual"} & public.keys())
                assert public["vocal_assets"] == [
                    {k: accepted[k] for k in ("id", "sha256", "duration", "provider", "model")}
                ]
                assert public["figure_assets"][0]["id"] == figure["id"]
                assert public["figure_assets"][0]["license"] == "synthetic fixture"
                assert z.read(f"game/vocal/{accepted['id']}.wav") == expected
                assert any(u.get("speaker_name") == char["display_name"] for u in public["units"])
    # A candidate can keep private pronunciation and performance directions
    # even if it previously had an accepted take. No revision publishes them.
    speech = c.app.state.speech
    line = speech.state(pid)["lines"][0]
    speech.line(
        pid,
        speech.load(pid)[0],
        line["id"],
        False,
        {line["segments"][0]["key"]: "PRIVATE_SPOKEN"},
        "PRIVATE_LINE_DIRECTION",
    )
    report = c.get(base + "/exports/compatibility").json()
    job_id = c.post(
        base + "/exports",
        params={"simplified": "true", "reader_revision": report["reader_revision"]},
    ).json()["job_id"]
    job = next(j for j in c.get(base + "/jobs").json() if j["id"] == job_id)
    assert job["state"] == "completed", job["error"]
    with zipfile.ZipFile(io.BytesIO(c.get(job["result"]["download_url"]).content)) as z:
        assert not any(n.startswith("game/vocal/") for n in z.namelist())
        assert all(
            all(
                x not in z.read(n) for x in [*secrets, b"PRIVATE_SPOKEN", b"PRIVATE_LINE_DIRECTION"]
            )
            for n in z.namelist()
        )


def test_private_editorial_roundtrip_keeps_open_deferred_resolved_and_stale_work(project, tmp_path):
    c, pid, *_ = project
    p = f"/api/projects/{pid}"
    anchor = c.app.state.reader.blocks(pid)[1]["byte_start"]
    original = None
    for i, (status, reason) in enumerate(
        [("deferred", "等作者回来"), ("resolved", "已复核"), ("open", "")]
    ):
        saved = c.post(
            p + "/reader/editorial",
            json={
                "revision": i,
                "anchor": anchor,
                "state": status,
                "category": "cast",
                "note": f"私有意见-{status}",
                "reason": reason,
            },
        )
        assert saved.status_code == 200, saved.text
        original = saved.json()
        if i == 0:
            reader = c.app.state.reader
            rev, cfg = reader.load(pid)
            reader.save(pid, rev, cfg | {"subtitle": "新版本"})  # preserve stale version receipts
    archive = c.get(p + "/bundle")
    assert archive.status_code == 200, archive.text[:100]
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        doc = json.loads(z.read("project.json"))
        assert doc["version"] == 5
        assert doc["states"]["reader_editorial"] == {"revision": 3, "data": original["issues"]}
        assert "不要作为读者版公开分享" in z.read("README.txt").decode()
    other = TestClient(create_app(tmp_path / "fresh"))
    imported = other.post("/api/project-bundles", files={"file": ("editable.zip", archive.content)})
    assert imported.status_code == 201, imported.text
    new = "/api/projects/" + imported.json()["id"]
    assert not imported.json()["restore_notices"] and not imported.json()["restore_issues"]
    assert other.get(new + "/reader/editorial").json() == original
    assert other.get(new + "/delivery").json()["records"] == []
    warnings = {w["detail"] for w in other.get(new + "/delivery").json()["warnings"]}
    assert warnings == {w["detail"] for w in c.get(p + "/delivery").json()["warnings"]}
    for label, expected in [("open", True), ("deferred", True), ("resolved", False)]:
        assert any("私有意见-" + label in w for w in warnings) is expected
    rejected = other.post(
        new + "/reader/editorial",
        json={
            "revision": 0,
            "anchor": anchor,
            "category": "cast",
            "note": "old edit",
            "state": "open",
            "reason": "",
        },
    )
    assert rejected.status_code == 409 and other.get(new + "/reader/editorial").json() == original


@pytest.mark.parametrize(
    "invalid",
    [
        "split-character",
        "range",
        "missing-reason",
        "duplicate-id",
        "future-version",
        "missing-field",
    ],
)
def test_private_editorial_bad_import_never_partially_restores(project, tmp_path, invalid):
    c, pid, *_ = project
    anchor = c.app.state.reader.blocks(pid)[1]["byte_start"]
    p = f"/api/projects/{pid}"
    for n in range(2):
        assert c.post(
            p + "/reader/editorial",
            json={
                "revision": n,
                "anchor": anchor,
                "state": "open",
                "category": "map",
                "note": "图例待核对",
                "reason": "",
            },
        ).is_success
    archive = c.get(p + "/bundle")
    assert archive.is_success
    from test_reader_motion import repack as with_inventory

    def change(doc):
        items = doc["states"]["reader_editorial"]["data"]
        if invalid == "split-character":
            items[0]["anchor"] += 1
        elif invalid == "range":
            items[0]["anchor"] = 999999
        elif invalid == "missing-reason":
            items[0]["state"] = "deferred"
        elif invalid == "duplicate-id":
            items[0]["id"] = items[1]["id"]
        elif invalid == "future-version":
            items[1]["versions"]["reader_revision"] += 100
        else:
            del items[1]["note"]

    other = TestClient(create_app(tmp_path / "fresh"))
    imported = other.post(
        "/api/project-bundles",
        files={"file": ("edited.zip", with_inventory(archive.content, change))},
    )
    assert imported.status_code == 400, imported.text
    assert other.get("/api/projects").json() == []


def test_editorial_coverage_notice_only_for_old_packages(project, tmp_path):
    c, pid, *_ = project
    data = c.get(f"/api/projects/{pid}/bundle").content
    # The pre-0.6.1 inventory omitted the new optional count. Don't claim
    # these old empty snapshots prove there were no issues in the original.
    older = repack(data, lambda _files: None)
    other = TestClient(create_app(tmp_path / "fresh"))
    for blob, legacy in ((data, False), (older, True)):
        restored = other.post("/api/project-bundles", files={"file": ("editable.zip", blob)})
        assert restored.is_success, restored.text
        j = restored.json()
        assert j["restore_issues"] == []
        assert bool(j["restore_notices"]) is legacy
        assert other.get(f"/api/projects/{j['id']}/reader/editorial").json() == {
            "revision": 0,
            "issues": [],
        }


def test_backup_refuses_to_silently_drop_issue_added_during_validation(project, monkeypatch):
    c, pid, *_ = project
    p = f"/api/projects/{pid}"
    unit = c.app.state.reader.blocks(pid)[1]
    bundles = c.app.state.bundles
    original = bundles.import_project

    def changed_after_snapshot(raw, **kwargs):
        result = original(raw, **kwargs)
        assert c.post(
            p + "/reader/editorial",
            json={
                "revision": 0,
                "anchor": unit["byte_start"],
                "category": "reading",
                "note": "刚添加的待办意见",
                "state": "open",
                "reason": "",
            },
        ).is_success
        return result

    monkeypatch.setattr(bundles, "import_project", changed_after_snapshot)
    response = c.get(p + "/bundle")
    assert response.status_code == 400 and "制作意见发生修改" in response.text
    assert c.get(p + "/reader/editorial").json()["revision"] == 1
