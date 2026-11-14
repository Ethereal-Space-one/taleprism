"""Maker provenance must distinguish historical requests from reconstructed intent."""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from chibi_provenance import (
    GATE,
    GROUP,
    PROMPTS,
    RECIPE,
    REVIEW,
    TRACE,
    WORKSHEET,
    make_trace,
    provenance_assets,
)
from chibi_source import digest, encoded, preflight


def read(name, root=ROOT):
    return json.loads((root / name).read_bytes())


def resolve(document, pointer):
    for part in pointer.strip("/").split("/"):
        document = document[int(part)] if isinstance(document, list) else document[part]
    return document


def test_all_twelve_trace_actual_effective_prompts_and_v2_lineage():
    trace, prompts, recipe, review = [read(p) for p in (TRACE, PROMPTS, RECIPE, REVIEW)]
    assert len(trace["records"]) == 12
    assert {r["key"] for r in trace["records"]} == {s["id"] for s in recipe["plan"]["shots"]}
    reviews = {r["sample_key"]: r for r in review["images"]}
    for index, record in enumerate(trace["records"]):
        original = record["original_generation"]
        result = record["current_result"]
        assert result["sha256"] == reviews[result["sample_key"]]["sha256"]
        assert result["asset_id"] == reviews[result["sample_key"]]["asset_id"]
        assert result["model_version"] is None and result["seed"] is None
        assert record["review"]["creator_final_art_review"] == "pending"
        assert original["references"][0]["role"] == "style_only"
        assert "几何母版" in original["references"][0]["scope"]
        for request in [original["prompt"], result["effective_actual_prompt"]]:
            actual = resolve(prompts, request["pointer"])
            assert request["path"] == PROMPTS
            assert request["value_sha256"] == digest(actual.encode())
        edits = record["edits"]
        if record["current_file"].endswith("-v2.png"):
            assert len(edits) == 1
            assert result["effective_actual_prompt"]["pointer"] == f"/images/{index}/edits/0/prompt"
            assert original["file"].endswith("-v1.png")
            assert original["result_sha256"] is None
            assert original["hash_status"] == "not_in_public_input"
            assert edits[0]["edit_target"]["sha256"] is None
            assert edits[0]["result_sha256"] == result["sha256"]
            assert original["generation_artifact"] != result["generation_artifact"]
        else:
            assert edits == []
            assert result["effective_actual_prompt"] == original["prompt"]
    altar = next(r for r in trace["records"] if r["key"] == "altar-assembly")
    assert altar["edits"][0]["date"] is None
    assert altar["edits"][0]["output_file_basis"] == "parent_current_file_and_generation_map"
    assert len(altar["edits"][0]["references"]) == 1
    assert trace["layers"]["retrospective_recipe"]["path"] == RECIPE
    assert "not the original" in trace["layers"]["retrospective_recipe"]["role"]
    assert trace["historical_requests_changed"] is False
    assert trace["image_bytes_changed"] is False


def test_trace_and_pair_gate_quotes_bind_exact_original_byte_spans():
    source = (ROOT / "samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt").read_bytes()
    trace, gate = read(TRACE), read(GATE)
    assert trace["source_sha256"] == gate["source_sha256"] == digest(source)
    evidence = list(gate["source_evidence"])
    for record in trace["records"]:
        evidence.extend(record["source_moment"][k] for k in [
            "recorded_marker", "retrospective_source_evidence",
        ])
    for item in evidence:
        assert source[item["byte_start"]:item["byte_end"]].decode() == item["quote"]
    assert any("青龍牙旗" in e["quote"] for e in evidence)
    assert any("前船一齊發火" in e["quote"] for e in evidence)


def test_paired_gate_is_honest_and_template_is_reusable_not_a_pass():
    gate, trace, sheet = read(GATE), read(TRACE), read(WORKSHEET)
    assert gate["decision"] == "needs_revision"
    assert gate["canonical_state_status"] == "proposed_for_future_correction_not_applied"
    assert gate["image_bytes_changed"] is False
    assert gate["creator_final_art_review"] == "pending"
    assert gate["shot_order"] == GROUP
    assert [s["flag_hue"] for s in gate["shots"]] == ["red", "blue-green", "red_under_firelight"]
    assert gate["trace_sha256"] == digest((ROOT / TRACE).read_bytes())
    by_key = {r["key"]: r for r in trace["records"]}
    assert gate["image_sha256"] == {k: by_key[k]["current_result"]["sha256"] for k in GROUP}
    assert any(p["dimension"] == "flag" and p["decision"] == "needs_revision" for p in gate["pair_checks"])
    assert any(p["dimension"] == "action" and p["decision"] == "passed" for p in gate["pair_checks"])
    assert sheet["decision"] == "not_checked"
    assert sheet["new_edit_result_id"] is None
    assert sheet["shots"][0]["image_inspected"] is False


@pytest.fixture(scope="module")
def public():
    source = Path(os.environ.get("TALEPRISM_CHIBI_SOURCE", ROOT / ".release/chibi-demo/taleprism-v0.1.0-chibi-reader.zip"))
    if not source.is_file():
        pytest.skip("optional pinned public v0.1 Chibi input; no private PNG required")
    _, _, files, content, _, _ = preflight(source, ROOT / RECIPE, ROOT / REVIEW)
    return files, content


def test_pinned_legacy_input_verifies_and_supplement_has_no_private_payload(public):
    files, content = public
    assert make_trace(files, content) == read(TRACE)
    assets = provenance_assets(files, content)
    assert assets["storygal-source/" + PROMPTS] == files["storygal-source/narrative-v1/prompts.json"]
    assert "storygal-source/" + GATE in assets
    assert not any(n.endswith((".png", ".wav", ".mp3")) for n in assets)
    assert all(n.startswith("storygal-source/") for n in assets)
    assert all(b"/workspace/" not in b and b"/home/" not in b for b in assets.values())


@pytest.mark.parametrize("mutation", ["prompt", "output", "creator", "gate_pass", "gate_corrected", "gate_hash", "gate_quote", "gate_unseen"])
def test_changed_history_or_clean_gate_cannot_be_replayed(public, tmp_path, mutation):
    files, content = public
    # Only public source documents; never copy a runtime project or local histories.
    for tree in ("examples/chibi", "samples/reader/narrative-v1", "prompts"):
        shutil.copytree(ROOT / tree, tmp_path / tree)
    if mutation == "prompt":
        name, value = PROMPTS, read(PROMPTS, tmp_path)
        value["images"][0]["prompt"] += " rewritten history"
    elif mutation in {"output", "creator"}:
        name, value = TRACE, read(TRACE, tmp_path)
        if mutation == "output":
            value["records"][0]["current_result"]["sha256"] = "0" * 64
        else:
            value["creator_final_art_review"] = "passed"
    else:
        name, value = GATE, read(GATE, tmp_path)
        if mutation == "gate_pass":
            value["decision"] = "passed"
        elif mutation == "gate_corrected":
            value["canonical_state_status"] = "corrected"
        elif mutation == "gate_hash":
            value["image_sha256"][GROUP[0]] = "0" * 64
        elif mutation == "gate_quote":
            value["source_evidence"][0]["byte_start"] += 1
        else:
            value["shots"][0]["image_inspected"] = False
    (tmp_path / name).write_bytes(encoded(value))
    with pytest.raises(ValueError):
        provenance_assets(files, content, tmp_path)
