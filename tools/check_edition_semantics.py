"""Verify actual delivered readers, ordinary cold exports, or the real Pages site.

The independent, reviewed book contracts encode both expected cues and silence.
Passing a ZIP checksum is required but never sufficient. A production run must
also exercise the browser, not --static-only (an explicit diagnostic).
"""

import argparse
import concurrent.futures
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from chibi_source import LIMIT, read_zip
from reissue_autoplay import inspect_story, loadzip
from release_version import FROZEN_BOOK_PREFIX, PREFIX, ROOT

CONTRACT = ROOT / "tools/edition-contract.json"
LIVE = "https://ethereal-space-one.github.io/taleprism/"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def variant(expected, name, cold):
    spec = copy.deepcopy(expected)
    if cold and name == "chibi":
        # Ordinary editable plans keep their own explicit plan-* placement IDs.
        # No fuzzy plate/title matching is permitted, even on a restored UUID.
        for plate in spec["illustrations"]:
            plate["id"] = "plan-" + plate["id"]
    return spec


def inspect(raw, expected, *, cold=False):
    files, _ = loadzip(raw)
    book = inspect_story(files)
    source = files["storygal-source/source.utf8.txt"]
    require(
        digest(source) == expected["source_sha256"]
        and source == files["storygal-source/original.txt"],
        "Original source mismatch",
    )
    require(
        book["preview"] is False and book["config"]["title"] == expected["title"],
        "Not the finished edition or wrong title",
    )
    if not cold:
        require(
            book["project"]["id"] == expected["public_work_id"],
            "Published work identity changed",
        )
    media, blocks = book["media"], book["blocks"]
    require(len(blocks) == expected["paragraphs"], "Paragraph count mismatch")
    require(
        len(book["presentations"]) == expected["presentations"]
        and len(book["map_entries"]) == expected["map_entries"],
        "Presentations/map changed",
    )
    require(
        sum(m["type"] == "image" for m in media.values()) == expected["image_members"],
        "Unexpected image count",
    )
    require(
        len(book["config"]["illustrations"]) == len(expected["illustrations"]),
        "Unexpected plate count",
    )
    for real, want in zip(
        book["config"]["illustrations"], expected["illustrations"], strict=True
    ):
        require(
            (real["id"], real["after_byte"], media[real["image_asset_id"]]["sha256"])
            == (want["id"], want["after_byte"], want["image_sha256"]),
            f"Wrong content binding for plate {want['id']}",
        )
        explicit = real.get("motion")
        if explicit is not None:
            require(
                explicit.get("reviewed") is True
                and explicit.get("effect") == want["motion"],
                "Unreviewed or wrong plate direction",
            )
    sc, narration, dialogue, audio_paths = [], [], [], set()
    for i, block in enumerate(blocks, 1):
        start, end = block["byte_start"], block["byte_end"]
        require(source[start:end].decode() == block["text"], "Paragraph bytes changed")
        if block.get("narration"):
            narration.append(start)
        dialogue.extend([start] * len(block.get("audio", [])))
        require(
            not any(r.get("take_id") for r in block.get("runs", [])),
            "Unexpected voiced dialogue run",
        )
        if cue := block.get("soundscape"):
            m = media[cue["id"]]
            path = m["url"].removeprefix("./")
            require(
                m["type"] == "audio"
                and m["origin"] == "paragraph_soundscape"
                and path in files,
                "Missing accepted WAV",
            )
            with wave.open(io.BytesIO(files[path]), "rb") as wav:
                require(
                    wav.getparams()[:4] == (2, 2, 24000, 288000),
                    "Unexpected WAV channels/rate/duration",
                )
            sc.append(
                {
                    "paragraph": i,
                    "byte": start,
                    "duration": cue["duration"],
                    "description": cue["description"],
                    "sha256": digest(files[path]),
                }
            )
            audio_paths.add(path)
    require(sc == expected["soundscapes"], f"Wrong soundscape/anchor/WAV: {sc!r}")
    require(
        narration == expected["narrations"] and dialogue == expected["dialogue_audio"],
        "Unexpected narration/dialogue",
    )
    require(
        audio_paths
        == {
            m["url"].removeprefix("./") for m in media.values() if m["type"] == "audio"
        },
        "Unbound audio media",
    )
    require(
        audio_paths
        == {
            p
            for p in files
            if p.startswith("media/")
            and p.lower().endswith((".wav", ".mp3", ".ogg", ".aiff", ".m4a"))
        },
        "Unexpected audio member",
    )
    require(
        book["config"].get("echo_fold") == expected["echo"],
        "Wrong echoed quote or source/target paragraph",
    )
    require(
        files.get("licenses/Taleprism-MIT.txt") == (ROOT / "LICENSE").read_bytes(),
        "Missing exact MIT notice",
    )
    return files


