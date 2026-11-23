"""Make four portable distribution candidates, offline. Never tag, publish or replace a release.

Usage: python3 tools/build_distribution_candidate.py --inputs V092_FILES --output NEW_DIR
Inputs are the four named classic assets from the official v0.9.2 release (or
byte-identical rebuilds). Its historical build/finalize procedure is independent.
Requires Python 3.11+ and a clean Git checkout with an up-to-date public inventory.
"""

import argparse
import hashlib
import io
import json
import ntpath
import os
import stat
import subprocess
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from build_release import starter_entries
from chibi_source import LIMIT, read_zip, verify_inventory
from package_source import EPOCH, document, package_source
from package_source import MANIFEST as SOURCE_MANIFEST
from release_files import ROOT, source_files, tracked_inventory
from release_version import FROZEN_BOOK_PREFIX, FROZEN_BOOK_TAG, VERSION

BASE = f"https://github.com/Ethereal-Space-one/taleprism/releases/download/{FROZEN_BOOK_TAG}"
# SHA256SUMS, v0.9.2. Never trust checksums supplied by --inputs or by a new catalog.
PINS = {
    "chibi": {
        "reader": "9a539fd9c444772a20417c0c5c4de2e591785db16ed1a7de036035c46f52d891",
        "project": "49514698704b2785edf51169080195c5d658bad60065abe9e7353e78a48186ca",
    },
    "last-light": {
        "reader": "4c885d469f3163d3d1e064b7e024875b51d5fb7764cefda2e049238e09e736dc",
        "project": "64fdc898fd955c27f1ab1f602f63b773f1300c98c148bebb87330428f914f882",
    },
}
TITLES = {"chibi": "赤壁 / Chibi", "last-light": "末班灯 / Last Light"}
STARTER = "taleprism-agent-starter.zip"
SOURCE = "taleprism-workbench-source.zip"
MANIFEST = "candidate-manifest.json"
SUMS = "SHA256SUMS"
STARTER_README = """# Taleprism · Agent 创作入门包 / Agent starter

有自己的一章小说？从[用自己的小说开始](prompts/START-HERE.md#中文手顺)复制第一条指令。
让 Agent 先给你一页镜头计划，等你确认再做图。不用先安装制作台、插件或配置 Taleprism 密钥。

Have a chapter of your own? Follow [Bring your own novel](prompts/START-HERE.md#english-walkthrough)
and copy the first prompt. Review the shot plan before making images. The first step
does not require a workbench, plugin installation or Taleprism model key.

[八套模板 / Eight templates](prompts/README.md) · [三镜头实例 / Three-shot tutorial](examples/last-light/README.en.md)
· [作品与下载 / Works and downloads](docs/DOWNLOADS.md)

此包只有模板、结构定义与公开教程，不含可运行制作台或完整小说读本。源码请使用配套的
`taleprism-workbench-source.zip`。软件许可与素材来源请分别查看 LICENSE、THIRD_PARTY_NOTICES.md 和各示例的说明。
For code links or the local workbench, use the matching source ZIP. The software license does
not replace the source and artwork notices in the examples. Share only material you have permission to use.
"""


def work_name(slug):
    return f"taleprism-{slug}-work.zip"


def work_readme(slug):
    return f"""# {TITLES[slug]}

**阅读：** 完整解压作品包，打开 [Reader/index.html](Reader/index.html)。无需安装制作台或 AI 服务。
保留整个 `Reader/` 文件夹，网页、插图、声音、原文和许可说明须放在一起。

**接着改：** 打开本地 Taleprism 制作台，展开「手动导入与原文练习」，在「示例与工程」中
选「导入可编辑工程」，选择同包的 `Project.zip`。不要解压它，不要导入外层作品包。
导入会创建新项目；修改后可预览并导出新的独立读本。

**Read:** Extract this entire work bundle, then open [Reader/index.html](Reader/index.html)
in your browser. Keep the complete Reader folder together. No workbench or AI service is required.

**Edit:** In the local Taleprism workbench, expand “手动导入与原文练习” (manual import),
then in “示例与工程” choose “导入可编辑工程” (import editable project). Select the enclosed
`Project.zip`, still zipped, not the outer work bundle. The import creates a new project.

两份内容均来自同一 [v0.9.2 发布](https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.9.2)，
本次仅调整打包方式。The reader files and editable archive are unchanged. Original source, artwork
and software notices travel with these files; see [Reader/RIGHTS.txt](Reader/RIGHTS.txt) and `Reader/licenses/`.
""".encode()


