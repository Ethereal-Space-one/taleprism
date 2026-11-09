"""Verify an extracted Storygal delivery using only the Python standard library."""

import hashlib
import json
import sys
from pathlib import Path, PurePosixPath


def verify(root: Path) -> dict:
    root = root.resolve()
    inventory = json.loads((root / "storygal-delivery.json").read_text(encoding="utf-8"))
    expected = inventory["files"]
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("工程中存在符号链接：" + str(path.relative_to(root)))
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != set(expected) | {"storygal-delivery.json"}:
        raise ValueError("工程文件缺失或出现清单外文件。")
    for name, entry in expected.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise ValueError("清单路径无效。")
        content = (root / name).read_bytes()
        if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError("文件校验失败：" + name)
    return {"passed": True, "files": len(expected), "export_id": inventory["export_id"]}


if __name__ == "__main__":
    try:
        result = verify(Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).parent)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("工程检查未通过：" + str(exc), file=sys.stderr)
        sys.exit(1)
