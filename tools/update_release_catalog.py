"""Pin explicitly named example artifacts without mixing projects and readers."""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = {
    "last-light": {
        "title": "末班灯 · 现代原创短篇",
        "description": "三镜头短篇教程，含原文、人物参考、场景物件与助手制作检查。公开版无系统演示音频。",
    },
    "chibi": {
        "title": "赤壁 · 可编辑主示例",
        "description": "12幅情境图、8位角色、9张立绘、3阶段地图；含新版制作方案与检查依据。公开版无系统演示音频。",
    },
}


def pin_release(release, root=ROOT):
    version = release["version"]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid release version")
    base = (
        f"https://github.com/Ethereal-Space-one/taleprism/releases/download/v{version}/"
    )
    catalog_path = root / "samples/content-packs/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    updates = {}
    for example, description in EXAMPLES.items():
        matching = [a for a in release["artifacts"] if a.get("example") == example]
        if not matching:
            continue
        pair = {}
        for artifact in matching:
            kind = artifact.get("kind")
            if kind not in {"project", "reader"} or kind in pair:
                raise ValueError("Ambiguous example artifact: " + example)
            expected = f"taleprism-v{version}-{example}-{kind}.zip"
            if artifact["file"] != expected or not re.fullmatch(
                r"[0-9a-f]{64}", artifact["sha256"]
            ):
                raise ValueError("Invalid example filename/checksum: " + example)
            pair[kind] = artifact
        if set(pair) != {"project", "reader"}:
            raise ValueError("Missing project or reader for " + example)
        project, reader = pair["project"], pair["reader"]
        updates[example] = {
            "id": example,
            **description,
            "file": project["file"],
            "sha256": project["sha256"],
            "download_url": base + project["file"],
            "reader": {
                "file": reader["file"],
                "sha256": reader["sha256"],
                "url": base + reader["file"],
            },
        }
    if not updates:
        raise ValueError("No explicitly identified example artifacts")
    # Validate all entries before updating either example's download links.
    result = [updates.pop(entry["id"], entry) for entry in catalog]
    result.extend(updates.values())
    catalog_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    pin_release(json.loads(args.manifest.read_text()))
    print("Explicit example project and reader checksums pinned.")


if __name__ == "__main__":
    main()
