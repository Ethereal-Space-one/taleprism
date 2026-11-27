"""Download the pinned public reader, verify its checksum/inventory, and unpack for Pages."""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

from reissue_autoplay import (
    INVENTORY,
    inspect_story,
    loadzip,
    packed,
    sha,
    summary,
    verified_runtime,
)

ROOT = Path(__file__).resolve().parents[1]


def reader_spec(root=ROOT, example=None):
    key = example or json.loads((root / "examples/site.json").read_text())["featured"]
    catalog = json.loads((root / "samples/content-packs/catalog.json").read_text())
    entry = next((s for s in catalog if s["id"] == key), None)
    if not entry or not entry.get("reader"):
        raise ValueError("No pinned reader for showcase: " + str(key))
    return entry["reader"]


def online_reader(raw, runtime_dir):
    """Update only the online shell and runtime, never the original book or work ID."""
    old, inventory = loadzip(raw)
    book = inspect_story(old)
    if book["config"].get("map_profile") != "chibi":
        raise ValueError("The online showcase is scoped to Chibi")
    runtime = verified_runtime(runtime_dir)
    new = dict(old)
    index = old["index.html"]
    shell = b'<div id="root">'
    if index.count(shell) != 1:
        raise ValueError("Unknown online reader shell")
    index = index.replace(shell, b'<div id="root" data-edition="online-chibi">')
    sums = {name: sha(data) for name, data in runtime.items()}
    for name, data in runtime.items():
        new["assets/" + name] = data
        url = ("./assets/" + name).encode("ascii")
        if index.count(url) != 1:
            raise ValueError("Unknown online runtime asset location")
        index = index.replace(url, url + b"?v=" + sums[name][:16].encode("ascii"))
    new["index.html"] = index
    new[INVENTORY] = json.dumps(
        {
            **inventory,
            "pages_runtime": {"reader_sha256": sha(raw), "assets": sums},
            "files": summary(new),
        },
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    if inspect_story(new) != book:
        raise ValueError("Published story changed")
    return packed(new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--example", help="Optional example ID; defaults to examples/site.json"
    )
    parser.add_argument(
        "--archive", type=Path, help="Verify a local candidate instead of downloading"
    )
    parser.add_argument(
        "--retain-archive",
        type=Path,
        help="Save the validated ZIP outside the Pages root for the browser acceptance gate.",
    )
    parser.add_argument(
        "--runtime", type=Path, help="Use the checked current portable runtime for Pages"
    )
    args = parser.parse_args()
    if args.retain_archive and (
        args.retain_archive.resolve().is_relative_to(args.output.resolve())
        or args.retain_archive.exists()
    ):
        parser.error("--retain-archive needs a new path outside the Pages root")
    spec = reader_spec(example=args.example)
    if args.archive:
        raw = args.archive.read_bytes()
    else:
        if not spec["url"].startswith("https://github.com/"):
            raise ValueError("Reader must be a pinned GitHub release asset")
        with urllib.request.urlopen(spec["url"], timeout=60) as response:
            raw = response.read(160_000_001)
    if len(raw) > 160_000_000 or hashlib.sha256(raw).hexdigest() != spec["sha256"]:
        raise ValueError("Reader download checksum mismatch")
    if args.runtime:
        raw = online_reader(raw, args.runtime)
    files, _ = loadzip(raw)
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError("Use an empty Pages output directory")
    for name, content in files.items():
        path = args.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    if args.retain_archive:
        args.retain_archive.parent.mkdir(parents=True, exist_ok=True)
        with args.retain_archive.open("xb") as dst:
            dst.write(raw)
    print("Pinned reader and all contained files verified.")


if __name__ == "__main__":
    main()
