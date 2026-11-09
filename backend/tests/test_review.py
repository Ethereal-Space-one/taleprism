import io
import json
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from storygal import llm
from storygal.app import create_app

STORY = "孔明曰：「此都督病源也。」周瑜曰：「願先生賜教。」\n孔明笑曰：「亮有一方。」\n有人喊道：「誰？」"


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path))


def project(client):
    return client.post(
        "/api/projects",
        files={"file": ("review.txt", STORY.encode())},
        data={"rights_status": "public_domain"},
    ).json()["id"]


def state(client, pid):
    return client.get(f"/api/projects/{pid}/review").json()


def character(client, pid, name, aliases=None):
    r = client.post(
        f"/api/projects/{pid}/characters",
        json={
            "revision": state(client, pid)["revision"],
            "display_name": name,
            "aliases": aliases or [],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def png():
    image = Image.new("RGBA", (32, 64), (100, 120, 160, 255))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def test_quote_anchors_assignment_conflict_and_immutable_source(client):
    pid = project(client)
    initial = state(client, pid)
    assert len(initial["dialogues"]) == 4
    assert {"孔明", "周瑜"} <= {c["display_name"] for c in initial["characters"]}
    raw = STORY.encode()
    for d in initial["dialogues"]:
        assert raw[d["byte_start"] : d["byte_end"]].decode() == d["text"]
        assert d["speaker_id"] is None
    c = character(client, pid, "諸葛亮", ["孔明"])
    revision = state(client, pid)["revision"]
    ids = [initial["dialogues"][0]["id"], initial["dialogues"][2]["id"]]
    r = client.patch(
        f"/api/projects/{pid}/dialogues",
        json={"revision": revision, "dialogue_ids": ids, "speaker_id": c["id"]},
    )
    assert r.status_code == 200
    assert [d["byte_start"] for d in state(client, pid)["dialogues"]] == sorted(
        d["byte_start"] for d in initial["dialogues"]
    )
    assert (
        client.patch(
            f"/api/projects/{pid}/dialogues",
            json={"revision": revision, "dialogue_ids": ids, "speaker_id": None},
        ).status_code
        == 409
    )
    text = client.get(f"/api/projects/{pid}/text").json()
    assert "".join(u["text"] for u in text["units"]) == STORY.replace("\n", "")
    assert [u["speaker_name"] for u in text["units"]].count("諸葛亮") == 2
    assert client.get(f"/api/projects/{pid}/source").content == raw
    assert client.post(f"/api/projects/{pid}/verify").json()["span_coverage"] is True
    assert len(client.get(f"/api/projects/{pid}/audit").json()) == 3


def test_merge_preserves_target_id_and_migrates_speakers(client):
    pid = project(client)
    a = character(client, pid, "諸葛亮")
    b = character(client, pid, "孔明", ["臥龍"])
    dialogue = state(client, pid)["dialogues"][0]
    client.patch(
        f"/api/projects/{pid}/dialogues",
        json={
            "revision": state(client, pid)["revision"],
            "dialogue_ids": [dialogue["id"]],
            "speaker_id": b["id"],
        },
    )
    r = client.post(
        f"/api/projects/{pid}/characters/{b['id']}/merge",
        json={"revision": state(client, pid)["revision"], "target_id": a["id"]},
    )
    assert r.status_code == 200
    s = state(client, pid)
    target = next(c for c in s["characters"] if c["id"] == a["id"])
    assert {"孔明", "臥龍"} <= set(target["aliases"])
    assert next(d for d in s["dialogues"] if d["id"] == dialogue["id"])["speaker_id"] == a["id"]
    assert next(c for c in s["characters"] if c["id"] == b["id"])["merged_into"] == a["id"]


def test_cross_project_ids_and_unconfirmed_speakers_rejected(client):
    one, two = project(client), project(client)
    c = character(client, one, "孔明")
    s = state(client, two)
    r = client.patch(
        f"/api/projects/{two}/dialogues",
        json={
            "revision": s["revision"],
            "dialogue_ids": [s["dialogues"][0]["id"]],
            "speaker_id": c["id"],
        },
    )
    assert r.status_code == 404
    assert state(client, two)["revision"] == s["revision"]
    pending = next(c for c in s["characters"] if c["status"] == "candidate")
    assert (
        client.patch(
            f"/api/projects/{two}/dialogues",
            json={
                "revision": s["revision"],
                "dialogue_ids": [s["dialogues"][0]["id"]],
                "speaker_id": pending["id"],
            },
        ).status_code
        == 400
    )


def test_assets_require_acceptance_and_reuse_single_file_in_export(client):
    pid = project(client)
    c = character(client, pid, "孔明")
    r = client.post(
        f"/api/projects/{pid}/characters/{c['id']}/assets",
        files={"file": ("sprite.png", png(), "image/png")},
        data={
            "revision": state(client, pid)["revision"],
            "kind": "reference_and_figure",
            "license_text": "test fixture, self-created",
        },
    )
    assert r.status_code == 201
    asset = r.json()
    assert asset["status"] == "pending"
    assert client.get(f"/api/projects/{pid}/assets/{asset['id']}/file").status_code == 200
    ids = [d["id"] for d in state(client, pid)["dialogues"][:3:2]]
    client.patch(
        f"/api/projects/{pid}/dialogues",
        json={
            "revision": state(client, pid)["revision"],
            "dialogue_ids": ids,
            "speaker_id": c["id"],
        },
    )
    assert not any(
        u.get("figure_asset_id") for u in client.get(f"/api/projects/{pid}/text").json()["units"]
    )
    r = client.patch(
        f"/api/projects/{pid}/assets/{asset['id']}",
        json={"revision": state(client, pid)["revision"], "status": "accepted", "active": True},
    )
    assert r.status_code == 200
    client.post(f"/api/projects/{pid}/exports")
    job = client.get(f"/api/projects/{pid}/jobs").json()[0]
    assert job["state"] == "completed", job
    path = client.app.state.store.project_dir(pid) / "exports" / (job["id"] + ".zip")
    with zipfile.ZipFile(path) as z:
        assert len([n for n in z.namelist() if n.startswith("game/figure/")]) == 1
        manifest = json.loads(z.read("storygal-manifest.json"))
        assert sum(u.get("figure_asset_id") == asset["id"] for u in manifest["units"]) == 2
        assert manifest["checks"]["parser"]["passed"] is True
    # Rejecting the previously accepted figure immediately removes it from future presentations.
    client.patch(
        f"/api/projects/{pid}/assets/{asset['id']}",
        json={"revision": state(client, pid)["revision"], "status": "rejected"},
    )
    assert not any(
        u.get("figure_asset_id") for u in client.get(f"/api/projects/{pid}/text").json()["units"]
    )


def test_invalid_image_and_non_image_payload_rejected(client):
    pid = project(client)
    c = character(client, pid, "孔明")
    r = client.post(
        f"/api/projects/{pid}/characters/{c['id']}/assets",
        files={"file": ("x.png", b"<script>bad</script>")},
        data={"revision": state(client, pid)["revision"], "kind": "figure", "license_text": "own"},
    )
    assert r.status_code == 400


def proposal_for(payload):
    return {
        "characters": [],
        "speakers": [
            {
                "dialogue_id": d["id"],
                "speaker_name": None,
                "confidence": 0,
                "evidence_span_ids": [payload["spans"][0]["id"]],
            }
            for d in payload["dialogues"]
        ],
    }


def test_llm_cache_and_manual_decisions_survive_rerun(client, monkeypatch):
    pid = project(client)
    review = client.app.state.review
    payload = review.payloads(pid)[0]
    calls = []

    def fake_analyze(data):
        calls.append(data)
        return proposal_for(data), {"total_tokens": 10}

    monkeypatch.setattr(llm, "analyze", fake_analyze)
    first = review.analyze(pid)
    second = review.analyze(pid)
    assert len(calls) == 1 and first["requests"] == 1 and second["cache_hits"] == 1
    c = character(client, pid, "孔明")
    d = state(client, pid)["dialogues"][0]
    review.assign(pid, state(client, pid)["revision"], [d["id"]], c["id"])
    review.analyze(pid)
    updated = next(x for x in state(client, pid)["dialogues"] if x["id"] == d["id"])
    assert updated["speaker_id"] == c["id"] and updated["status"] == "reviewed"
    invalid = proposal_for(payload)
    invalid["characters"] = [
        {"name": "不存在的名字", "aliases": [], "evidence_span_ids": [payload["spans"][0]["id"]]}
    ]
    with pytest.raises(ValueError, match="原文依据"):
        review.validate_proposal(invalid, payload, pid)
    invalid = proposal_for(payload)
    invalid["speakers"][0]["dialogue_id"] = "invented"
    with pytest.raises(ValueError):
        review.validate_proposal(invalid, payload, pid)


def test_model_transport_and_errors_do_not_leak_key(monkeypatch):
    monkeypatch.setenv("STORYGAL_LLM_API_KEY", "test-secret-never-export")

    def handler(request):
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"characters":[],"speakers":[]}'},
                    }
                ],
                "usage": {"total_tokens": 4},
            },
        )

    result, usage = llm.analyze({}, transport=httpx.MockTransport(handler))
    assert result == {"characters": [], "speakers": []} and usage["total_tokens"] == 4

    def broken(_request):
        return httpx.Response(401, json={"error": "test-secret-never-export"})

    with pytest.raises(ValueError) as error:
        llm.analyze({}, transport=httpx.MockTransport(broken))
    assert "test-secret-never-export" not in str(error.value)


