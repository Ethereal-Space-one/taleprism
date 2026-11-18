"""Exercise a real v0.9 reader's saved plate, bookmark and font on a same-origin upgrade.

Use --previous DIR to stay offline; --fetch-previous downloads only the two fixed
public predecessors, not end-user records. Requires the locked browser tools.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen

from reissue_autoplay import loadzip
from release_version import PREFIX, ROOT

OLD = {
    "chibi": "16c89132d27345b51d6ef223c8c3db676b5f804f95c10987c5a5e5de6f09cc28",
    "last-light": "f7dd4374b75924f7c7c378c901c57894b6182e0cec51d4c5754aef0ae7856e35",
}


def extract(raw, directory):
    files, _ = loadzip(raw)
    for rel, body in files.items():
        dst = directory / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(body)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output", type=Path, required=True, help="Candidate release folder"
    )
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--previous", type=Path)
    source.add_argument("--fetch-previous", action="store_true")
    p.add_argument("--chromium")
    args = p.parse_args()
    chrome = (
        args.chromium
        or os.getenv("CHROME_PATH")
        or next(
            (
                x
                for n in (
                    "google-chrome",
                    "google-chrome-stable",
                    "chromium",
                    "chromium-browser",
                )
                if (x := shutil.which(n))
            ),
            None,
        )
    )
    if not chrome:
        p.error("Chrome/Chromium not available")
    with tempfile.TemporaryDirectory(prefix="taleprism-upgrade-") as tmp:
        root = Path(tmp)
        for book, prior_digest in OLD.items():
            filename = f"taleprism-v0.9.0-{book}-reader.zip"
            if args.previous:
                raw = (args.previous / filename).read_bytes()
            else:
                with urlopen(
                    "https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.0/"
                    + filename,
                    timeout=90,
                ) as r:
                    raw = r.read(160_000_001)
            if hashlib.sha256(raw).hexdigest() != prior_digest:
                raise ValueError("Wrong v0.9.0 predecessor: " + filename)
            old, new = root / book / "previous", root / book / "candidate"
            extract(raw, old)
            extract((args.output / f"{PREFIX}-{book}-reader.zip").read_bytes(), new)
            script = ROOT / "tools/webgal-verify"
            subprocess.run(
                [
                    "node",
                    str(script / "edition-upgrade.cjs"),
                    str(old),
                    str(new),
                    book,
                    str(chrome),
                ],
                check=True,
            )
            if book == "chibi":
                subprocess.run(
                    [
                        "node",
                        str(script / "release-progress-check.cjs"),
                        str(old),
                        str(new),
                        str(root / "legacy-shape"),
                    ],
                    check=True,
                    env={**os.environ, "CHROME_PATH": str(chrome)},
                )


if __name__ == "__main__":
    main()
