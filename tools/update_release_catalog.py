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
    catalog = [
        {
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
        },
        {
            "id": "chibi",
            "title": "赤壁 · 本机历史工程",
            "file": "chibi.storygal.zip",
            "description": "仅在保留旧内容包的本机出现；两幅心理表演修订图仍待审，保留原制作状态。",
        },
    ]
    (ROOT / "samples/content-packs/catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    )
    print("Candidate checksums pinned; historical local pack retained when present.")


if __name__ == "__main__":
    main()
