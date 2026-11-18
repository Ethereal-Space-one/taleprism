"""Make an identity-preserving re-edition from two verified reading ZIPs.

Requires exact same original, canonical text, chapter structure and retained old
media. Editable projects intentionally keep their distinct import IDs. No service,
publication, replacement of old ZIPs or access to personal reading records.
"""

import argparse
import copy
import json
from pathlib import Path

from build_chibi_demo import pack, sync_reader_data
from chibi_source import digest, encoded, read_zip, verify_inventory


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def reissue(baseline, candidate, expected):
    require(digest(baseline) == expected, "Incorrect previous archive checksum")
    old, files = read_zip(baseline), read_zip(candidate)
    for z in [old, files]:
        verify_inventory(z)
    prev, fresh = [json.loads(z["reader.json"]) for z in [old, files]]
    new = copy.deepcopy(fresh)
    for n in ["storygal-source/original.txt", "storygal-source/source.utf8.txt"]:
        require(old[n] == files[n], "Source bytes differ: " + n)
    # Never import an old project notebook to "complete" a new one, or lose
    # third-party notices/source supplements in a seemingly successful reissue.
    for name, raw in old.items():
        if name.startswith(("storygal-source/", "licenses/")):
            require(
                files.get(name) == raw,
                "Source supplement or license missing/changed: " + name,
            )
    for key in ("canonical_sha256", "rights_status", "filename"):
        require(
            prev["project"].get(key) == new["project"].get(key),
            "Edition identity mismatch: " + key,
        )

    def anchors(d):
        return [
            (b["byte_start"], b["byte_end"], b["text"], b["heading"])
            for b in d["blocks"]
        ]

    require(anchors(prev) == anchors(new), "Original paragraph anchors differ")
    require(prev["config"]["title"] == new["config"]["title"], "Title changed")
    for mid, old_media in prev["media"].items():
        m = new["media"].get(mid)
        require(
            m and (old_media["type"], old_media["sha256"]) == (m["type"], m["sha256"]),
            "Old asset was lost or replaced",
        )
        require(
            old[old_media["url"].removeprefix("./")]
            == files[m["url"].removeprefix("./")],
            "Old media bytes differ",
        )
        if old_media.get("credit"):
            require(
                old_media["credit"] == m.get("credit"), "Published attribution changed"
            )

    def identity(p):
        return (p["image_asset_id"], p["after_byte"], p["title"])

    before = prev["config"].get("illustrations", [])
    after = new["config"].get("illustrations", [])
    require(
        len(before) == len(after)
        and list(map(identity, before)) == list(map(identity, after)),
        "Illustrations moved or rebound",
    )
    for a, b in zip(before, after, strict=True):
        b["id"] = a["id"]
    require(
        prev["config"] == new["config"],
        "Previous reading arrangement, map or notes changed",
    )
    require(prev.get("characters") == new.get("characters"), "Characters changed")
    for original, restored in zip(prev["blocks"], new["blocks"], strict=True):
        for key, value in original.items():
            if key == "soundscape":
                continue
            require(
                restored.get(key) == value, "Previous block content changed: " + key
            )
    new["project"]["id"] = prev["project"]["id"]
    files["reader.json"] = encoded(new)
    sync_reader_data(files, fresh, new)
    inv = json.loads(files.pop("storygal-delivery.json"))
    inv["files"] = {
        n: {"bytes": len(raw), "sha256": digest(raw)}
        for n, raw in sorted(files.items())
    }
    files["storygal-delivery.json"] = encoded(inv)
    verify_inventory(files)
    return pack(files), {
        "prior_reader": expected,
        "raw_new_reader": digest(candidate),
        "work_id": new["project"]["id"],
        "source_sha256": digest(files["storygal-source/original.txt"]),
        "original_assets": len(prev["media"]),
        "blocks": len(new["blocks"]),
        "plates": len(after),
        "sound_blocks": [b["byte_start"] for b in new["blocks"] if b.get("soundscape")],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--baseline-sha256", required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    raw, r = reissue(
        a.baseline.read_bytes(), a.candidate.read_bytes(), a.baseline_sha256
    )
    with a.output.open("xb") as out:
        out.write(raw)
    print(json.dumps({**r, "new_reader": digest(raw)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
