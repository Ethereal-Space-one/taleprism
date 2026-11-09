"""Pin the prepared candidate's exact project/reader checksums. Does not upload."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    release = json.loads(args.manifest.read_text())
    base = (
        "https://github.com/Ethereal-Space-one/taleprism/releases/download/v"
        + release["version"]
        + "/"
    )
    project = next(
        a for a in release["artifacts"] if a["file"].endswith("-project.zip")
    )
    reader = next(a for a in release["artifacts"] if a["file"].endswith("-reader.zip"))
    catalog_path = ROOT / "samples/content-packs/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    last_light = {
        "id": "last-light",
        "title": "末班灯 · 现代原创短篇",
        "description": "三位人物、两张立绘、三幅情境图；含母版、11件物品状态与助手检查。公开版不含系统演示音频。",
        "file": project["file"],
        "sha256": project["sha256"],
        "download_url": base + project["file"],
        "reader": {
            "file": reader["file"],
            "sha256": reader["sha256"],
            "url": base + reader["file"],
        },
    }
    catalog = [last_light] + [entry for entry in catalog if entry["id"] != "last-light"]
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    print("Last Light checksums pinned; other examples and reader pins preserved.")


if __name__ == "__main__":
    main()
