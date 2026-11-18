"""Verify and open both final public encounter ZIPs in offline Chromium; no Python browser dependency.

First install tools/webgal-verify's locked npm dependencies. Chrome/Chromium needs to
be on PATH, or pass --chromium. Runs locally or from Linux CI after the book build.
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from reissue_autoplay import inspect_story, loadzip, sha
from release_version import PREFIX, ROOT

BOOKS = ("the-door-left-open", "the-margin")


def check(output, chromium=None):
    output = Path(output).resolve()
    chrome = (
        chromium
        or os.getenv("CHROME_PATH")
        or next(
            (
                p
                for name in (
                    "google-chrome",
                    "google-chrome-stable",
                    "chromium",
                    "chromium-browser",
                )
                if (p := shutil.which(name))
            ),
            None,
        )
    )
    if not chrome or not shutil.which(str(chrome)):
        raise SystemExit(
            "No usable Chrome/Chromium. Install a browser or pass --chromium /path/to/chrome."
        )
    node = shutil.which("node")
    if not node:
        raise SystemExit("Install Node.js 22+ before running the offline reader check.")
    with tempfile.TemporaryDirectory(prefix="taleprism-public-preview-") as tmp:
        root = Path(tmp)
        for book in BOOKS:
            archive = output / f"{PREFIX}-{book}-reader.zip"
            if not archive.is_file():
                raise SystemExit(
                    f"Missing final reader ZIP: {archive.name} in {output}"
                )
            raw_zip = archive.read_bytes()
            files, _ = loadzip(raw_zip)
            record = inspect_story(files)
            sample = ROOT / "examples/encounters" / book
            if record != json.loads((sample / "reading.json").read_bytes()):
                raise ValueError(
                    f"{book}: packaged story differs from the public reading arrangement"
                )
            if (
                files["storygal-source/original.txt"]
                != (sample / "source.txt").read_bytes()
            ):
                raise ValueError(f"{book}: public original changed")
            if files["licenses/Taleprism-MIT.txt"] != (ROOT / "LICENSE").read_bytes():
                raise ValueError(f"{book}: incorrect reader MIT notice")
            print(f"Verified {archive.name} (SHA-256 {sha(raw_zip)})", flush=True)
            # loadzip checked canonical, relative, non-link paths and the full inventory.
            for name, raw in files.items():
                target = root / book / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
        subprocess.run(
            [
                node,
                str(ROOT / "tools/webgal-verify/public-preview-check.cjs"),
                str(root),
                str(chrome),
            ],
            check=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Directory containing both final reader ZIPs.",
    )
    parser.add_argument(
        "--chromium", help="Chrome/Chromium executable (optional if on PATH)."
    )
    opts = parser.parse_args()
    check(opts.output, opts.chromium)