def checked_input(folder, slug, kind):
    name = f"{FROZEN_BOOK_PREFIX}-{slug}-{kind}.zip"
    path = folder / name
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= LIMIT:
        raise ValueError("Missing, linked or oversized official input: " + name)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) > LIMIT or digest != PINS[slug][kind]:
        raise ValueError("Input does not match v0.9.2 SHA-256: " + name)
    return raw, {"file": name, "url": f"{BASE}/{name}", "sha256": digest}


def windows_reserved(part):
    # The ZIP must also be safe to extract on Windows, even when built on macOS
    # or Linux. ntpath.isreserved arrived in 3.13; pathlib's method is gone in 3.15.
    check = getattr(ntpath, "isreserved", None)
    if check is not None:
        return check(part)
    return PureWindowsPath(part).is_reserved()


def safe_files(raw):
    """Do not extract input files. Reject names/aliases that are unsafe on other OSes."""
    files = read_zip(raw)  # limits, CRCs, traversal, duplicates, symlinks, encryption
    aliases = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for info in z.infolist():
            parts = PurePosixPath(info.filename).parts
            file_type = stat.S_IFMT(info.external_attr >> 16)
            if (
                info.orig_filename != info.filename
                or file_type not in (0, stat.S_IFREG)
                or not parts
                or any(
                    any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                    or part.endswith((" ", "."))
                    or windows_reserved(part)
                    for part in parts
                )
            ):
                raise ValueError("Unsafe member in official reader: " + info.filename)
            # Guard file/directory conflicts and case-insensitive / Unicode aliases.
            for i in range(1, len(parts) + 1):
                name = "/".join(parts[:i])
                key = unicodedata.normalize("NFC", name).casefold()
                member = (name, i == len(parts))
                if aliases.setdefault(key, member) != member:
                    raise ValueError("Conflicting reader member: " + name)
    return files


def write_zip(path, files):
    # STORED avoids zlib/platform drift and recompression of project ZIPs and PNGs.
    # Same executable-mode convention as the pinned v0.9.2 readers and starter.
    with zipfile.ZipFile(path, "x") as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, EPOCH)
            info.create_system = 3
            info.external_attr = (
                stat.S_IFREG | (0o755 if name.endswith(".command") else 0o644)
            ) << 16
            z.writestr(info, data, compress_type=zipfile.ZIP_STORED)


def work_files(slug, reader, project):
    files = safe_files(reader)
    verify_inventory(files)  # all file contents and original license inventory
    for key in (
        "index.html",
        "reader.json",
        "RIGHTS.txt",
        "licenses/Taleprism-MIT.txt",
    ):
        if not files.get(key):
            raise ValueError("Incomplete reader: " + key)
    return {
        **{"Reader/" + name: raw for name, raw in files.items()},
        "Project.zip": project,
        "README.md": work_readme(slug),
    }


def verify_members(archive, expected, executable_suffixes):
    """Check exact names, modes and bytes, not a digest of a possibly wrong wrapper."""
    names = archive.namelist()
    if len(names) != len(expected) or set(names) != set(expected):
        raise ValueError(
            "ZIP is missing files or contains unexpected members: "
            + str(archive.filename)
        )
    for info in archive.infolist():
        name = info.filename
        mode = stat.S_IFREG | (0o755 if name.endswith(executable_suffixes) else 0o644)
        if info.external_attr >> 16 != mode or info.file_size > LIMIT:
            raise ValueError("Unexpected ZIP member mode or size: " + name)
        with archive.open(info) as member:
            if hashlib.file_digest(member, "sha256").hexdigest() != expected[name]:
                raise ValueError("ZIP member differs from expected content: " + name)


def verify_work_zip(path, slug, pinned_reader, project_sha256):
    # Hash the official input archive directly, independently of the wrapper's assembly.
    expected = {
        "Project.zip": project_sha256,
        "README.md": hashlib.sha256(work_readme(slug)).hexdigest(),
    }
    with zipfile.ZipFile(io.BytesIO(pinned_reader)) as ref:
        for info in ref.infolist():
            with ref.open(info) as original:
                expected["Reader/" + info.filename] = hashlib.file_digest(
                    original, "sha256"
                ).hexdigest()
    with zipfile.ZipFile(path) as archive:
        verify_members(archive, expected, (".command",))