def same_site(files, directory=None, url=None):
    """All live/staged payload bytes must match the already semantically approved reader."""
    if directory:
        actual = {
            p.relative_to(directory).as_posix()
            for p in directory.rglob("*")
            if p.is_file()
        }
        require(
            actual == set(files), "Staged Pages tree does not exactly match the reader"
        )
        require(
            all((directory / p).read_bytes() == b for p, b in files.items()),
            "Staged Pages file changed",
        )
    if url:
        require(
            url == LIVE,
            "Live verification is scoped to the official Taleprism Pages prefix",
        )

        def one(k):
            with urlopen(url + quote(k, safe="/"), timeout=40) as r:
                require(
                    r.geturl().startswith(LIVE),
                    "Live file redirected outside the reading room",
                )
                require(
                    r.read(len(files[k]) + 1) == files[k], f"Live file mismatch: {k}"
                )

        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            list(pool.map(one, files))


def run():
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--output",
        type=Path,
        help="Release asset directory; tests 4 readers and 2 editable projects",
    )
    group.add_argument(
        "--frozen-books",
        type=Path,
        help="Test 6 pinned historical book ZIPs with the current workbench; not a release finalization",
    )
    group.add_argument(
        "--reader-zip",
        type=Path,
        help="Exact released Pages or individually selected reader ZIP",
    )
    ap.add_argument(
        "--book", choices=["chibi", "last-light", "the-door-left-open", "the-margin"]
    )
    ap.add_argument("--site-dir", type=Path, help="Verify every staged Pages file")
    ap.add_argument(
        "--live-url",
        choices=[LIVE],
        help="Verify every live Pages file plus real browser",
    )
    ap.add_argument("--chromium")
    ap.add_argument(
        "--static-only",
        action="store_true",
        help="Diagnosis only; does NOT pass CI/CD acceptance",
    )
    ap.add_argument(
        "--report",
        type=Path,
        help="New success receipt; never emitted for static-only or partial failure",
    )
    args = ap.parse_args()
    if args.report and (args.static_only or args.report.exists()):
        ap.error("--report needs a fresh destination and complete browser verification")
    if bool(args.reader_zip) != bool(args.book) or (
        (args.site_dir or args.live_url) and args.book != "chibi"
    ):
        ap.error("--reader-zip requires --book; Pages flags require --book chibi")
    contract = json.loads(CONTRACT.read_text())["books"]
    chrome = (
        args.chromium
        or os.getenv("CHROME_PATH")
        or next(
            (
                p
                for n in ("google-chrome", "chromium", "chromium-browser")
                if (p := shutil.which(n))
            ),
            None,
        )
    )
    if not args.static_only and not chrome:
        ap.error("A real Chrome/Chromium is required; missing browser is not a pass")
    with tempfile.TemporaryDirectory(prefix="taleprism-semantics-") as temp:
        scratch = Path(temp)
        jobs = []
        asset_hashes = {}

        def archive(p):
            raw = p.read_bytes()
            asset_hashes[p.name] = digest(raw)
            return raw

        def check(name, data, kind):
            specification = variant(contract[name], name, kind == "cold")
            files = inspect(data, specification, cold=kind == "cold")
            print(f"Static contract: {name}/{kind}, ZIP {digest(data)}.", flush=True)
            if args.site_dir or args.live_url:
                same_site(files, args.site_dir, args.live_url)
            if not args.static_only:
                folder = scratch / (name + "-" + kind)
                folder.mkdir()
                for path, raw in files.items():
                    dest = folder / path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(raw)
                url = (
                    args.live_url
                    or (args.site_dir or folder).resolve().as_uri() + "/index.html"
                )
                jobs.append(
                    {
                        "slug": name,
                        "kind": kind,
                        "url": url,
                        "folder": str(folder),
                        "expected": specification,
                    }
                )

        if args.reader_zip:
            check(args.book, archive(args.reader_zip), "reader")
        else:
            from build_public_example_pairs import cold_export

            folder = args.output or args.frozen_books
            prefix = FROZEN_BOOK_PREFIX if args.frozen_books else PREFIX
            pins = {}
            if args.frozen_books:
                from build_distribution_candidate import PINS
                from check_plate_studies import SHEETS, plans

                books = plans(json.loads((SHEETS / "catalog.json").read_bytes()))
                pins = {b["reader"]: b["sha256"] for b in books}
                pins.update(
                    {f"{prefix}-{s}-project.zip": p["project"] for s, p in PINS.items()}
                )
            else:
                for suffix in ("source", "prompt-starter"):
                    archive(folder / f"{PREFIX}-{suffix}.zip")

            def book_archive(name):
                path = folder / name
                require(
                    not path.is_symlink()
                    and path.is_file()
                    and path.stat().st_size <= LIMIT,
                    "Missing/oversized: " + name,
                )
                raw = archive(path)
                if args.frozen_books:
                    require(
                        asset_hashes[name] == pins[name],
                        "Wrong frozen book SHA-256: " + name,
                    )
                return raw

            for name in contract:
                check(name, book_archive(f"{prefix}-{name}-reader.zip"), "reader")
                if name in ("chibi", "last-light"):
                    raw = book_archive(f"{prefix}-{name}-project.zip")
                    project = json.loads(read_zip(raw)["project.json"])
                    takes = project["records"].get("soundscape_takes", [])
                    want = contract[name]["soundscapes"]
                    require(
                        [(s["status"], s["byte_start"], s["sha256"]) for s in takes]
                        == [("accepted", s["byte"], s["sha256"]) for s in want],
                        "Wrong editable accepted cue or included private takes",
                    )
                    require(
                        not project["records"].get("narration_takes")
                        and not project["records"].get("speech_takes"),
                        "Unexpected private audio history",
                    )
                    check(name, cold_export(raw, scratch / ("restore-" + name)), "cold")
        if jobs:
            spec = scratch / "run.json"
            spec.write_text(json.dumps({"jobs": jobs, "books": contract}))
            subprocess.run(
                [
                    "node",
                    str(ROOT / "tools/webgal-verify/edition-semantic-check.cjs"),
                    str(spec),
                    chrome,
                    str(scratch / "browser.json"),
                ],
                check=True,
            )
            observations = json.loads((scratch / "browser.json").read_text())
            if args.report:
                receipt = {
                    "schema": 1,
                    "static_only": False,
                    "mode": "release"
                    if args.output
                    else "frozen-books"
                    if args.frozen_books
                    else "pages-live"
                    if args.live_url
                    else "pages-staged"
                    if args.site_dir
                    else "reader",
                    "source_commit": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                    ).strip(),
                    "zip_sha256": asset_hashes,
                    "cold_exports": sorted(
                        j["slug"] for j in jobs if j["kind"] == "cold"
                    ),
                    "browser_version": observations["browser_version"],
                    "results": observations["results"],
                }
                with args.report.open("x", encoding="utf-8") as output:
                    output.write(
                        json.dumps(
                            receipt, sort_keys=True, ensure_ascii=False, indent=2
                        )
                        + "\n"
                    )
            print(
                "PASS: actual artifact, book intent and real browser observations.",
                flush=True,
            )
        else:
            print("STATIC ONLY: no browser acceptance or deployment authorization.")


if __name__ == "__main__":
    run()
