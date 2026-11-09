import importlib.util
import json

from fastapi.testclient import TestClient

from storygal import bundles, prompts
from storygal.app import create_app
from storygal.production import plan_task_schema
from storygal.reader import REPO


def test_generated_prompt_kit_matches_runtime_and_schema_refs_resolve():
    spec = importlib.util.spec_from_file_location(
        "prompt_export", REPO / "tools/export_prompt_kit.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, expected in module.outputs().items():
        assert (REPO / name).read_text() == expected, name
    assert len(prompts.library()["stages"]) == 8
    for stage in prompts.library()["stages"]:
        result = prompts.render(stage["id"], stage["example_inputs"])
        assert "{{" not in result and prompts.rules_text() in result
    schema = plan_task_schema()

    def visit(node):
        if isinstance(node, dict):
            if "$ref" in node:
                target = schema
                for key in node["$ref"].removeprefix("#/").split("/"):
                    target = target[key]
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)


def test_missing_and_corrupt_optional_pack_fail_without_creating_projects(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    folder = root / "samples/content-packs"
    folder.mkdir(parents=True)
    (folder / "catalog.json").write_text(
        json.dumps(
            [
                {
                    "id": "demo",
                    "file": "demo.zip",
                    "sha256": "0" * 64,
                    "download_url": "https://example.org/demo.zip",
                }
            ]
        )
    )
    monkeypatch.setattr(bundles, "REPO", root)
    client = TestClient(create_app(tmp_path / "work"))
    assert client.get("/api/content-packs").json()[0]["available"] is False
    assert client.post("/api/content-packs/demo").status_code == 400
    (folder / "demo.zip").write_bytes(b"wrong download")
    assert client.get("/api/content-packs").json()[0]["available"] is True
    assert client.post("/api/content-packs/demo").status_code == 400
    assert client.get("/api/projects").json() == []


def test_second_story_worksheet_uses_generic_flow_without_images_or_model_calls(tmp_path):
    client = TestClient(create_app(tmp_path / "work"))
    folder = REPO / "examples/archive-room"
    raw = (folder / "source.txt").read_bytes()
    p = client.post(
        "/api/projects", files={"file": ("archive.txt", raw)}, data={"rights_status": "owned"}
    )
    assert p.status_code == 201
    pid = p.json()["id"]
    review = client.app.state.review
    data = json.loads((folder / "worksheet.json").read_text())
    characters = {}
    for name in data.pop("characters"):
        existing = next(
            (c for c in review.state(pid)["characters"] if c["display_name"] == name), None
        )
        c = review.character(
            pid,
            review.state(pid)["revision"],
            name,
            [],
            "原创短篇人物",
            existing["id"] if existing else None,
        )
        characters[name] = c["id"]
    blocks = client.app.state.reader.blocks(pid)
    for shot in data["shots"]:
        shot["after_byte"] = blocks[shot.pop("paragraph")]["byte_end"]
        for actor in shot["actors"]:
            actor["character_id"] = characters[actor.pop("character")]
    state = client.get(f"/api/projects/{pid}/production").json()
    result = client.put(
        f"/api/projects/{pid}/production",
        json={"revision": state["revision"], "source_sha256": state["source_sha256"], "plan": data},
    )
    assert result.status_code == 200, result.text
    for shot in data["shots"]:
        state = client.get(f"/api/projects/{pid}/production").json()
        result = client.post(
            f"/api/projects/{pid}/production/{shot['id']}/approve",
            json={"revision": state["revision"]},
        )
        assert result.status_code == 200, result.text
    tasks = client.get(f"/api/projects/{pid}/production/tasks").json()
    assert tasks["prompt_library"] == prompts.metadata()
    assert tasks["tasks"][1]["blocked"] is True
    assert all(s["continuity_check"] is None for s in result.json()["plan"]["shots"])
    assert client.get(f"/api/projects/{pid}/source").content == raw
    assert client.get(f"/api/projects/{pid}/jobs").json() == []
