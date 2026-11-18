"""Verify adoption of the two curated review sheets through a real, fresh Workbench restore.

Never translates a user worksheet. The one alternate artifact is made ONLY for the reviewed
Chibi public Reader and its independently checked editable plan. It retains the original PUBLIC
work ID: importing a fresh restoration must still require an explicit exact-copy decision.
"""

import argparse
import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from chibi_source import LIMIT, read_zip
from screen_plates import (
    ROOT,
    Worksheet,
    assess,
    carriers_for_book,
    digest,
    inventory,
    limited,
    require,
    unique_json,
)
from storygal.plate_screening import BINDING

SHEETS = ROOT / "examples/plate-screening"
PUBLIC_091 = {
    "chibi": {
        "reader": "9a539fd9c444772a20417c0c5c4de2e591785db16ed1a7de036035c46f52d891",
        "project": "49514698704b2785edf51169080195c5d658bad60065abe9e7353e78a48186ca",
    },
    "last-light": {
        "reader": "4c885d469f3163d3d1e064b7e024875b51d5fb7764cefda2e049238e09e736dc",
        "project": "64fdc898fd955c27f1ab1f602f63b773f1300c98c148bebb87330428f914f882",
    },
}


def transfer_sheet(
    slug, public, current, public_plates, cold_plates, editor, spec, source, manual
):
    """Verify the 12+3 curated identities. No fuzzy matching, title inference or prefix stripping."""
    require(
        slug in PUBLIC_091
        and public["work_id"] == spec["public_work_id"]
        and public["source_sha256"]
        == current["source_sha256"]
        == spec["source_sha256"]
        == digest(source),
        f"{slug}: not the exact reviewed work/source",
    )
    require(
        public["work_id"] != current["work_id"],
        "test needs an independently restored work",
    )
    shots = editor["states"]["production_states"]["data"]["shots"]
    applied = editor["states"]["reader_states"]["data"]["illustrations"]
    targets = spec["illustrations"]
    require(
        len(targets) == (12 if slug == "chibi" else 3)
        and len(targets)
        == len(public["plates"])
        == len(current["plates"])
        == len(shots)
        == len(public_plates)
        == len(cold_plates)
        == len(applied),
        "missing/extra review, plate or shot",
    )
    out = deepcopy(public)
    for row, local, original, cold, recorded, shot, target in zip(
        out["plates"],
        current["plates"],
        public_plates,
        cold_plates,
        applied,
        shots,
        targets,
        strict=True,
    ):
        # edition-contract's finite ID list is independent of the incoming worksheet.
        rid = target["id"]
        cid = "plan-" + rid if slug == "chibi" else rid
        sid = rid if slug == "chibi" else shot["id"]
        require(
            rid == row["plate_id"] == original["id"]
            and cid
            == local["plate_id"]
            == cold["id"]
            == recorded["id"]
            == "plan-" + sid
            and shot["id"] == sid
            and shot["status"] == "approved",
            f"{rid}: not the exact independently accepted reader/plan placement",
        )
        require(
            all(row[k] == local[k] for k in BINDING if k != "plate_id")
            and row["image_sha256"] == target["image_sha256"]
            and original == (recorded | {"id": rid})
            and cold == recorded,
            f"{rid}: different illustration bytes, image identity, dimensions, anchor or caption",
        )
        require(
            row["after_byte"]
            == target["after_byte"]
            == shot["after_byte"]
            == recorded["after_byte"]
            and shot["image_asset_id"]
            == local["image_asset_id"]
            == recorded["image_asset_id"]
            and shot["title"] == recorded["title"]
            and shot["moment"] == recorded["description"],
            f"{rid}: not the same approved production shot",
        )
        quote = shot["evidence"].encode()
        require(
            quote and quote in source[: row["after_byte"]],
            f"{rid}: invalid independently bound plan evidence",
        )
        if slug == "chibi":
            matches = [
                im for im in manual["images"] if im["sample_key"] == "narrative:" + rid
            ]
            require(
                len(matches) == 1
                and matches[0]["asset_id"] == row["image_asset_id"]
                and matches[0]["sha256"] == row["image_sha256"]
                and matches[0]["inspection"]
                and manual["shots"].get(rid)
                and target["description"],
                f"{rid}: independent per-image visual review does not corroborate the ID",
            )
        row["plate_id"] = cid
    return out


