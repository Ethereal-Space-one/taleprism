"""Bind frozen local release artifacts to a clean, reviewed Git commit. No upload."""

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

from build_release import starter_entries
from release_files import ROOT, source_files, tracked_inventory
from release_version import PREFIX, VERSION


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def finalize(output):
    output = Path(output).resolve()
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT
    ):
        raise ValueError("Commit reviewed source changes before finalizing a release.")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    selected = source_files()
    if [name for name, _ in selected] != tracked_inventory():
        raise ValueError("Public source inventory does not match the Git index.")
    manifest = json.loads((output / "release-manifest.json").read_text())
    if manifest["version"] != VERSION:
        raise ValueError("Release version mismatch")
    expected = {
        PREFIX + "-prompt-starter.zip",
        *[
            f"{PREFIX}-{example}-{kind}.zip"
            for example in ("chibi", "last-light")
            for kind in ("project", "reader")
        ],
    }
    records = [a for a in manifest["artifacts"] if a.get("kind") != "source"]
    if len(records) != len(expected) or {a["file"] for a in records} != expected:
        raise ValueError("A complete release needs the starter and both example pairs.")
    for record in records:
        raw = (output / record["file"]).read_bytes()
        if len(raw) != record["bytes"] or digest(raw) != record["sha256"]:
            raise ValueError("Frozen artifact changed: " + record["file"])
    with zipfile.ZipFile(output / (PREFIX + "-prompt-starter.zip")) as starter:
        entries = starter_entries()
        if sorted(starter.namelist()) != sorted(entries) or any(
            starter.read(name) != raw for name, raw in entries.items()
        ):
            raise ValueError("Prompt starter does not match the final reviewed source.")
    source = output / (PREFIX + "-source.zip")
    with zipfile.ZipFile(source) as archive:
        inventory = {name: digest(path.read_bytes()) for name, path in selected}
        document = json.loads(archive.read("taleprism/SOURCE-MANIFEST.json"))
        expected_files = sorted("taleprism/" + name for name in [*inventory, "SOURCE-MANIFEST.json"])
        if document["files"] != inventory or sorted(archive.namelist()) != expected_files:
            raise ValueError("Source archive does not match the final reviewed source.")
        for name, expected_hash in inventory.items():
            if digest(archive.read("taleprism/" + name)) != expected_hash:
                raise ValueError("Source archive checksum mismatch: " + name)
    catalog = json.loads((ROOT / "samples/content-packs/catalog.json").read_text())
    for example in ("chibi", "last-light"):
        entry = next(e for e in catalog if e["id"] == example)
        for kind in ("project", "reader"):
            pin = entry if kind == "project" else entry["reader"]
            record = next(
                a
                for a in records
                if a.get("example") == example and a.get("kind") == kind
            )
            if pin["file"] != record["file"] or pin["sha256"] != record["sha256"]:
                raise ValueError("Catalog does not match frozen artifacts: " + example)
    raw = source.read_bytes()
    records.append(
        {
            "file": source.name,
            "bytes": len(raw),
            "sha256": digest(raw),
            "kind": "source",
            "example": None,
        }
    )
    manifest.update(commit=commit, artifacts=records)
    manifest_path = output / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    sums = "".join(a["sha256"] + "  " + a["file"] + "\n" for a in records)
    sums += digest(manifest_path.read_bytes()) + "  release-manifest.json\n"
    (output / "SHA256SUMS").write_text(sums)
    return {
        "version": VERSION,
        "commit": commit,
        "archives": len(records),
        "checksums": str(output / "SHA256SUMS"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".release" / ("v" + VERSION)
    )
    print(json.dumps(finalize(parser.parse_args().output), indent=2))
