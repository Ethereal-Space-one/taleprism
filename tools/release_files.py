"""Explicit public source inventory; local history and runtime data stay on disk."""

import json
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = "tools/public-source.json"
TREES = (
    "backend",
    "frontend",
    "tools",
    "prompts",
    "schemas",
    "examples",
    ".github",
    "samples",
)
SKIP = {
    ".venv",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
}
ROOT_FILES = (
    "README.md",
    "README.en.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    ".gitignore",
    ".env.example",
    "start.sh",
    "run.sh",
    "打开Taleprism.command",
    "停止Taleprism.command",
    "打开原页.command",
    "停止原页.command",
    "engine/README.md",
    "engine/LICENSE-MPL-2.0.txt",
    "docs/快速上手.md",
    "docs/ARCHITECTURE.md",
    "docs/人物视觉导演标准.md",
    "docs/使用与恢复指南.md",
    "docs/COMPATIBILITY.md",
    "docs/RELEASING.md",
    "docs/RELEASE-v0.1.0.md",
    "docs/VALIDATION-v0.1.0.md",
    "docs/RELEASE-v0.2.0.md",
    "docs/VALIDATION-v0.2.0.md",
    "docs/Taleprism-v0.2.0-发布计划.md",
)


def allowed(name):
    if not isinstance(name, str) or not name or "\\" in name:
        return False
    rel = PurePosixPath(name)
    if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != name:
        return False
    if name not in ROOT_FILES and rel.parts[0] not in TREES:
        return False
    if any(part in SKIP for part in rel.parts) or rel.name == ".DS_Store":
        return False
    if any(p.startswith(".env") and name != ".env.example" for p in rel.parts):
        return False
    if rel.suffix.lower() in {".pyc", ".tsbuildinfo", ".zip", ".wav", ".mp3", ".aiff"}:
        return False
    if rel.name.endswith(".build.json"):
        return False
    return not (
        rel.parts[0] == "samples"
        and rel.suffix.lower() == ".png"
        and rel.parts[1] != "last-light"
    )


def source_files(root=None):
    """Read an explicit inventory; untracked files are never discovered by walking folders."""
    root = Path(root or ROOT).resolve()
    manifest = root / INVENTORY
    if not manifest.is_file():
        raise ValueError(
            "Missing public source inventory; maintainers must refresh it from Git."
        )
    names = json.loads(manifest.read_text())
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValueError("Invalid public source inventory")
    if names != sorted(set(names)):
        raise ValueError("Public source inventory must be unique and sorted")
    selected = []
    for name in names:
        if not allowed(name):
            raise ValueError("Disallowed public source: " + name)
        path = root / name
        if not path.is_file() or any(
            p.is_symlink() for p in [path, *path.parents] if p != root
        ):
            raise ValueError("Missing or linked public source: " + name)
        selected.append((name, path))
    return selected


def tracked_inventory(root=None):
    root = Path(root or ROOT).resolve()
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached"], cwd=root, check=True, capture_output=True
    )
    return sorted(
        {n for n in result.stdout.decode().split("\0") if allowed(n)} | {INVENTORY}
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--null",
        action="store_true",
        help="NUL-separated paths for git add --pathspec-from-file",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Review and stage files first, then record the Git inventory",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check inventory against tracked public source",
    )
    args = parser.parse_args()
    if args.refresh:
        (ROOT / INVENTORY).write_text(
            json.dumps(tracked_inventory(), ensure_ascii=False, indent=2) + "\n"
        )
    if args.check and [name for name, _ in source_files()] != tracked_inventory():
        raise SystemExit(
            "Public source inventory is stale; stage intended files and run --refresh."
        )
    names = [name for name, _ in source_files()]
    if args.check or args.refresh:
        print(f"Public source inventory verified: {len(names)} files.")
    else:
        print(
            ("\0" if args.null else "\n").join(names), end="\0" if args.null else "\n"
        )
