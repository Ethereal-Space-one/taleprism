"""Build a local, dependency-free source handoff. Never uploads or reads runtime data."""

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path

from release_files import ROOT, source_files
from release_version import PREFIX


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".release" / (PREFIX + "-source.zip")
    )
    args = parser.parse_args()
    selected = source_files()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    inventory = {}
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, p in selected:
            raw = p.read_bytes()
            inventory[name] = hashlib.sha256(raw).hexdigest()
            info = zipfile.ZipInfo("taleprism/" + name)
            info.create_system = 3
            info.external_attr = (
                stat.S_IFREG | (0o755 if p.suffix in {".sh", ".command"} else 0o644)
            ) << 16
            archive.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr(
            "taleprism/SOURCE-MANIFEST.json",
            json.dumps(
                {
                    "format": "storygal-source",
                    "version": 1,
                    "files": inventory,
                    "note": "Source and examples only. Dependencies, engine binaries and local projects are excluded.",
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    result = {
        "file": str(args.output),
        "files": len(inventory),
        "bytes": args.output.stat().st_size,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
