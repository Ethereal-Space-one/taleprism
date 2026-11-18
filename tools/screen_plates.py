"""Inventory actual Reader illustrations and check a private sidecar. Neither input is rewritten.

Use the backend Python environment (Pillow, Pydantic). No browser is needed for intent
coverage. Only a fresh --probe or the exact independent public 0.9.1 --receipt can
promote an eligible treatment from candidate to active; personal notes cannot.
A motion proposal with no bound treatment must name a supported proposed_effect
(rain-wet-ground or wave-impact-backwash); otherwise choose deferred.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from chibi_source import LIMIT
from reissue_autoplay import inspect_story, loadzip, verified_runtime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
from storygal.plate_screening import (
    Judgment,
    Worksheet,
    assess,
    carriers_for_book,
    digest,
    make_worksheet,
    reconcile,
    require,
)
from storygal.portable_reader import TEMPLATE, embed_story

# Independent hosted CI receipt for v0.9.1; NOT a release attachment or ZIP member.
# https://github.com/Ethereal-Space-one/taleprism/actions/runs/44263696049/job/134662927169
RECEIPT_091 = "9459b7a30f7cade776b12ad7ffdc5907e8d18a8efd6c77e195324f9dd16c3efe"
COMMIT_091 = "f73c3e07751dd62bbb394fe405bce6334b5acbf0"
RUNTIME_091 = {
    "reader.js": "043693c909eea69de270fe24c87bbaa9893a5a40d95120b52989a311799cdab6",
    "reader.css": "865f7452217de8ec333e361d0209cc1cb980e6437d7b571d51abd1838982d967",
}


def unique_json(raw):
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            require(k not in obj, f"duplicate JSON key: {k}")
            obj[k] = v
        return obj

    def invalid(value):
        raise ValueError(f"invalid JSON constant: {value}")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def limited(path, maximum):
    require(
        path.is_file() and path.stat().st_size <= maximum,
        f"missing or oversized file: {path}",
    )
    return path.read_bytes()


def inventory(path):
    raw = limited(path, LIMIT)
    sha = digest(raw)
    files, _ = loadzip(raw)
    unique_json(files["reader.json"])
    book = inspect_story(files)
    require(
        book.get("preview") is False,
        "expected a finished portable Reader, not a preview",
    )
    src = files["storygal-source/source.utf8.txt"]
    original = files["storygal-source/original.txt"]
    if original != src:
        # The exporter also supports lossless GB18030 originals. Individually matching
        # metadata hashes would not detect an unrelated original and working text.
        text = original.decode("gb18030", errors="strict")
        require(
            text.encode("gb18030") == original and text.encode("utf-8") == src,
            "original and canonical source do not describe the same text",
        )
    sheet = make_worksheet(
        book, src, lambda aid: files[book["media"][aid]["url"].removeprefix("./")]
    )
    return sha, files, book, src, sheet


def receipt_evidence(raw, sha, current, carriers):
    require(
        digest(raw) == RECEIPT_091,
        "untrusted or changed receipt (v0.9.1 published acceptance only); use a fresh --probe for other editions",
    )
    r = unique_json(raw)
    require(
        r["schema"] == 1
        and r["source_commit"] == COMMIT_091
        and r["mode"] == "release"
        and r["static_only"] is False,
        "not the complete independent release browser acceptance",
    )
    matches = [
        re.fullmatch(r"taleprism-v0\.9\.1-(.+)-reader\.zip", k)
        for k, v in r["zip_sha256"].items()
        if v == sha
    ]
    require(
        len(matches) == 1 and matches[0] is not None,
        "receipt does not bind this exact Reader ZIP",
    )
    slug = matches[0][1]
    contract = unique_json((ROOT / "tools/edition-contract.json").read_bytes())[
        "books"
    ][slug]
    require(
        current["work_id"] == contract["public_work_id"]
        and current["source_sha256"] == contract["source_sha256"],
        "release work/source identity mismatch",
    )
    ids = [p["plate_id"] for p in current["plates"]]
    require(
        ids == [p["id"] for p in contract["illustrations"]]
        and carriers
        == {p["id"]: p["motion"] for p in contract["illustrations"] if p["motion"]},
        "release contract, plate inventory or eligible effect disagreement",
    )
    observations = [
        v for v in r["results"] if v["book"] == slug and v["kind"] == "reader"
    ]
    normal = [v for v in observations if v["policy"] == "normal"]
    quiet = [v for v in observations if v["policy"] == "quiet"]
    require(
        len(normal) == len(quiet) == 1
        and normal[0]["changed_motion"] == list(carriers)
        and not quiet[0]["changed_motion"]
        and all(v["visible_plates"] == len(ids) for v in observations),
        "release receipt lacks matching normal/quiet plate observations",
    )
    return set(normal[0]["changed_motion"]), r["browser_version"]


def trust_probe_payload(files, book):
    require(
        files["index.html"] == embed_story(TEMPLATE, book).encode(),
        "unrecognized HTML envelope; will not execute this ZIP for browser proof",
    )
    names = tuple(RUNTIME_091)
    shipped = {n: files[f"assets/{n}"] for n in names}
    if {n: digest(shipped[n]) for n in names} != RUNTIME_091:
        build = ROOT / "frontend/dist/reader"
        require(
            (build / "runtime-checksums.json").is_file()
            and verified_runtime(build) == shipped,
            "unknown reader JS/CSS; use an exact trusted local build or released runtime before --probe",
        )
    members = {"reader.json", "index.html", *("assets/" + n for n in names)}
    for aid, a in book["media"].items():
        kind = a.get("type")
        require(
            kind in ("audio", "image", "figure")
            and re.fullmatch(r"[A-Za-z0-9_-]+", aid)
            and a.get("id") == aid,
            f"unexpected media key or kind: {aid}",
        )
        name = "media/" + aid + (".wav" if kind == "audio" else ".png")
        require(
            a.get("url") == "./" + name and name in files,
            f"unexpected media path: {aid}",
        )
        members.add(name)
    return members


def observed_active(result, current, carriers):
    require(
        isinstance(result, dict)
        and set(result) == {"schema_version", "browser_version", "observations"}
        and type(result["schema_version"]) is int
        and result["schema_version"] == 1
        and isinstance(result["browser_version"], str)
        and re.fullmatch(r"\d+(?:\.\d+){1,3}", result["browser_version"]),
        "incomplete or unknown direct browser observation",
    )
    ids = [p["plate_id"] for p in current["plates"]]
    rows = result["observations"]
    require(
        isinstance(rows, list) and len(rows) == len(ids),
        "browser missed or added plates",
    )
    active = set()
    for pid, row in zip(ids, rows, strict=True):
        require(
            isinstance(row, dict)
            and set(row)
            == {"plate_id", "eligible_effect", "normal_frames", "reduced_frames"}
            and row["plate_id"] == pid,
            f"{pid}: missing, duplicate or misordered browser observation",
        )
        effect = carriers.get(pid)
        require(
            effect == row["eligible_effect"],
            f"{pid}: static data and runtime eligibility disagree",
        )
        n, reduced = row["normal_frames"], row["reduced_frames"]
        require(
            type(n) is int
            and type(reduced) is int
            and reduced == 0
            and (n >= 2 if effect else n == 0),
            f"{pid}: expected changing nonempty frames only during eligible normal reading, none during reduced motion",
        )
        if effect:
            active.add(pid)
    return active, result["browser_version"]


def probe(files, book, current, carriers, chrome):
    members = trust_probe_payload(files, book)
    chrome = (
        chrome
        or os.environ.get("CHROME_PATH")
        or next(
            (
                p
                for n in ("google-chrome", "chromium", "chromium-browser")
                if (p := shutil.which(n))
            ),
            None,
        )
    )
    require(
        chrome,
        "--probe requires Chromium (--chromium PATH or CHROME_PATH); no browser is not proof",
    )
    with tempfile.TemporaryDirectory(prefix="taleprism-plate-check-") as tmp:
        work = Path(tmp)
        folder, result = work / "reader", work / "result.json"
        for name in sorted(members):
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(files[name])
        # Import no proof data from the worksheet or ZIP; launch our own local checker.
        subprocess.run(
            [
                "node",
                str(ROOT / "tools/webgal-verify/probe-plate-motion.cjs"),
                str(folder),
                chrome,
                str(result),
            ],
            check=True,
            stdout=sys.stderr,
        )
        return observed_active(unique_json(limited(result, 100_000)), current, carriers)


def apply_study(sha, current, prior, source, study, carriers):
    require(
        isinstance(study, dict)
        and set(study) == {"reader_sha256", "plates"}
        and study["reader_sha256"] == sha,
        "study must pin this exact reader_sha256, not just a title/work/plate ID",
    )
    assess(
        current, prior, source, carriers=carriers
    )  # validates even a partial worksheet's bindings
    out = Worksheet.model_validate(prior).model_dump()
    by_id = {r["plate_id"]: r for r in out["plates"]}
    seen = set()
    require(isinstance(study["plates"], list), "expected study.plates array")
    for value in study["plates"]:
        r = Judgment.model_validate(value).model_dump()
        pid = r["plate_id"]
        require(
            pid in by_id and pid not in seen, f"{pid}: unknown or duplicate study plate"
        )
        seen.add(pid)
        by_id[pid].update(r)
    result = assess(current, out, source, carriers=carriers)
    for p in result["plates"]:
        if p["plate_id"] in seen and p["decision"] != "unassessed":
            require(not p["errors"], f"{p['plate_id']}: " + "; ".join(p["errors"]))
    return out


def write_new(path, obj):
    # Never open an existing path (including the Reader ZIP) for writing.
    with path.open("x", encoding="utf-8") as f:
        f.write(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def run(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest="command", required=True)
    for verb, description in [
        (
            "init",
            "Create a new private worksheet; begin with every actual plate unassessed",
        ),
        (
            "apply",
            "Merge explicitly reviewed, ZIP-pinned plate judgments into a NEW private worksheet",
        ),
        (
            "check",
            "Check every current plate against the worksheet; never plays or inserts motion by default",
        ),
    ]:
        cmd = commands.add_parser(verb, help=description)
        cmd.add_argument("reader", metavar="READER.zip", type=Path)
        cmd.add_argument("worksheet", metavar="WORKSHEET.json", type=Path)
        if verb == "init":
            cmd.add_argument(
                "--previous",
                type=Path,
                help="Carry only exact unchanged plate bindings forward",
            )
        if verb == "apply":
            cmd.add_argument(
                "--study",
                type=Path,
                required=True,
                help="JSON {reader_sha256,plates:[...]} (partial allowed)",
            )
            cmd.add_argument("--out", type=Path, required=True)
        if verb == "check":
            proof = cmd.add_mutually_exclusive_group()
            proof.add_argument(
                "--receipt",
                type=Path,
                help="Exact v0.9.1 hosted CI edition-acceptance.json (not a Release attachment)",
            )
            proof.add_argument(
                "--probe",
                action="store_true",
                help="Independently observe this approved runtime in a real browser",
            )
            cmd.add_argument("--chromium", help="Chromium executable for --probe")
            cmd.add_argument(
                "--json", action="store_true", help="Machine-readable report on stdout"
            )
    args = ap.parse_args(argv)
    try:
        sha, files, book, source, current = inventory(args.reader)
        if args.command == "init":
            out, messages = (
                reconcile(current, unique_json(limited(args.previous, 2_000_000)))
                if args.previous
                else (current, [])
            )
            write_new(args.worksheet, out)
            for message in messages:
                print(message)
            print(
                f"{len(out['plates'])} narrative plate(s); worksheet: {args.worksheet}; Reader SHA-256 {sha}"
            )
            return 0
        sheet = unique_json(limited(args.worksheet, 2_000_000))
        carriers = carriers_for_book(book, current, source)
        if args.command == "apply":
            study = unique_json(limited(args.study, 2_000_000))
            write_new(
                args.out, apply_study(sha, current, sheet, source, study, carriers)
            )
            print(
                f"Saved the specified human judgments to {args.out}; no media or motion changed."
            )
            return 0
        active, browser, proof = set(), None, None
        if args.receipt:
            active, browser = receipt_evidence(
                limited(args.receipt, 100_000), sha, current, carriers
            )
            proof = "public-v0.9.1-receipt"
        elif args.probe:
            active, browser = probe(files, book, current, carriers, args.chromium)
            proof = "fresh-browser-probe"
        elif args.chromium:
            raise ValueError("--chromium only applies with --probe")
        report = assess(current, sheet, source, carriers=carriers, active=active)
        report.update(
            reader_sha256=sha,
            work_id=current["work_id"],
            proof=proof,
            browser_version=browser,
        )
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(
                f"{report['counts']['screened']}/{report['counts']['total']} screened, "
                f"{report['counts']['active']} verified active ({proof or 'no browser proof supplied'})"
            )
            for p in report["plates"]:
                print(
                    f"  {p['plate_id']}: {p['status']}"
                    + (" — " + "; ".join(p["errors"]) if p["errors"] else "")
                )
        return 0 if report["ok"] else 1
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        AttributeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"Plate screening failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
