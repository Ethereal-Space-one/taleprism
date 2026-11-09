"""Download the pinned public reader, verify its checksum/inventory, and unpack for Pages."""

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def reader_spec(root=ROOT, example=None):
    key = example or json.loads((root / "examples/site.json").read_text())["featured"]
    catalog = json.loads((root / "samples/content-packs/catalog.json").read_text())
    entry = next((s for s in catalog if s["id"] == key), None)
    if not entry or not entry.get("reader"):
        raise ValueError("No pinned reader for showcase: " + str(key))
    return entry["reader"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--example", help="Optional example ID; defaults to examples/site.json"
    )
    parser.add_argument(
        "--archive", type=Path, help="Verify a local candidate instead of downloading"
    )
    args = parser.parse_args()
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
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        if (
            len(names) != len(set(names))
            or sum(i.file_size for i in z.infolist()) > 160_000_000
        ):
            raise ValueError("Invalid reader archive size/duplicates")
        for name in names:
            p = PurePosixPath(name)
            if p.is_absolute() or ".." in p.parts or "\\" in name:
                raise ValueError("Unsafe reader path")
        inventory = json.loads(z.read("storygal-delivery.json"))["files"]
        if set(names) != set(inventory) | {"storygal-delivery.json"}:
            raise ValueError("Unexpected reader files")
        for name, meta in inventory.items():
            content = z.read(name)
            if (
                len(content) != meta["bytes"]
                or hashlib.sha256(content).hexdigest() != meta["sha256"]
            ):
                raise ValueError("Reader file checksum mismatch: " + name)
        args.output.mkdir(parents=True, exist_ok=True)
        if any(args.output.iterdir()):
            raise ValueError("Use an empty Pages output directory")
        z.extractall(args.output)
    print("Pinned reader and all contained files verified.")


if __name__ == "__main__":
    main()