def encoding(sheet):
    return (json.dumps(sheet, ensure_ascii=False, indent=2) + "\n").encode()


def checked(response):
    response.raise_for_status()
    return response


def check_one(output, edition, slug, spec, manual, store, write_restored):
    from fastapi.testclient import TestClient

    # The ASGI module initializes a default app at import time. Confine even that
    # incidental, unused store to this run instead of opening the usual workspace DB.
    with patch.dict(os.environ, {"STORYGAL_DATA_DIR": str(store / "module-default")}):
        from storygal.app import create_app

    stem = f"taleprism-{edition}-{slug}"
    reader_sha, files, book, source, blank = inventory(output / (stem + "-reader.zip"))
    raw = limited(output / (stem + "-project.zip"), LIMIT)
    project_sha = digest(raw)
    if edition in {"v0.9.1", "v0.9.2"}:
        require(
            {"reader": reader_sha, "project": project_sha} == PUBLIC_091[slug],
            f"{slug}: not the published v0.9.1 reader/editable pair",
        )
    project = read_zip(raw)
    editor = unique_json(project["project.json"])
    require(
        project["source.utf8.txt"] == source
        and project["original.txt"] == files["storygal-source/original.txt"],
        f"{slug}: reader and editable source bytes differ",
    )
    original = (SHEETS / (slug + "-worksheet.json")).read_bytes()
    public = unique_json(original)
    carriers = carriers_for_book(book, blank, source)
    require(
        assess(blank, public, source, carriers=carriers)["ok"],
        f"{slug}: invalid published judgments",
    )
    with TestClient(create_app(store)) as client:
        restored = checked(
            client.post("/api/project-bundles", files={"file": ("example.zip", raw)})
        ).json()
        require(not restored.get("restore_issues"), f"{slug}: restore issues")
        base = "/api/projects/" + restored["id"]
        api = base + "/plate-screening"
        before = checked(client.get(api)).json()
        current = before["worksheet"]
        count = len(blank["plates"])
        require(
            before["revision"] == 0
            and before["report"]["counts"]["unassessed"] == count
            and before["report"]["counts"]["screened"] == 0
            and all(p["decision"] == "unassessed" for p in current["plates"]),
            f"{slug}: fresh project must not silently inherit reviews",
        )
        preview = checked(client.get(base + "/reader/content")).json()
        require(
            checked(client.get(base + "/text")).json()["text"].encode() == source
            and checked(client.get(base + "/source")).content
            == project["original.txt"],
            f"{slug}: restored source differs",
        )
        for p in blank["plates"]:
            aid = p["image_asset_id"]
            image = files[book["media"][aid]["url"].removeprefix("./")]
            require(
                image
                == project["reader-assets/" + aid + ".png"]
                == checked(client.get(base + "/reader/assets/" + aid)).content,
                f"{slug}/{p['plate_id']}: actual restored image bytes differ",
            )
        generated = transfer_sheet(
            slug,
            public,
            current,
            book["config"]["illustrations"],
            preview["config"]["illustrations"],
            editor,
            spec,
            source,
            manual,
        )
        if slug == "chibi":
            saved = encoding(generated)
            if not write_restored:
                require(
                    (SHEETS / "chibi-restored-worksheet.json").read_bytes() == saved,
                    "curated Chibi restored worksheet is stale; rebuild and inspect it",
                )
        else:
            require(
                generated == public,
                "Last Light must use its unmodified regular worksheet",
            )
            saved = original
        version = {
            "revision": before["revision"],
            "reader_revision": before["reader_revision"],
        }

        def attempt(sheet, consent):
            return client.post(
                api + "/import",
                json=version
                | {
                    "worksheet": json.dumps(sheet, ensure_ascii=False),
                    "exact_copy": consent,
                },
            )

        negative = attempt(generated, False)
        require(
            negative.status_code in (400, 409)
            and "另一工程" in negative.json().get("detail", ""),
            "a new work ID must require explicit exact-copy consent",
        )
        if slug == "chibi":
            mismatch = attempt(public, True)
            require(
                mismatch.status_code == 400
                and "不一致" in mismatch.json().get("detail", ""),
                "Reader-only IDs must not pass the unchanged Workbench importer",
            )
        altered = deepcopy(generated)
        altered["plates"][0]["image_sha256"] = "0" * 64
        mismatch = attempt(altered, True)
        require(
            mismatch.status_code == 400
            and "不一致" in mismatch.json().get("detail", "")
            and checked(client.get(api)).json() == before,
            "incorrect bindings accepted or changed local state",
        )
        after = checked(attempt(generated, True)).json()
        normalized = Worksheet.model_validate(generated).model_dump()
        require(
            after["worksheet"] == normalized | {"work_id": restored["id"]}
            and after["report"]["ok"] is True
            and after["report"]["counts"]["screened"] == count
            and after["report"]["counts"]["active"] == 0
            and after["revision"] == 1
            and checked(client.get(api)).json() == after,
            f"{slug}: explicit import must preserve every note/binding, without claiming playback",
        )
        info = {
            "reader_sha256": reader_sha,
            "project_sha256": project_sha,
            "worksheet_sha256": digest(saved),
            "public_worksheet_sha256": digest(original),
            "source_sha256": digest(source),
            "unassessed_before": count,
            "screened": count,
            "imported_with_explicit_consent": True,
            "refused_without_consent": True,
            "refused_wrong_binding": True,
        }
        return info, saved


