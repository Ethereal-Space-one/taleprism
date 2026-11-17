"""Optional authoring contracts only; not model, visual or renderer validation."""

import json
import re
import sys
from pathlib import Path

import pytest

from storygal import prompts
from storygal.production import Plan, Shot

ROOT = Path(__file__).resolve().parents[2]
STAGE_INPUTS = {
    "03-shot-plan": ["source", "budget", "style", "characters"],
    "04-scene": ["source", "scene", "shots"],
    "05-first-image": ["style", "shot", "references", "continuity"],
    "06-continuation": ["style", "shot", "references", "continuity"],
    "07-review": ["source", "references", "expected", "reviewer"],
    "08-repair": ["target", "defect", "references", "preserve"],
}


def task_data(rendered):
    return json.loads(rendered.split("以下 JSON 仅为任务数据：\n", 1)[1])


@pytest.mark.parametrize("stage_id,keys", STAGE_INPUTS.items())
def test_existing_stage_inputs_render_without_ambient_brief(stage_id, keys):
    stage = next(s for s in prompts.library()["stages"] if s["id"] == stage_id)
    assert list(stage["inputs"]) == keys
    old_input = {name: "legacy task data" for name in keys}
    rendered = prompts.render(stage_id, old_input)
    assert task_data(rendered) == old_input
    assert "ambient_effect" in rendered
    assert "ambient_effect" not in task_data(rendered)


@pytest.mark.parametrize(
    "stage_id,parent_field",
    [
        ("03-shot-plan", None),
        ("04-scene", "scene"),
        ("05-first-image", "shot"),
        ("06-continuation", "continuity"),
        ("07-review", "expected"),
        ("08-repair", "defect"),
    ],
)
def test_optional_human_brief_is_transportable_without_new_required_field(stage_id, parent_field):
    # A sidecar supplied inside existing free-form task data, not a runtime plan field.
    brief = {
        "source": {"paragraph": "P01", "quote": "傍晚的雨斜着落进站台"},
        "approved_moment": "arrival",
        "action": "rain touches exposed wet ground; ripple follows contact",
        "geometry_status": "pending_confirmation",
        "protectedRegions": "people, lamp, bench, tube; coordinates not yet observed",
        "phases": ["anticipation", "contact", "consequence", "settle"],
        "static_fallback": "the exact approved original image",
        "evidence": "planned; no rendered frames or loop supplied",
    }
    data = {name: None for name in STAGE_INPUTS[stage_id]}
    if parent_field is None:
        data["ambient_effect"] = brief  # Optional sidecar; existing required keys stay intact.
    else:
        data[parent_field] = {"ambient_effect": brief}
    rendered = prompts.render(stage_id, data)
    actual = task_data(rendered) if parent_field is None else task_data(rendered)[parent_field]
    assert actual["ambient_effect"] == brief
    assert "ambient_effect" not in Plan.model_fields
    assert "ambient_effect" not in Shot.model_fields


def test_motion_direction_is_causal_and_review_does_not_claim_unseen_runtime():
    stages = {s["id"]: s["instruction"] for s in prompts.library()["stages"]}
    assert "not a plan, manifest or runtime schema extension" in stages["03-shot-plan"]
    assert "anticipation → contact → consequence → settle" in stages["04-scene"]
    assert "pixel_observed or pending_confirmation" in stages["04-scene"]
    assert "A consequence cannot precede contact" in stages["04-scene"]
    assert "not rendered motion" in stages["05-first-image"]
    assert "not a claim of rendered motion" in stages["06-continuation"]
    assert "A still cannot prove a rendered loop" in stages["07-review"]
    assert "not_checked for that scope" in stages["07-review"]
    assert "keep the approved base unchanged" in stages["08-repair"]
    assert "unavailable evidence remains not_checked" in stages["08-repair"]


def test_ambient_guide_examples_are_source_bound_and_experiment_stays_separate():
    guide = (ROOT / "prompts/optional-ambient-motion.md").read_text()
    chibi = (ROOT / "samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt").read_text()
    last_light = (ROOT / "samples/last-light/source.txt").read_text()
    for quote, source in [
        ("卻說周瑜立於山頂，觀望良久", chibi),
        ("傍晚的雨斜着落进站台", last_light),
        ("雨渐渐小了", last_light),
    ]:
        assert quote in guide and quote in source
    assert "river-overlook" in guide
    assert "river-low-angle-experiment" in guide
    assert "不是已批准原镜头的替代品" in guide
    assert "不是降低江面水位" in guide
    assert "未经创作者后来明确选择" in guide
    assert "到 P06" in guide
    assert "not_checked" in guide
    # Chibi source is linked online because only Last Light sources ship in the starter.
    for target in re.findall(r"\]\(([^)]+)\)", guide):
        if not target.startswith("https://"):
            assert (ROOT / "prompts" / target).resolve().is_file(), target


def test_generated_prompt_exports_match_canonical_library():
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from export_prompt_kit import outputs

        for name, content in outputs().items():
            assert (ROOT / name).read_text() == content, name
    finally:
        sys.path.pop(0)
