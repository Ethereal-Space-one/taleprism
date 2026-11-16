"""Check portable render/metadata contracts; no model or visual scoring."""

import json

import pytest

from storygal import prompts
from storygal.production import Plan, Shot

# Fixed adversarial briefs with explicit expected outcomes for future visual QA.
# Assertions below are on data transport, not whether a model follows the brief.
CASES = [
    (
        "deception",
        ["小船逼近。岸上的守卫以为来船送粮。", "巡船横出，来船仍未起火。"],
        1,
        "谁在逼近、谁在叫停？",
        "小船进、巡船拦；幕中身份认知有差异。",
        "船头朝向、停与进的动作",
        "不能提前点火",
        "needs_revision",
    ),
    (
        "quiet-dialogue",
        ["她指着图纸。", "听见问题，她收回手。", "两人第二天才签字。"],
        1,
        "谁转向倾听？",
        "她停下解释，尚未达成协议。",
        "手离开图纸，目光转向说话人",
        "不能签字或庆祝",
        "needs_revision",
    ),
    (
        "chapter-transition",
        ["上章：门口长凳完好。", "三年后，站台封闭，长凳已经拆除。"],
        1,
        "同一地点什么变了？",
        "是同一站台；凳子随时间离场。",
        "保留窗和檐柱；原位置可空",
        "不强迫跨时间保持长凳",
        "passed",
    ),
    (
        "unreliable-mystery",
        ["她说门一直锁着。门缝露出一根浅色丝线。", "直到次日才确认钥匙持有人。"],
        0,
        "此时能确认什么？",
        "可以看到线索，不能证实门是否一直锁着。",
        "仅门缝丝线，不把叙述转成客观闪回",
        "不能揭露钥匙持有人",
        "warning",
    ),
    (
        "atmosphere",
        ["他离开后，窗上的水缓慢流下，隔壁座位没人。"],
        0,
        "画面需要留下什么感受？",
        "停顿与空落即可，不需要解释离开的原因。",
        "空椅与水痕；可留白不配图",
        "不要发明争执或离开的原因",
        "not_applicable",
    ),
    (
        "mobile-placement",
        ["墙面深处有影子。", "灯亮后，他才认出那是谁。"],
        0,
        "此时能否察觉有人，但还认不出是谁？",
        "影子可见，身份仍未知。",
        "实际手机画幅下仍可见的背光轮廓",
        "封面、插图和说明都不可提前泄露身份",
        "not_checked",
    ),
]


@pytest.mark.parametrize(
    "name,paragraphs,placement,question,answer,cue,withhold,semantic_expected", CASES
)
def test_reader_intent_flows_from_numbered_source_to_manual_review(
    name, paragraphs, placement, question, answer, cue, withhold, semantic_expected
):
    source = [{"id": f"P{i + 1:02}", "text": text} for i, text in enumerate(paragraphs)]
    moment = source[placement]
    brief = {
        "question": question,
        "expected_reading": answer,
        "visible_cue": cue,
        "withhold": withhold,
    }
    plan = prompts.render(
        "03-shot-plan", {"source": source, "budget": 2, "style": "neutral", "characters": []}
    )
    review = prompts.render(
        "07-review",
        {
            "source": moment,
            "references": [],
            "expected": {"reader_intent": brief},
            "reviewer": "no attached image; template contract only",
        },
    )
    data = lambda text: json.loads(text.split("以下 JSON 仅为任务数据：\n", 1)[1])
    assert data(plan)["source"] == source, name
    assert data(review)["source"] == moment, name
    assert data(review)["expected"]["reader_intent"] == brief, name
    assert data(review)["references"] == [], name
    assert "visual checks are not_checked" in review, name
    assert semantic_expected in {
        "needs_revision",
        "passed",
        "warning",
        "not_applicable",
        "not_checked",
    }
    assert len(source) > placement


def test_prompt_version_is_independent_of_workspace_schema():
    assert prompts.metadata()["version"] == "0.2.1"
    assert "reader_intent" not in Shot.model_fields
    assert Plan(budget=0).shots == []
    assert [s["id"] for s in prompts.library()["stages"]] == [
        "01-source",
        "02-character",
        "03-shot-plan",
        "04-scene",
        "05-first-image",
        "06-continuation",
        "07-review",
        "08-repair",
    ]


@pytest.mark.parametrize("stage", ["05-first-image", "06-continuation"])
def test_production_style_exports_still_render_without_manual_intent(stage):
    text = prompts.render(
        stage, {"style": "neutral", "shot": {}, "references": [], "continuity": {}}
    )
    assert "When a reader_intent is supplied" in text
    assert "without inventing a missing brief" in text
    assert "only to its stated role" in text
