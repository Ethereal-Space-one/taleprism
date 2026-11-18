"""Bind the four curated works' per-plate reviews and fresh observation to FINAL reader bytes."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHEETS = ROOT / "examples/plate-screening"
NAMES = ("chibi", "last-light", "the-door-left-open", "the-margin")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def plans(catalog):
    """Do not let deleting a catalog row turn a missing review into a clean pass."""
    require(
        isinstance(catalog, dict) and set(catalog) == {"edition", "books"},
        "Bad catalog",
    )
    require(re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", catalog["edition"]), "Bad version")
    books = catalog["books"]
    require(
        isinstance(books, list) and [b["slug"] for b in books] == list(NAMES),
        "Expected four curated books",
    )
    for b in books:
        slug = b["slug"]
        require(
            set(b) == {"slug", "reader", "worksheet", "sha256"}
            and b["reader"] == f"taleprism-{catalog['edition']}-{slug}-reader.zip"
            and b["worksheet"] == slug + "-worksheet.json"
            and re.fullmatch(r"[0-9a-f]{64}", b["sha256"]),
            "Unexpected reader, worksheet or digest for " + slug,
        )
    return books


def validate_report(
    report, records, commit, *, catalog_path=SHEETS / "catalog.json", sheet_dir=SHEETS
):
    """Refuse to finalize with a stale/missing worksheet or a prior/static browser run."""
    catalog = json.loads(catalog_path.read_bytes())
    books = plans(catalog)
    require(
        report.get("schema") == 1
        and report.get("proof") == "fresh-browser-probe"
        and report.get("source_commit") == commit
        and report.get("catalog_sha256") == digest(catalog_path.read_bytes())
        and set(report["books"]) == set(NAMES),
        "Plate-screening receipt is stale or incomplete",
    )
    for b in books:
        slug = b["slug"]
        r = report["books"][slug]
        sheet = (sheet_dir / b["worksheet"]).read_bytes()
        rows = json.loads(sheet)["plates"]
        require(
            r["worksheet_sha256"] == digest(sheet)
            and r["reader_sha256"] == b["sha256"] == records.get(b["reader"]),
            "Plate screening does not bind final bytes: " + slug,
        )
        require(
            r["ok"] is True
            and r["proof"] == "fresh-browser-probe"
            and r["browser_version"]
            and r.get("errors") == []
            and r["counts"]["screened"] == r["counts"]["total"] == len(rows)
            and r["counts"]["unassessed"] == 0
            and len(r["plates"]) == len(rows),
            "Incomplete observed plate screening: " + slug,
        )
        expected_ids = [p["plate_id"] for p in rows]
        require(
            [p["plate_id"] for p in r["plates"]] == expected_ids
            and len(expected_ids) == len(set(expected_ids)),
            "Observed plate IDs differ: " + slug,
        )
        for actual, row in zip(r["plates"], rows, strict=True):
            choice = row["decision"]
            require(
                choice in ("still", "deferred", "motion")
                and actual["decision"] == choice
                and not actual["errors"],
                "Unreviewed plate: " + actual["plate_id"],
            )
            # A normal project may finish an unimplemented supported candidate;
            # our curated release demonstrations explicitly promise these active.
            expected = {
                "still": "still",
                "deferred": "deferred-static",
                "motion": "active",
            }[choice]
            require(
                actual["status"] == expected,
                f"{slug}: expected {expected} on {actual['plate_id']}",
            )

    transfers = report.get("editable_transfers") or {}
    require(
        set(transfers) == {"chibi", "last-light"},
        "Missing editable worksheet restore evidence",
    )
    for b in books[:2]:
        slug = b["slug"]
        reader = report["books"][slug]
        transfer = transfers[slug]
        imported = sheet_dir / (
            "chibi-restored-worksheet.json" if slug == "chibi" else b["worksheet"]
        )
        count = reader["counts"]["total"]
        project_name = b["reader"].removesuffix("-reader.zip") + "-project.zip"
        require(
            records.get(project_name)
            and transfer["project_sha256"] == records[project_name]
            and transfer["reader_sha256"] == reader["reader_sha256"]
            and transfer["worksheet_sha256"] == digest(imported.read_bytes())
            and transfer["screened"] == transfer["unassessed_before"] == count
            and transfer["imported_with_explicit_consent"] is True,
            "Curated worksheet did not cold-import into the final editable: " + slug,
        )


def run(output, report_path, chrome=None):
    require(
        not report_path.exists(),
        "Choose a NEW output receipt; existing evidence will not be replaced",
    )
    catalog_path = SHEETS / "catalog.json"
    raw = catalog_path.read_bytes()
    books = plans(json.loads(raw))
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    receipt = {
        "schema": 1,
        "proof": "fresh-browser-probe",
        "source_commit": commit,
        "catalog_sha256": digest(raw),
        "books": {},
    }
    actual_sha = {}
    for b in books:
        slug = b["slug"]
        reader, sheet = output / b["reader"], SHEETS / b["worksheet"]
        require(
            reader.is_file() and reader.stat().st_size <= 160_000_000,
            "Missing/oversized final reader: " + slug,
        )
        actual_sha[reader.name] = digest(reader.read_bytes())
        require(
            actual_sha[reader.name] == b["sha256"], "Wrong final reader bytes: " + slug
        )
        cmd = [
            sys.executable,
            str(ROOT / "tools/screen_plates.py"),
            "check",
            str(reader),
            str(sheet),
            "--json",
            "--probe",
        ]
        result = json.loads(
            subprocess.check_output(cmd + (["--chromium", chrome] if chrome else []))
        )
        result["worksheet_sha256"] = digest(sheet.read_bytes())
        receipt["books"][slug] = result
    from check_example_screening_transfer import check_transfers

    receipt["editable_transfers"] = check_transfers(output, json.loads(raw)["edition"])
    for b in books[:2]:
        project = output / b["reader"].replace("-reader.zip", "-project.zip")
        actual_sha[project.name] = digest(project.read_bytes())
    validate_report(receipt, actual_sha, commit)
    with report_path.open("x", encoding="utf-8") as f:
        f.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return {slug: r["counts"] for slug, r in receipt["books"].items()}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output",
        required=True,
        type=Path,
        help="The actual complete final reader ZIP directory",
    )
    p.add_argument("--report", required=True, type=Path)
    p.add_argument("--chromium")
    args = p.parse_args()
    print(json.dumps(run(args.output, args.report, args.chromium), indent=2))