def verify_source_zip(path, selected):
    inventory = {name: hash_file(source) for name, source in selected}
    manifest = "taleprism/" + SOURCE_MANIFEST
    with zipfile.ZipFile(path) as archive:
        if (
            manifest not in archive.namelist()
            or archive.getinfo(manifest).file_size > 4_000_000
        ):
            raise ValueError("Missing/oversized source manifest")
        raw = archive.read(manifest)
        doc = json.loads(raw)
        if (
            doc.get("format") != "storygal-source"
            or doc.get("version") != 1
            or doc.get("files") != inventory
        ):
            raise ValueError(
                "Source manifest differs from the reviewed source inventory"
            )
        expected = {"taleprism/" + name: sha for name, sha in inventory.items()}
        expected[manifest] = hashlib.sha256(raw).hexdigest()
        verify_members(archive, expected, (".command", ".sh"))


def hash_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_commit():
    # Existing source builder reads current files. Do not attribute a dirty or
    # incomplete inventory to HEAD. Untracked private artifacts are never scanned.
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT
    ):
        raise ValueError("Commit tracked changes before building the candidate.")
    names = [n for n, _ in source_files()]
    if names != tracked_inventory() or not {
        "tools/build_distribution_candidate.py",
        "tools/test_distribution_candidate.py",
        "docs/DOWNLOADS.md",
        "prompts/START-HERE.md",
    }.issubset(names):
        raise ValueError("Refresh and commit the complete public source inventory.")
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def build(inputs, output):
    inputs, output = Path(inputs).resolve(), Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError(
            "Use a new output directory; existing artifacts are never replaced."
        )
    commit = source_commit()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".taleprism-candidate-", dir=output.parent
    ) as t:
        out = Path(t) / "candidate"
        out.mkdir()
        files = starter_entries()
        files["taleprism/README.md"] = STARTER_README.encode()
        files["taleprism/README.en.md"] = STARTER_README.encode()
        files["taleprism/docs/DOWNLOADS.md"] = (ROOT / "docs/DOWNLOADS.md").read_bytes()
        if "taleprism/prompts/START-HERE.md" not in files:
            raise ValueError("Agent walkthrough missing from starter inventory")
        write_zip(out / STARTER, files)
        with zipfile.ZipFile(out / STARTER) as archive:
            verify_members(
                archive,
                {n: hashlib.sha256(b).hexdigest() for n, b in files.items()},
                (".command",),
            )
        del files
        inputs_by_work = {}
        for slug in PINS:
            reader, r = checked_input(inputs, slug, "reader")
            project, p = checked_input(inputs, slug, "project")
            write_zip(out / work_name(slug), work_files(slug, reader, project))
            verify_work_zip(out / work_name(slug), slug, reader, p["sha256"])
            inputs_by_work[slug] = {"reader": r, "project": p}
            del reader, project
        package_source(out / SOURCE)
        verify_source_zip(out / SOURCE, source_files())
        (out / SOURCE).with_suffix(
            ".json"
        ).unlink()  # candidate has one shared manifest
        artifacts = []
        for name, role in [
            (STARTER, "agent-starter"),
            *((work_name(slug), "work") for slug in PINS),
            (SOURCE, "workbench-source"),
        ]:
            path = out / name
            artifacts.append(
                {
                    "file": name,
                    "kind": role,
                    "bytes": path.stat().st_size,
                    "sha256": hash_file(path),
                }
            )
        (out / MANIFEST).write_bytes(
            document(
                {
                    "schema": 1,
                    "product": "Taleprism",
                    "version": VERSION,
                    "channel": "local-distribution-candidate",
                    "commit": commit,
                    "artifacts": artifacts,
                    "work_inputs": {"tag": FROZEN_BOOK_TAG, "works": inputs_by_work},
                    "historical_reader_only": [
                        {
                            "id": slug,
                            "url": f"{BASE}/{FROZEN_BOOK_PREFIX}-{slug}-reader.zip",
                        }
                        for slug in ("the-door-left-open", "the-margin")
                    ],
                }
            )
        )
        sums = "".join(a["sha256"] + "  " + a["file"] + "\n" for a in artifacts)
        (out / SUMS).write_bytes(
            (sums + hash_file(out / MANIFEST) + "  " + MANIFEST + "\n").encode()
        )
        if source_commit() != commit:
            raise ValueError("Source changed during candidate build.")
        os.rename(
            out, output
        )  # complete directory appears at once; no writes to inputs
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inputs",
        required=True,
        type=Path,
        help="Directory holding four pinned v0.9.2 inputs.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="New (nonexistent) candidate directory.",
    )
    args = parser.parse_args()
    print(build(args.inputs, args.output))
