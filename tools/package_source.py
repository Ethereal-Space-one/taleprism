"""Build a reproducible local source handoff from the explicit source inventory. No uploads."""

import argparse
import hashlib
import json
import os
import stat
import tempfile
import zipfile
from pathlib import Path

from release_files import ROOT, source_files
from release_version import PREFIX

# ZIP's earliest supported timestamp, independent of time zone, clock and checkout mtimes.
EPOCH = (1980, 1, 1, 0, 0, 0)
MANIFEST = "SOURCE-MANIFEST.json"


def document(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def entry(archive, name, content):
    info = zipfile.ZipInfo("taleprism/" + name, date_time=EPOCH)
    info.create_system = 3
    mode = 0o755 if name.endswith((".sh", ".command")) else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    # Most bytes are PNGs. Storing entries also removes variation across zlib versions.
    archive.writestr(info, content, compress_type=zipfile.ZIP_STORED)


def package_source(output, root=ROOT):
    output = Path(output)
    if output.suffix.lower() != ".zip":
        raise ValueError("Source archive output must end in .zip")
    selected = source_files(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    inventory = {}
    # Never leave a partial archive in place of a previous, successful handoff.
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            for name, path in selected:
                raw = path.read_bytes()
                inventory[name] = hashlib.sha256(raw).hexdigest()
                entry(archive, name, raw)
            entry(
                archive,
                MANIFEST,
                document(
                    {
                        "format": "storygal-source",
                        "version": 1,
                        "files": inventory,
                        "note": "Source and examples only. Dependencies, engine binaries and local projects are excluded.",
                    }
                ),
            )
        with temporary.open("rb") as f:
            checksum = hashlib.file_digest(f, "sha256").hexdigest()
        result = {
            "file": output.name,
            "files": len(inventory),
            "bytes": temporary.stat().st_size,
            "sha256": checksum,
        }
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    # Shareable alongside the ZIP: stable basename, never the builder's checkout path.
    output.with_suffix(".json").write_bytes(document(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".release" / (PREFIX + "-source.zip")
    )
    print(
        json.dumps(
            package_source(parser.parse_args().output), ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
