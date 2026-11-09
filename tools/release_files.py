"""Explicit public source inventory; local history and runtime data stay on disk."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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
)


def source_files():
    paths = [ROOT / p for p in ROOT_FILES]
    for tree in TREES:
        paths.extend(p for p in (ROOT / tree).rglob("*") if p.is_file())
    selected = []
    for p in sorted(set(paths)):
        rel = p.relative_to(ROOT)
        if any(part in SKIP for part in rel.parts) or p.name == ".DS_Store":
            continue
        if p.suffix in {
            ".pyc",
            ".tsbuildinfo",
            ".zip",
            ".wav",
            ".mp3",
            ".aiff",
        } or p.name.endswith(".build.json"):
            continue
        if (
            rel.parts[0] == "samples"
            and p.suffix.lower() == ".png"
            and rel.parts[1] != "last-light"
        ):
            continue
        if p.is_symlink() or not p.is_file():
            raise ValueError(f"Invalid public source: {rel}")
        if p.name.startswith(".env") and p.name != ".env.example":
            raise ValueError(f"Environment file in public source: {rel}")
        selected.append((rel.as_posix(), p))
    return selected


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--null",
        action="store_true",
        help="NUL-separated paths for git add --pathspec-from-file",
    )
    args = parser.parse_args()
    names = [name for name, _ in source_files()]
    print(("\0" if args.null else "\n").join(names), end="\0" if args.null else "\n")