def check_transfers(output, edition, *, write_restored=None):
    """Run real cold restores in isolated stores, never editing a project, Reader or repository fixture."""
    require(re.fullmatch(r"v\d+\.\d+\.\d+", edition), "invalid edition")
    catalog = unique_json((SHEETS / "catalog.json").read_bytes())
    require(
        catalog["edition"] == edition, "edition must match the screened Reader catalog"
    )
    specs = unique_json((ROOT / "tools/edition-contract.json").read_bytes())["books"]
    manual = unique_json(
        (ROOT / "examples/chibi/visual-review-v0.2.0.json").read_bytes()
    )
    results = {}
    with tempfile.TemporaryDirectory(prefix="taleprism-screened-transfer-") as tmp:
        for slug in PUBLIC_091:
            result, body = check_one(
                Path(output),
                edition,
                slug,
                specs[slug],
                manual,
                Path(tmp) / slug,
                write_restored,
            )
            matches = [r for r in catalog["books"] if r["slug"] == slug]
            require(
                len(matches) == 1 and result["reader_sha256"] == matches[0]["sha256"],
                f"{slug}: Reader digest does not match the current screening catalog",
            )
            if slug == "chibi":
                generated = body
            results[slug] = result
    if write_restored:
        with Path(write_restored).open("xb") as f:
            f.write(generated)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--output", required=True, type=Path, help="Directory of the exact public pairs"
    )
    ap.add_argument(
        "--edition", required=True, help="Screened catalog edition, e.g. v0.9.1"
    )
    ap.add_argument(
        "--write-restored",
        type=Path,
        help="Regenerate the paired Chibi sidecar to a NEW path",
    )
    args = ap.parse_args()
    print(
        json.dumps(
            check_transfers(
                args.output, args.edition, write_restored=args.write_restored
            ),
            indent=2,
        )
    )