def test_revoking_last_reference_disables_active_figure(client):
    pid = project(client)
    c = character(client, pid, "孔明")
    review = client.app.state.review
    ref = review.upload_asset(
        pid, state(client, pid)["revision"], c["id"], png(), "reference", "own"
    )
    review.accept_asset(pid, state(client, pid)["revision"], ref["id"], "accepted", False)
    fig = review.upload_asset(pid, state(client, pid)["revision"], c["id"], png(), "figure", "own")
    review.accept_asset(pid, state(client, pid)["revision"], fig["id"], "accepted", True)
    review.assign(
        pid, state(client, pid)["revision"], [state(client, pid)["dialogues"][0]["id"]], c["id"]
    )
    assert any(u.get("figure_asset_id") for u in review.presentation(pid)[0])
    review.accept_asset(pid, state(client, pid)["revision"], ref["id"], "rejected", False)
    assert not any(u.get("figure_asset_id") for u in review.presentation(pid)[0])
    assert (
        next(x for x in state(client, pid)["characters"] if x["id"] == c["id"])["active_figure_id"]
        is None
    )


def test_export_blocks_known_service_secret_and_cleans_partial_output(client, monkeypatch):
    key = "test-known-private-service-key"
    monkeypatch.setenv("STORYGAL_LLM_API_KEY", key)
    pid = client.post(
        "/api/projects",
        files={"file": ("secret.txt", key.encode())},
        data={"rights_status": "local_test"},
    ).json()["id"]
    client.post(f"/api/projects/{pid}/exports")
    job = client.get(f"/api/projects/{pid}/jobs").json()[0]
    assert job["state"] == "failed" and "密钥" in job["error"]
    assert key not in job["error"]
    directory = client.app.state.store.project_dir(pid) / "exports"
    assert not list(directory.glob("*.zip"))
    assert not list(directory.glob("*.partial"))
