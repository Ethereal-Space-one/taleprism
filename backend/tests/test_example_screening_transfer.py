"""Cold adoption is scoped to specific curated pairs, never a generic ID alias facility."""

import json
import os
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_example_screening_transfer as transfer


@pytest.fixture
def chibi():
    """Small public source/plan fixture (no binary downloads). Approval set only in the test copy."""
    public = json.loads((transfer.SHEETS / "chibi-worksheet.json").read_bytes())
    current = deepcopy(public)
    current["work_id"] = "independent-temporary-ID"
    plan = json.loads((ROOT / "examples/chibi/rebuild-v0.2.0.json").read_bytes())["plan"]
    original, cold = [], []
    for shot, r in zip(plan["shots"], current["plates"], strict=True):
        shot["status"] = "approved"
        p = {
            "id": shot["id"],
            "after_byte": shot["after_byte"],
            "image_asset_id": shot["image_asset_id"],
            "title": shot["title"],
            "description": shot["moment"],
        }
        original.append(p)
        r["plate_id"] = "plan-" + r["plate_id"]
        cold.append(p | {"id": r["plate_id"]})
    editor = {
        "states": {
            "reader_states": {"data": {"illustrations": deepcopy(cold)}},
            "production_states": {"data": plan},
        }
    }
    spec = json.loads((ROOT / "tools/edition-contract.json").read_bytes())["books"]["chibi"]
    source = (ROOT / "samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt").read_bytes()
    manual = json.loads((ROOT / "examples/chibi/visual-review-v0.2.0.json").read_bytes())
    return [public, current, original, cold, editor, spec, source, manual]


def test_alternate_sidecar_is_only_the_exact_approved_ids(chibi):
    original = deepcopy(chibi[0])
    derived = transfer.transfer_sheet("chibi", *chibi)
    assert chibi[0] == original
    assert (
        transfer.encoding(derived)
        == (transfer.SHEETS / "chibi-restored-worksheet.json").read_bytes()
    )
    assert derived["work_id"] == original["work_id"] != chibi[1]["work_id"]
    for published, paired in zip(original["plates"], derived["plates"], strict=True):
        assert paired == published | {"plate_id": "plan-" + published["plate_id"]}
    # In particular: technical activation must not lose an adverse visual review.
    assert "松枝" in derived["plates"][0]["verification"]
    with pytest.raises(ValueError, match="reviewed work"):
        transfer.transfer_sheet("arbitrary-project", *chibi)


@pytest.mark.parametrize(
    "change",
    [
        "lookalike-id",
        "duplicate",
        "different-image",
        "anchor",
        "source",
        "wrong-caption",
        "wrong-plan",
        "unapproved",
        "bad-evidence",
        "different-inspection",
    ],
)
def test_matching_fails_closed_without_altering_source_sheet(chibi, change):
    public, current, originals, cold, editor, _, _, manual = chibi
    original = deepcopy(public)
    if change == "lookalike-id":
        cold[0]["id"] = current["plates"][0]["plate_id"] = "plan-plan-river-overlook"
    elif change == "duplicate":
        current["plates"][1] = deepcopy(current["plates"][0])
    elif change == "different-image":
        current["plates"][0]["image_sha256"] = "0" * 64
    elif change == "anchor":
        current["plates"][0]["after_byte"] += 1
    elif change == "source":
        chibi[6] += b"!"
    elif change == "wrong-caption":
        originals[0]["description"] += " changed"
    elif change == "wrong-plan":
        editor["states"]["production_states"]["data"]["shots"][0]["id"] = "other-id"
    elif change == "unapproved":
        editor["states"]["production_states"]["data"]["shots"][0]["status"] = "draft"
    elif change == "bad-evidence":
        editor["states"]["production_states"]["data"]["shots"][0]["evidence"] = "made up"
    elif change == "different-inspection":
        next(v for v in manual["images"] if v["sample_key"] == "narrative:river-overlook")[
            "asset_id"
        ] = "other"
    with pytest.raises(ValueError):
        transfer.transfer_sheet("chibi", *chibi)
    assert public == original


@pytest.mark.skipif(
    not os.environ.get("TALEPRISM_PUBLIC_SCREENING_PAIRS"),
    reason="Set TALEPRISM_PUBLIC_SCREENING_PAIRS to the public release final ZIP directory",
)
def test_complete_actual_cold_imports_when_pairs_installed():
    edition = json.loads((transfer.SHEETS / "catalog.json").read_bytes())["edition"]
    receipts = transfer.check_transfers(
        Path(os.environ["TALEPRISM_PUBLIC_SCREENING_PAIRS"]), edition
    )
    assert set(receipts) == {"chibi", "last-light"}
    for slug, total in (("chibi", 12), ("last-light", 3)):
        r = receipts[slug]
        assert r["screened"] == r["unassessed_before"] == total
        assert (
            r["refused_without_consent"]
            and r["refused_wrong_binding"]
            and r["imported_with_explicit_consent"]
        )
