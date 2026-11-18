"""Only a current, complete observation of final curated readers may be sealed."""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from check_plate_studies import NAMES, digest, plans, validate_report


@pytest.fixture
def receipt(tmp_path):
    # A minimal *synthetic* receipt for structural negative tests, never passed to the browser.
    catalog = {"edition": "v3.2.1", "books": []}
    results, hashes = {}, {}
    for i, slug in enumerate(NAMES):
        reader = f"taleprism-v3.2.1-{slug}-reader.zip"
        filename = slug + "-worksheet.json"
        body = json.dumps(
            {"plates": [{"plate_id": "x", "decision": "motion" if i == 0 else "still"}]}
        ).encode()
        (tmp_path / filename).write_bytes(body)
        hashes[reader] = digest(slug.encode())
        catalog["books"].append(
            {"slug": slug, "reader": reader, "worksheet": filename, "sha256": hashes[reader]}
        )
        results[slug] = {
            "reader_sha256": hashes[reader],
            "worksheet_sha256": digest(body),
            "ok": True,
            "proof": "fresh-browser-probe",
            "browser_version": "synthetic",
            "errors": [],
            "counts": {"total": 1, "screened": 1, "unassessed": 0},
            "plates": [
                {
                    "plate_id": "x",
                    "decision": "motion" if i == 0 else "still",
                    "status": "active" if i == 0 else "still",
                    "errors": [],
                }
            ],
        }
    transfers = {}
    for slug in NAMES[:2]:
        b = next(b for b in catalog["books"] if b["slug"] == slug)
        project = b["reader"].replace("-reader.zip", "-project.zip")
        hashes[project] = digest(project.encode())
        path = tmp_path / b["worksheet"]
        if slug == "chibi":
            (tmp_path / "chibi-restored-worksheet.json").write_bytes(path.read_bytes())
        transfers[slug] = {
            "project_sha256": hashes[project],
            "reader_sha256": b["sha256"],
            "worksheet_sha256": digest(path.read_bytes()),
            "screened": 1,
            "unassessed_before": 1,
            "imported_with_explicit_consent": True,
        }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    return (
        {
            "schema": 1,
            "proof": "fresh-browser-probe",
            "source_commit": "commit",
            "catalog_sha256": digest(path.read_bytes()),
            "books": results,
            "editable_transfers": transfers,
        },
        hashes,
        path,
    )


def test_accepts_complete_structure(receipt):
    r, h, c = receipt
    validate_report(r, h, "commit", catalog_path=c, sheet_dir=c.parent)


@pytest.mark.parametrize(
    "fault",
    [
        "missing-book",
        "changed-plate-id",
        "missing-worksheet",
        "stale-reader",
        "stale-commit",
        "unassessed",
        "static-only",
        "configured-not-played",
    ],
)
def test_rejects_bad_gate_receipt(receipt, fault):
    r, h, c = receipt
    out = copy.deepcopy(r)
    sub = out["books"]["chibi"]
    if fault == "missing-book":
        del out["books"]["the-margin"]
    elif fault == "changed-plate-id":
        sub["plates"][0]["plate_id"] = "same-name-wrong-plate"
    elif fault == "missing-worksheet":
        (c.parent / "chibi-worksheet.json").unlink()
    elif fault == "stale-reader":
        h[next(iter(h))] = "0" * 64
    elif fault == "stale-commit":
        out["source_commit"] = "elsewhere"
    elif fault == "unassessed":
        sub["counts"]["unassessed"] = 1
    elif fault == "static-only":
        sub["proof"] = None
    else:
        sub["plates"][0]["status"] = "configured"
    with pytest.raises((ValueError, FileNotFoundError)):
        validate_report(out, h, "commit", catalog_path=c, sheet_dir=c.parent)


def test_catalog_cannot_omit_quiet_book_or_escape_worksheet_dir(receipt):
    c = json.loads(receipt[2].read_bytes())
    c["books"][0]["worksheet"] = "../notes.json"
    with pytest.raises(ValueError):
        plans(c)
    c["books"] = c["books"][1:]
    with pytest.raises(ValueError):
        plans(c)


@pytest.mark.parametrize(
    "defect", ["missing", "other-edition", "other-sidecar", "auto-consent", "preapproved"]
)
def test_seal_requires_both_exact_real_workbench_transfers(receipt, defect):
    r, h, c = receipt
    x = r["editable_transfers"]["chibi"]
    if defect == "missing":
        del r["editable_transfers"]["last-light"]
    elif defect == "other-edition":
        x["project_sha256"] = "0" * 64
    elif defect == "other-sidecar":
        x["worksheet_sha256"] = "a" * 64
    elif defect == "auto-consent":
        x["imported_with_explicit_consent"] = False
    else:
        x["unassessed_before"] = 0
    with pytest.raises(ValueError):
        validate_report(r, h, "commit", catalog_path=c, sheet_dir=c.parent)
