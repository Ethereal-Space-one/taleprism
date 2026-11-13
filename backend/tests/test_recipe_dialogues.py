"""Recipe dialogue tasks resolve immutable UTF-8 ranges before any project is created."""

import copy
import importlib.util
import json
import wave
import zipfile
from pathlib import Path

import httpx
import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
STORY = "开场\n甲说：「好。」\n乙说：“好。”\n甲说：「走吧🙂。」\n乙说：「他说『等一等』，我答应了。」\n风穿过站台。"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def anchored(source, text, character, occurrence=0):
    raw = source.encode("utf-8")
    start = -1
    for _ in range(occurrence + 1):
        start = raw.index(text.encode("utf-8"), start + 1)
    return {
        "text": text,
        "character": character,
        "byte_start": start,
        "byte_end": start + len(text.encode("utf-8")),
    }


@pytest.fixture
def builder():
    spec = importlib.util.spec_from_file_location(
        "recipe_dialogues_builder", REPO / "tools/build_content_pack.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def recipe_path(tmp_path):
    root = tmp_path / "recipe"
    root.mkdir()
    (root / "source.txt").write_bytes(STORY.encode("utf-8"))
    Image.new("RGB", (80, 45), "navy").save(root / "scene.png")
    recipe = {
        "title": "重复对白回归",
        "subtitle": "合成测试",
        "source": "source.txt",
        "rights_status": "owned",
        "license": "synthetic fixture",
        "style": "合成平色素材",
        "budget": 1,
        "cover": "cover",
        "background": "station",
        "characters": [
            {"name": "甲", "description": "第一位说话人"},
            {"name": "乙", "description": "第二位说话人"},
        ],
        "images": [
            {"key": "cover", "file": "scene.png", "title": "封面", "kind": "cover"},
            {"key": "station", "file": "scene.png", "title": "站台", "kind": "scene"},
        ],
        # Deliberately reverse source order: the task list is not an occurrence index.
        "dialogues": [
            anchored(STORY, "好。", "乙", 1),
            {"text": "走吧🙂。", "character": "甲", "voice_prefix": "Tingting"},
            anchored(STORY, "好。", "甲"),
            anchored(STORY, "他说『等一等』，我答应了。", "乙"),
        ],
        "shots": [
            {
                "id": "station",
                "title": "站台",
                "marker": "风穿过站台。",
                "image": "station",
                "moment": "空站台吹过一阵风",
                "evidence": "风穿过站台。",
                "framing": "固定机位远景",
                "avoid": "不增加原文未出现的人物",
                "actors": [],
            }
        ],
    }
    path = root / "recipe.json"
    write_json(path, recipe)
    return path


def reject_before_client(builder, recipe_path, tmp_path, match, with_audio=True):
    before = {p.name: p.read_bytes() for p in recipe_path.parent.iterdir()}

    def no_client(**_kwargs):
        pytest.fail("Invalid recipes must fail before constructing a client or a project")

    destination = tmp_path / "output" / "project.zip"
    with pytest.raises(ValueError, match=match):
        # Even an audio-enabled request must fail before any service can be contacted.
        builder.build(
            recipe_path,
            "http://unused.invalid",
            destination,
            with_audio=with_audio,
            client_factory=no_client,
        )
    assert not destination.parent.exists()
    assert {p.name: p.read_bytes() for p in recipe_path.parent.iterdir()} == before


@pytest.mark.parametrize(
    ("character", "field"),
    [
        ({"name": "丙"}, "description"),
        ({"name": "丙", "description": None}, "description"),
        ({"name": "丙", "description": 123}, "description"),
        ({"name": "丙", "description": "字" * 2000 + " "}, "description"),
        ({"name": "丙" * 40 + " ", "description": ""}, "name"),
    ],
    ids=["missing-description", "null-description", "numeric-description", "long-description", "long-name"],
)
def test_invalid_character_payload_is_rejected_before_project_creation(
    builder, recipe_path, tmp_path, character, field
):
    recipe = json.loads(recipe_path.read_text())
    recipe["characters"].append(character)
    write_json(recipe_path, recipe)
    reject_before_client(builder, recipe_path, tmp_path, field)


@pytest.mark.parametrize(
    ("case", "match"),
    [
        ("ambiguous", "重复.*byte_start.*byte_end"),
        ("ambiguous_after_assignment", "重复.*byte_start.*byte_end"),
        ("missing_text", "未找到"),
        ("wrong_text", "与原文不一致"),
        ("missing_start", "同时"),
        ("missing_end", "同时"),
        ("start_inside_character", "字符边界"),
        ("end_inside_character", "字符边界"),
        ("character_offset", "字符边界|与原文不一致|完整对白"),
        ("out_of_bounds", "范围"),
        ("negative", "范围"),
        ("reversed", "范围"),
        ("empty", "范围"),
        ("outer_quotes", "完整对白"),
        ("narration", "完整对白"),
        ("partial", "完整对白"),
        ("nested", "完整对白"),
        ("cross_dialogues", "完整对白"),
        ("missing_speaker", "character.*不存在"),
        ("inferred_speaker", "character.*不存在"),
        ("duplicate", "重叠|重复任务"),
        ("conflicting_duplicate", "重叠|重复任务"),
        ("mixed_duplicate", "重叠|重复任务"),
        ("partial_overlap", "重叠|完整对白"),
        ("unknown_anchor_field", "未知字段"),
        ("unknown_speaker_field", "未知字段"),
        ("duplicate_character", "人物.*重复"),
        ("normalized_duplicate_character", "人物.*重复"),
    ],
)
def test_invalid_task_is_rejected_before_project_creation(
    builder, recipe_path, tmp_path, case, match
):
    recipe = json.loads(recipe_path.read_text())
    task = anchored(STORY, "好。", "甲")
    raw = STORY.encode("utf-8")
    if case in {"ambiguous", "ambiguous_after_assignment"}:
        task = {"text": "好。", "character": "甲"}
    elif case == "missing_text":
        task = {"text": "并不存在。", "character": "甲"}
    elif case == "wrong_text":
        task["text"] = "错。"
    elif case in {"missing_start", "missing_end"}:
        del task["byte_" + case.removeprefix("missing_")]
    elif case == "start_inside_character":
        task["byte_start"] += 1
    elif case == "end_inside_character":
        task["byte_end"] -= 1
    elif case == "character_offset":
        task["byte_start"] = STORY.index("好。")
        task["byte_end"] = task["byte_start"] + len("好。")
    elif case == "out_of_bounds":
        task["byte_end"] = len(raw) + 1
    elif case == "negative":
        task["byte_start"] = -1
    elif case == "reversed":
        task["byte_start"], task["byte_end"] = task["byte_end"], task["byte_start"]
    elif case == "empty":
        task["byte_end"] = task["byte_start"]
    elif case == "outer_quotes":
        task = anchored(STORY, "「好。」", "甲")
    elif case == "narration":
        task = anchored(STORY, "风穿过站台。", "甲")
    elif case in {"partial", "partial_overlap"}:
        task = anchored(STORY, "好", "甲")
    elif case == "nested":
        task = anchored(STORY, "等一等", "乙")
    elif case == "cross_dialogues":
        task["byte_end"] = anchored(STORY, "好。", "乙", 1)["byte_end"]
        task["text"] = raw[task["byte_start"] : task["byte_end"]].decode("utf-8")
    elif case == "missing_speaker":
        task["character"] = "不存在的人"
    elif case == "inferred_speaker":
        recipe["characters"] = [recipe["characters"][1]]
    elif case == "conflicting_duplicate":
        task["character"] = "乙"
    elif case == "mixed_duplicate":
        task = {"text": "走吧🙂。", "character": "甲"}
    elif case == "unknown_anchor_field":
        task = {"text": "走吧🙂。", "character": "甲", "byte_strat": 0}
    elif case == "unknown_speaker_field":
        task["speaker"] = "不存在的人"
    elif case in {"duplicate_character", "normalized_duplicate_character"}:
        recipe["characters"].append(
            {"name": " 甲 " if case.startswith("normalized") else "甲", "description": "重复"}
        )

    # A good first task must not be applied before a bad later task is inspected.
    recipe["dialogues"] = [anchored(STORY, "他说『等一等』，我答应了。", "乙")]
    if case in {
        "duplicate",
        "conflicting_duplicate",
        "partial_overlap",
        "ambiguous_after_assignment",
    }:
        recipe["dialogues"].append(anchored(STORY, "好。", "甲"))
    elif case == "mixed_duplicate":
        recipe["dialogues"].append(anchored(STORY, "走吧🙂。", "甲"))
    recipe["dialogues"].append(task)
    write_json(recipe_path, recipe)
    reject_before_client(builder, recipe_path, tmp_path, match)


@pytest.mark.parametrize("field", ["byte_start", "byte_end"])
@pytest.mark.parametrize("value", [None, True, False, 1.0, "18", [], {}])
def test_anchor_requires_json_integers(builder, recipe_path, tmp_path, field, value):
    recipe = json.loads(recipe_path.read_text())
    recipe["dialogues"][0][field] = value
    write_json(recipe_path, recipe)
    reject_before_client(builder, recipe_path, tmp_path, "整数")


@pytest.mark.parametrize("field", ["text", "character"])
@pytest.mark.parametrize("value", [None, 123, 1.5, True, False, [], {}, "", "   "])
def test_dialogue_requires_nonempty_strings(builder, recipe_path, tmp_path, field, value):
    recipe = json.loads(recipe_path.read_text())
    recipe["dialogues"][0][field] = value
    write_json(recipe_path, recipe)
    reject_before_client(builder, recipe_path, tmp_path, field)


@pytest.mark.parametrize("with_audio", [False, True])
@pytest.mark.parametrize(
    "value", [42, 0, 1.5, True, False, None, [], {}, "", "  ", " Tingting", "Ting\nting"]
)
def test_voice_prefix_type_is_checked_even_without_audio(
    builder, recipe_path, tmp_path, with_audio, value
):
    recipe = json.loads(recipe_path.read_text())
    recipe["dialogues"][-1]["voice_prefix"] = value
    write_json(recipe_path, recipe)
    reject_before_client(builder, recipe_path, tmp_path, "voice_prefix", with_audio)


@pytest.fixture
def local_app(tmp_path, monkeypatch):
    from storygal import llm, settings

    monkeypatch.setenv("STORYGAL_DATA_DIR", str(tmp_path / "default-app"))
    monkeypatch.setattr(settings, "load_env", lambda _path: None)
    monkeypatch.setattr(llm, "api_key", lambda: "")
    from storygal import app as app_module
    from storygal import exporter, openai_speech, reader_export, speech

    monkeypatch.setattr(app_module, "load_env", lambda _path: None)
    monkeypatch.setattr(exporter, "api_key", lambda: "")
    monkeypatch.setattr(reader_export, "api_key", lambda: "")

    def forbidden(*_args, **_kwargs):
        pytest.fail("Recipe dialogue tests must never call network or TTS")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(speech, "voices", list)
    monkeypatch.setattr(speech, "render", forbidden)
    monkeypatch.setattr(openai_speech, "render", forbidden)
    return app_module.create_app(tmp_path / "work")


def test_character_payload_accepts_empty_description_and_api_length_limits(
    builder, recipe_path, tmp_path, local_app
):
    from fastapi.testclient import TestClient

    recipe = json.loads(recipe_path.read_text())
    added = [
        {"name": "丙", "description": ""},
        {"name": "丁" * 40, "description": "字" * 2000},
    ]
    recipe["characters"].extend(added)
    write_json(recipe_path, recipe)
    report = builder.build(
        recipe_path,
        "http://testserver",
        tmp_path / "output.zip",
        client_factory=lambda **_kwargs: TestClient(local_app),
    )
    state = TestClient(local_app).get(f"/api/projects/{report['project_id']}/review").json()
    descriptions = {c["display_name"]: c["description"] for c in state["characters"]}
    assert all(descriptions[c["name"]] == c["description"] for c in added)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-bom-crlf", "gb18030"])
@pytest.mark.parametrize("change_after_preflight", [False, True])
def test_repeated_dialogues_and_legacy_text_build_with_stable_ranges(
    builder, recipe_path, tmp_path, local_app, encoding, change_after_preflight
):
    from fastapi.testclient import TestClient

    recipe = json.loads(recipe_path.read_text())
    source = "\ufeff" + STORY.replace("\n", "\r\n") if encoding == "utf-8-bom-crlf" else STORY
    original = source.encode("gb18030" if encoding == "gb18030" else "utf-8")
    (recipe_path.parent / "source.txt").write_bytes(original)
    recipe["dialogues"] = [
        anchored(source, "好。", "乙", 1),
        {"text": "走吧🙂。", "character": "甲", "voice_prefix": "Tingting"},
        anchored(source, "好。", "甲"),
        anchored(source, "他说『等一等』，我答应了。", "乙"),
    ]
    write_json(recipe_path, recipe)
    expected = copy.deepcopy(recipe["dialogues"])

    def factory(**_kwargs):
        if change_after_preflight:
            # Prevent a future reread from quietly changing either anchors or upload bytes.
            (recipe_path.parent / "source.txt").write_bytes(b"replaced after preflight")
            (recipe_path.parent / "scene.png").write_bytes(b"replaced after preflight")
            recipe_path.write_bytes(b"replaced after preflight")
        return TestClient(local_app)

    destination = tmp_path / "result.zip"
    report = builder.build(recipe_path, "http://testserver", destination, client_factory=factory)
    assert report["export"]["state"] == "completed"
    client = TestClient(local_app)
    prefix = "/api/projects/" + report["project_id"]
    state = client.get(prefix + "/review").json()
    names = {c["id"]: c["display_name"] for c in state["characters"]}
    assert len(state["dialogues"]) == len(expected)
    for task in expected:
        anchor = task if "byte_start" in task else anchored(source, task["text"], task["character"])
        found = next(d for d in state["dialogues"] if d["byte_start"] == anchor["byte_start"])
        assert found["byte_end"] == anchor["byte_end"]
        assert found["text"] == task["text"]
        assert names[found["speaker_id"]] == task["character"]
        assert found["status"] == "reviewed"
    assert client.get(prefix + "/source").content == original
    with zipfile.ZipFile(destination) as archive:
        assert archive.read("original.txt") == original
        assert archive.read("source.utf8.txt") == source.encode("utf-8")
        project = json.loads(archive.read("project.json"))
        assert project["records"]["speech_takes"] == []
    assert not any(job.get("kind") == "speech" for job in client.get(prefix + "/jobs").json())


def local_caps(voices=None, available=True):
    return {
        "provider": "macos-say",
        "model": "synthetic-test",
        "version": 1,
        "format": "pcm_s16le/24000Hz/mono",
        "available": available,
        "voices": voices if voices is not None else ["Tingting (zh_CN)", "Eddy (zh_CN)"],
    }


def database_snapshot(app):
    with app.state.store.db() as db:
        return list(db.iterdump())


def test_server_capabilities_route_is_project_free_and_uses_speech_state_source(
    local_app, monkeypatch
):
    from fastapi.testclient import TestClient

    from storygal import openai_speech, speech

    caps = local_caps()
    monkeypatch.setattr(speech, "capabilities", lambda: caps)
    before = database_snapshot(local_app)

    def forbidden_cloud_caps():
        pytest.fail("Local capabilities endpoint must not probe cloud providers")

    client = TestClient(local_app)
    with monkeypatch.context() as guard:
        guard.setattr(openai_speech, "capabilities", forbidden_cloud_caps)
        response = client.get("/api/speech/capabilities")
    assert response.status_code == 200
    assert response.json() == caps
    assert database_snapshot(local_app) == before
    assert local_app.state.store.list_projects() == []
    pid = client.post(
        "/api/projects",
        files={"file": ("source.txt", STORY.encode())},
        data={"rights_status": "owned"},
    ).json()["id"]
    assert client.get(f"/api/projects/{pid}/speech").json()["capabilities"] == caps


@pytest.mark.parametrize(
    ("case", "match"),
    [
        ("unavailable", "合成不可用"),
        ("no_match", "没有匹配"),
        ("ambiguous", "匹配多个"),
        ("exact_name_and_variant", "匹配多个"),
        ("later_no_match", "没有匹配"),
        ("conflicting_character", "不同音色"),
        ("not_an_object", "格式无效"),
        ("missing_available", "格式无效"),
        ("non_boolean_available", "格式无效"),
        ("non_list_voices", "格式无效"),
        ("non_string_voice", "格式无效"),
        ("blank_voice", "格式无效"),
        ("wrong_provider", "格式无效"),
    ],
)
def test_audio_preflight_errors_leave_database_unchanged(
    builder, recipe_path, tmp_path, local_app, monkeypatch, case, match
):
    from fastapi.testclient import TestClient

    from storygal import speech

    caps = local_caps()
    recipe = json.loads(recipe_path.read_text())
    if case == "unavailable":
        caps["available"] = False
    elif case == "no_match":
        caps["voices"] = []
    elif case == "ambiguous":
        caps["voices"] = ["Tingting (zh_CN)", "Tingting (zh_TW)"]
    elif case == "exact_name_and_variant":
        caps["voices"] = ["Tingting", "Tingting Enhanced"]
    elif case == "later_no_match":
        recipe["dialogues"][-1]["voice_prefix"] = "Missing"
    elif case == "conflicting_character":
        recipe["dialogues"][2]["voice_prefix"] = "Eddy"
    elif case == "not_an_object":
        caps = []
    elif case == "missing_available":
        del caps["available"]
    elif case == "non_boolean_available":
        caps["available"] = 1
    elif case == "non_list_voices":
        caps["voices"] = "Tingting"
    elif case == "non_string_voice":
        caps["voices"] = ["Tingting", 42]
    elif case == "blank_voice":
        caps["voices"] = ["Tingting", "   "]
    elif case == "wrong_provider":
        caps["provider"] = "openai-realtime"
    write_json(recipe_path, recipe)
    monkeypatch.setattr(speech, "capabilities", lambda: caps)
    requests = []
    client = TestClient(local_app)
    client.event_hooks["request"].append(lambda r: requests.append((r.method, r.url.path)))
    before = database_snapshot(local_app)
    destination = tmp_path / "no-output" / "project.zip"
    with pytest.raises(ValueError, match=match) as caught:
        builder.build(
            recipe_path,
            "http://testserver",
            destination,
            with_audio=True,
            client_factory=lambda **_kwargs: client,
        )
    assert "未创建项目，未合成语音" in str(caught.value)
    assert requests == [("GET", "/api/speech/capabilities")]
    assert database_snapshot(local_app) == before
    assert local_app.state.store.list_projects() == []
    assert not destination.parent.exists()


@pytest.mark.parametrize("case", ["404", "500", "invalid_json", "timeout"])
def test_unreadable_capabilities_fail_before_writes_without_echoing_server_details(
    builder, recipe_path, tmp_path, case
):
    requests = []
    private_detail = "private-response-marker"

    def handler(request):
        requests.append((request.method, request.url.path))
        if case == "timeout":
            raise httpx.ReadTimeout(private_detail, request=request)
        return httpx.Response(200 if case == "invalid_json" else int(case), text=private_detail)

    def factory(**kwargs):
        return httpx.Client(**kwargs, transport=httpx.MockTransport(handler))

    with pytest.raises(ValueError, match="未创建项目，未合成语音") as caught:
        builder.build(
            recipe_path,
            "http://unused.invalid",
            tmp_path / "output.zip",
            with_audio=True,
            client_factory=factory,
        )
    assert private_detail not in str(caught.value)
    assert requests == [("GET", "/api/speech/capabilities")]
    assert not (tmp_path / "output.zip").exists()


@pytest.mark.parametrize("with_audio", [False, True])
@pytest.mark.parametrize("has_prefix", [False, True])
def test_audio_build_uses_preflight_server_voice_and_default_adds_no_request(
    builder, recipe_path, tmp_path, local_app, monkeypatch, with_audio, has_prefix
):
    from fastapi.testclient import TestClient

    from storygal import speech

    selected = "Tingting (zh_CN)"
    # Identical IDs do not represent different voices. No speech is needed without prefixes.
    caps = local_caps([selected, selected], available=with_audio and has_prefix)
    if not has_prefix:
        recipe = json.loads(recipe_path.read_text())
        for task in recipe["dialogues"]:
            task.pop("voice_prefix", None)
        write_json(recipe_path, recipe)

    def server_voices():
        # A new matching voice after preflight must not change the resolved choice.
        return (
            [selected, "Tingting (zh_TW)"] if local_app.state.store.list_projects() else [selected]
        )

    monkeypatch.setattr(speech, "capabilities", lambda: caps)
    monkeypatch.setattr(speech, "voices", server_voices)
    rendered = []

    def synthetic_render(text, voice, speed, path):
        rendered.append((text, voice, speed))
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(24000)
            out.writeframes(b"\x10\x10" * 2400)

    monkeypatch.setattr(speech, "render", synthetic_render)
    requests = []
    client = TestClient(local_app)

    def observe(request):
        requests.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path == "/api/projects":
            caps["voices"] = [selected, "Tingting (zh_TW)"]

    client.event_hooks["request"].append(observe)
    destination = tmp_path / "result.zip"
    report = builder.build(
        recipe_path,
        "http://testserver",
        destination,
        with_audio=with_audio,
        client_factory=lambda **_kwargs: client,
    )
    assert report["export"]["state"] == "completed"
    if with_audio:
        assert requests[:2] == [("GET", "/api/speech/capabilities"), ("POST", "/api/projects")]
        assert requests.count(("GET", "/api/speech/capabilities")) == 1
    else:
        assert requests[0] == ("POST", "/api/projects")
        assert ("GET", "/api/speech/capabilities") not in requests
        assert not any(path.endswith("/speech/generate") for _, path in requests)
    assert rendered == ([("走吧🙂。", selected, 170)] if with_audio and has_prefix else [])
    if not has_prefix:
        assert not any(path.endswith("/speech/generate") for _, path in requests)
    with zipfile.ZipFile(destination) as archive:
        project = json.loads(archive.read("project.json"))
        assert len(project["records"]["speech_takes"]) == int(with_audio and has_prefix)
        assert archive.read("original.txt") == STORY.encode()
