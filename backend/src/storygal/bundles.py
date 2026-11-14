"""Portable editable projects. Fixed records, bounded ZIPs, staged validation, atomic publish."""

import io
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated
from xml.etree import ElementTree

from fastapi import File, UploadFile
from fastapi.responses import Response
from PIL import Image

from .character_identity import resolved_character_id
from .reader import REPO
from .reader_api import Configuration
from .review import top_dialogues
from .speech import inspect_audio
from .speech_api import Line
from .speech_models import StoredProfile, validate_take_profile
from .text import sha256

LIMIT = 160_000_000
MEMBER_LIMIT = 3000
JSON_LIMIT = 5_000_000
ROW_LIMIT = 5000
ROW_TABLES = ("characters", "dialogues", "assets", "reader_assets", "speech_takes", "visual_assets")
STATE_TABLES = ("reader_states", "speech_states", "visual_states", "production_states")
MEDIA = {
    "assets": ("assets", ".png"),
    "reader_assets": ("reader-assets", ".png"),
    "speech_takes": ("audio", ".wav"),
    "visual_assets": ("visual", ".png"),
}
ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
FIELDS = {
    "characters": "id display_name aliases description evidence status active_figure_id origin merged_into",
    "dialogues": "id byte_start byte_end outer_start outer_end text label attribution speaker_id suggested_speaker_id status confidence evidence reviewer reviewed_at origin",
    "assets": "id character_id kind status sha256 width height license origin created_at label sample_key portrait_state",
    "reader_assets": "id kind status sha256 width height license origin created_at label sample_key",
    "speech_takes": "id cache_key sha256 duration created_at profile provider model text_sha256 imported",
    "visual_assets": "id sha256 svg_sha256 config_hash license origin",
}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode()


def limit_errors(sizes, records=None):
    """One set of format bounds for the exporter, preflight and ZIP reader."""
    errors = []
    if len(sizes) > MEMBER_LIMIT:
        errors.append(f"工程包含 {len(sizes)} 个文件，超过 {MEMBER_LIMIT} 个文件限制。")
    total = sum(sizes.values())
    if total > LIMIT:
        errors.append(f"工程解压后共 {total:,} 字节，超过 {LIMIT:,} 字节（160MB）限制。")
    for name in ("project.json", "manifest.json"):
        if sizes.get(name, 0) > JSON_LIMIT:
            errors.append(f"{name} 为 {sizes[name]:,} 字节，超过 {JSON_LIMIT:,} 字节 JSON 限制。")
    for table, rows in (records or {}).items():
        if len(rows) > ROW_LIMIT:
            errors.append(f"{table} 有 {len(rows)} 条记录，超过每表 {ROW_LIMIT} 条限制。")
    return errors


class Bundles:
    def __init__(self, app):
        self.app, self.store = app, app.state.store

    def snapshot(self, pid):
        a = self.app.state
        a.review.ensure(pid)
        for component in [a.reader, a.speech, a.visual, a.production]:
            component.load(pid)
        self.store.verify(pid)
        with self.store.db() as db:
            db.execute("BEGIN")
            meta = self.store.get(pid)
            rows = {
                t: [
                    {k: v for k, v in r.items() if k in FIELDS[t].split()}
                    for r in a.review.rows(db, t, pid)
                ]
                for t in ROW_TABLES
            }
            states = {
                t: dict(
                    db.execute(
                        f"SELECT revision,data FROM {t} WHERE project_id=?", (pid,)
                    ).fetchone()
                )
                for t in STATE_TABLES
            }
            for s in states.values():
                s["data"] = json.loads(s["data"])
            review_revision = db.execute(
                "SELECT revision FROM review_states WHERE project_id=?", (pid,)
            ).fetchone()[0]
        document = {
            "format": "storygal-project",
            "version": 2,
            "project": {
                k: meta[k]
                for k in ["filename", "encoding", "rights_status", "sha256", "canonical_sha256"]
            },
            "review_revision": review_revision,
            "records": rows,
            "states": states,
            "review_note": "素材接受与方案确认是原工程制作记录；本包不包含接收者或发布者最终复核。",
        }
        return document

    def inventory(self, pid, document):
        """Stat all recorded media, including old/unselected takes; never silently omit any."""
        files = {"project.json": encoded(document)}
        files["README.txt"] = (
            "Taleprism 可编辑工程。请在制作台导入工程包，不要手动运行包内文件。包含原文、制作状态与媒体；不含密钥、模型缓存、工作日志或个人阅读进度。\n".encode()
        )
        paths = {name: None for name in ("original.txt", "source.utf8.txt")}
        for table, (directory, ext) in MEDIA.items():
            for asset in document["records"][table]:
                paths[f"{directory}/{asset['id']}{ext}"] = asset["sha256"]
                if table == "visual_assets" and asset.get("svg_sha256"):
                    paths[f"{directory}/{asset['id']}.svg"] = asset["svg_sha256"]
        missing = []
        sizes = {name: len(raw) for name, raw in files.items()}
        for name in paths:
            try:
                sizes[name] = (self.store.project_dir(pid) / name).stat().st_size
            except FileNotFoundError:
                missing.append(name)
                sizes[name] = 0
        # Every digest has the same encoded length; preflight needn't load large media.
        manifest = encoded(
            {
                "format": "storygal-project-inventory",
                "version": 1,
                "files": {name: "0" * 64 for name in [*files, *paths]},
            }
        )
        sizes["manifest.json"] = len(manifest)
        return files, paths, sizes, missing

    def preflight(self, pid):
        document = self.snapshot(pid)
        _, paths, sizes, missing = self.inventory(pid, document)
        errors = limit_errors(sizes, document["records"])
        if missing:
            errors.append(f"有 {len(missing)} 个已记录文件缺失，不能生成完整工程备份。")
        media = [{"path": name, "bytes": sizes[name]} for name in paths if "/" in name]
        return {
            "can_export": not errors,
            "validation": "size_and_presence_only",
            "note": "预检只检查大小、数量与文件存在；导出时还会校验哈希、素材与可恢复结构。ZIP 包本身也须不超过160MB。不会跳过旧素材或自动删除文件。",
            "limits": {
                "archive_bytes": LIMIT,
                "uncompressed_bytes": LIMIT,
                "members": MEMBER_LIMIT,
                "json_bytes": JSON_LIMIT,
                "rows_per_table": ROW_LIMIT,
            },
            "uncompressed_bytes": sum(sizes.values()),
            "members": len(sizes),
            "json_bytes": {name: sizes[name] for name in ("project.json", "manifest.json")},
            "rows": {table: len(rows) for table, rows in document["records"].items()},
            "media_bytes": sum(item["bytes"] for item in media),
            "media_files": len(media),
            "largest_media": sorted(media, key=lambda item: item["bytes"], reverse=True)[:10],
            "missing_files": missing,
            "errors": errors,
        }

    def export(self, pid):
        document = self.snapshot(pid)
        files, paths, sizes, missing = self.inventory(pid, document)
        errors = limit_errors(sizes, document["records"])
        if missing:
            errors.append("已记录文件缺失：" + "、".join(missing[:5]))
        if errors:
            raise ValueError(
                "不能导出完整可编辑工程："
                + " ".join(errors)
                + " 不会跳过素材；请停止工作台后复制完整数据目录作为备份。"
            )
        for name, expected_hash in paths.items():
            try:
                files[name] = (self.store.project_dir(pid) / name).read_bytes()
            except FileNotFoundError as exc:
                raise ValueError(f"工程文件缺失：{name}；未导出不完整备份。") from exc
            if expected_hash and sha256(files[name]) != expected_hash:
                raise ValueError(f"工程素材哈希校验失败：{name}；未导出不完整备份。")
        files["manifest.json"] = encoded(
            {
                "format": "storygal-project-inventory",
                "version": 1,
                "files": {name: sha256(raw) for name, raw in files.items()},
            }
        )
        errors = limit_errors({name: len(raw) for name, raw in files.items()}, document["records"])
        if errors:
            raise ValueError("不能导出完整可编辑工程：" + " ".join(errors))
        with self.store.db() as db:
            current = {
                t: db.execute(f"SELECT revision FROM {t} WHERE project_id=?", (pid,)).fetchone()[0]
                for t in STATE_TABLES
            }
            current_review = db.execute(
                "SELECT revision FROM review_states WHERE project_id=?", (pid,)
            ).fetchone()[0]
        if current_review != document["review_revision"] or any(
            current[t] != document["states"][t]["revision"] for t in STATE_TABLES
        ):
            raise ValueError("打包期间工程发生修改，请重试。")
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for name, raw in files.items():
                z.writestr(name, raw)
        raw = out.getvalue()
        # Use the actual restore path, including media and structural validation,
        # before advertising a ZIP as an editable backup. Nothing is published.
        try:
            self.import_project(raw, validate_only=True)
        except ValueError as exc:
            raise ValueError(f"工程无法通过恢复校验，未导出备份：{exc}") from exc
        return raw

    def inspect(self, raw):
        if len(raw) > LIMIT:
            raise ValueError("工程包超过160MB。")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                infos = z.infolist()
                names = [i.filename for i in infos]
                if len(set(names)) != len(names):
                    raise ValueError("工程包包含重复文件。")
                errors = limit_errors({i.filename: i.file_size for i in infos})
                if errors:
                    raise ValueError(" ".join(errors))
                if any(
                    i.is_dir()
                    or not re.fullmatch(r"(?:[a-z0-9-]+/)?[a-zA-Z0-9_.-]+", i.filename)
                    or ".." in i.filename
                    or (i.external_attr >> 16) & 0o170000 == 0o120000
                    for i in infos
                ):
                    raise ValueError("工程包包含不允许的路径或链接。")
                if any(i.flag_bits & 1 for i in infos):
                    raise ValueError("不支持加密工程包，请使用未加密的可编辑工程 ZIP。")
                files = {name: z.read(name) for name in names}
            manifest = json.loads(files.pop("manifest.json"))
            if (
                manifest.get("format") != "storygal-project-inventory"
                or manifest.get("version") != 1
                or set(manifest["files"]) != set(files)
            ):
                raise ValueError("工程清单版本或文件集合不匹配。")
            if any(sha256(data) != manifest["files"][name] for name, data in files.items()):
                raise ValueError("工程包哈希校验失败。")
            doc = json.loads(files["project.json"])
            if doc.get("format") != "storygal-project" or doc.get("version") not in {1, 2}:
                raise ValueError("不支持此工程包版本。")
            if set(doc) != {
                "format",
                "version",
                "project",
                "review_revision",
                "records",
                "states",
                "review_note",
            }:
                raise ValueError("工程包包含未知字段。")
            if set(doc["records"]) != set(ROW_TABLES) or set(doc["states"]) != set(STATE_TABLES):
                raise ValueError("工程包记录类型不匹配。")
            if any(not isinstance(rows, list) for rows in doc["records"].values()):
                raise ValueError("工程记录类型无效。")
            errors = limit_errors({}, doc["records"])
            if errors:
                raise ValueError(" ".join(errors))
            allowed = {"original.txt", "source.utf8.txt", "project.json", "README.txt"}
            for table, records in doc["records"].items():
                if len({r["id"] for r in records}) != len(records):
                    raise ValueError("工程记录重复或超出限制。")
                for row in records:
                    if not ID.fullmatch(row["id"]) or not set(row) <= set(FIELDS[table].split()):
                        raise ValueError("工程记录编号或字段无效。")
                    if table in MEDIA:
                        directory, ext = MEDIA[table]
                        name = directory + "/" + row["id"] + ext
                        allowed.add(name)
                        if name not in files:
                            raise ValueError(f"工程包缺少已记录素材：{name}。")
                        media = files[name]
                        if sha256(media) != row["sha256"]:
                            raise ValueError("素材记录与文件不匹配。")
                        if ext == ".png":
                            with Image.open(io.BytesIO(media)) as image:
                                if (
                                    image.format != "PNG"
                                    or max(image.size) > 8192
                                    or image.width * image.height > 24_000_000
                                ):
                                    raise ValueError("图片格式或大小无效。")
                                image.verify()
                        else:
                            inspect_audio(media)
                        if table == "visual_assets" and row.get("svg_sha256"):
                            name = directory + "/" + row["id"] + ".svg"
                            allowed.add(name)
                            if name not in files:
                                raise ValueError(f"工程包缺少图解源文件：{name}。")
                            if sha256(files[name]) != row["svg_sha256"]:
                                raise ValueError("图解源文件哈希不匹配。")
                            xml = ElementTree.fromstring(files[name])
                            for node in xml.iter():
                                if node.tag.split("}")[-1] not in {
                                    "svg",
                                    "rect",
                                    "text",
                                    "path",
                                    "circle",
                                    "ellipse",
                                    "line",
                                    "polyline",
                                    "polygon",
                                    "g",
                                } or any(
                                    k.lower().startswith("on") or "href" in k for k in node.attrib
                                ):
                                    raise ValueError("图解包含主动内容。")
            if set(files) != allowed:
                raise ValueError("工程包含清单之外的文件。")
            return doc, files
        except (
            KeyError,
            TypeError,
            AttributeError,
            zipfile.BadZipFile,
            NotImplementedError,
            RuntimeError,
            SyntaxError,
            UnicodeDecodeError,
            ElementTree.ParseError,
            OSError,
        ) as exc:
            raise ValueError("工程包结构或素材损坏，未导入任何项目。") from exc

    def import_project(self, raw, *, validate_only=False):
        doc, files = self.inspect(raw)
        from .app import create_app

        staging_root = self.store.root / ".imports"
        staging_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=staging_root) as temp:
            staged = create_app(Path(temp)).state
            try:
                meta = doc["project"]
                if set(meta) != {
                    "filename",
                    "encoding",
                    "rights_status",
                    "sha256",
                    "canonical_sha256",
                }:
                    raise ValueError("工程元数据字段无效。")
                project = staged.store.create(
                    files["original.txt"], meta["filename"], meta["rights_status"], meta["encoding"]
                )
                pid = project["id"]
                if (
                    project["sha256"] != meta["sha256"]
                    or project["canonical_sha256"] != meta["canonical_sha256"]
                    or (staged.store.project_dir(pid) / "source.utf8.txt").read_bytes()
                    != files["source.utf8.txt"]
                ):
                    raise ValueError("工程原文与工作副本不一致。")
                records = doc["records"]
                chars = {c["id"]: c for c in records["characters"]}
                assets = {a["id"]: a for a in records["assets"]}
                for c in chars.values():
                    resolved_character_id(chars, c["id"])
                    if (
                        not c["display_name"].strip()
                        or len(c["display_name"]) > 40
                        or c["status"] not in {"candidate", "confirmed", "merged", "rejected"}
                        or not isinstance(c["aliases"], list)
                    ):
                        raise ValueError("人物记录无效。")
                    aid = c["active_figure_id"]
                    if aid and (
                        aid not in assets
                        or assets[aid]["character_id"] != c["id"]
                        or assets[aid]["kind"] == "reference"
                    ):
                        raise ValueError("人物立绘引用无效。")
                for a in records["assets"]:
                    if (
                        a["character_id"] not in chars
                        or a["kind"] not in {"reference", "figure", "reference_and_figure"}
                        or a["status"] not in {"pending", "accepted", "rejected"}
                    ):
                        raise ValueError("角色素材引用无效。")
                for a in records["reader_assets"]:
                    if a["kind"] not in {"cover", "scene"} or a["status"] not in {
                        "pending",
                        "accepted",
                        "rejected",
                    }:
                        raise ValueError("阅读器素材类型无效。")
                expected = top_dialogues(files["source.utf8.txt"])
                dialogues = records["dialogues"]
                fields = ["byte_start", "byte_end", "outer_start", "outer_end", "text"]
                if sorted([tuple(d[k] for k in fields) for d in dialogues]) != sorted(
                    [tuple(d[k] for k in fields) for d in expected]
                ):
                    raise ValueError("对白与原文不一致。")
                for d in dialogues:
                    if d["status"] not in {"pending", "reviewed"} or any(
                        d[k] and d[k] not in chars for k in ["speaker_id", "suggested_speaker_id"]
                    ):
                        raise ValueError("对白归属无效。")
                speech = doc["states"]["speech_states"]["data"]
                if set(speech) != {"profiles", "lines"} or not set(speech["profiles"]) <= set(
                    chars
                ):
                    raise ValueError("配音角色配置无效。")
                for profile in speech["profiles"].values():
                    StoredProfile.model_validate(profile)
                takes = {t["id"]: t for t in records["speech_takes"]}
                for take in takes.values():
                    validate_take_profile(take)
                    if not re.fullmatch(r"[0-9a-f]{64}", take["cache_key"]) or not re.fullmatch(
                        r"[0-9a-f]{64}", take["text_sha256"]
                    ):
                        raise ValueError("音频缓存记录无效。")
                by_dialogue = {d["id"]: d for d in dialogues}
                for did, settings in speech["lines"].items():
                    if did not in by_dialogue or not set(settings) <= {
                        "selected",
                        "overrides",
                        "instructions",
                        "accepted",
                    }:
                        raise ValueError("配音对白记录无效。")
                    Line(revision=0, **{k: v for k, v in settings.items() if k != "accepted"})
                    for key, aid in settings.get("accepted", {}).items():
                        if aid not in takes or not re.fullmatch(r"\d+:\d+", key):
                            raise ValueError("已接受声音引用不存在。")
                        start, end = map(int, key.split(":"))
                        d = by_dialogue[did]
                        if not d["byte_start"] <= start < end <= d["byte_end"]:
                            raise ValueError("声音片段超出对白。")
                        spoken = settings.get("overrides", {}).get(
                            key, files["source.utf8.txt"][start:end].decode()
                        )
                        if takes[aid]["text_sha256"] != sha256(spoken.encode()):
                            raise ValueError("声音与读音文本不一致。")
                for name, data in files.items():
                    if "/" in name:
                        target = staged.store.project_dir(pid) / name
                        target.parent.mkdir(exist_ok=True)
                        target.write_bytes(data)
                        target.chmod(0o444)
                for take in records["speech_takes"]:
                    take["imported"] = True
                    take["url"] = f"/api/projects/{pid}/speech/takes/{take['id']}"
                with staged.store.db() as db:
                    db.execute(
                        "INSERT INTO review_states VALUES(?,?,NULL)", (pid, doc["review_revision"])
                    )
                    for table, rows in records.items():
                        for row in rows:
                            staged.review.put(db, table, pid, row)
                    for table, state in doc["states"].items():
                        if (
                            set(state) != {"revision", "data"}
                            or not isinstance(state["revision"], int)
                            or state["revision"] < 0
                        ):
                            raise ValueError("工程状态版本无效。")
                        db.execute(
                            f"INSERT INTO {table} VALUES(?,?,?)",
                            (pid, state["revision"], json.dumps(state["data"], ensure_ascii=False)),
                        )
                config = Configuration(
                    revision=0, **doc["states"]["reader_states"]["data"]
                ).model_dump(exclude={"revision"})
                staged.reader.validate(pid, config, for_restore=True)
                from .reader_presentation import validate

                validate(staged.reader, pid, config, for_restore=True)
                plan = doc["states"]["production_states"]["data"]
                staged.production.validate(pid, plan, for_restore=True)
                restore_issues = staged.reader.content(pid)["issues"]
                # Structural checks above must succeed before publication problems
                # may be presented as repairable warnings. Never rewrite approvals.
                for check in (
                    lambda: staged.reader.content(pid, strict=True),
                    lambda: staged.production.validate(pid, plan),
                ):
                    try:
                        check()
                    except ValueError as exc:
                        restore_issues.append(str(exc))
                for item in staged.visual.load(pid)[1]["items"]:
                    staged.visual.validate(pid, item)
                staged.store.verify(pid)
                if validate_only:
                    return {"restore_issues": sorted(set(restore_issues))}
                destination = self.store.project_dir(pid)
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged.store.project_dir(pid), destination)
                try:
                    with self.store.db() as target, staged.store.db() as source:
                        target.execute("BEGIN IMMEDIATE")
                        for table in (
                            "projects",
                            "spans",
                            "units",
                            "review_states",
                            *ROW_TABLES,
                            *STATE_TABLES,
                        ):
                            rows = source.execute(f"SELECT * FROM {table}").fetchall()
                            for row in rows:
                                target.execute(
                                    f"INSERT INTO {table} VALUES({','.join('?' for _ in row)})",
                                    tuple(row),
                                )
                        staged.review.audit(
                            target,
                            pid,
                            "project.import",
                            None,
                            {"source_sha256": project["sha256"], "format": 1},
                            actor="project-import",
                        )
                except Exception:
                    os.replace(destination, staged.store.project_dir(pid))
                    raise
                return project | {"restore_issues": sorted(set(restore_issues))}
            except (KeyError, TypeError, IndexError, AttributeError) as exc:
                raise ValueError("工程状态或引用不完整，未导入任何项目。") from exc


def mount_bundles(app):
    bundles = Bundles(app)
    app.state.bundles = bundles

    @app.get("/api/projects/{pid}/bundle/preflight")
    def preflight(pid: str):
        return bundles.preflight(pid)

    @app.get("/api/projects/{pid}/bundle")
    def export(pid: str):
        return Response(
            bundles.export(pid),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="taleprism-project.zip"'},
        )

    @app.post("/api/project-bundles", status_code=201)
    async def restore(file: Annotated[UploadFile, File()]):
        return bundles.import_project(await file.read(LIMIT + 1))

    @app.get("/api/content-packs")
    def packs():
        catalog = REPO / "samples/content-packs/catalog.json"
        specs = json.loads(catalog.read_text()) if catalog.exists() else []
        return [
            {**s, "available": (REPO / "samples/content-packs" / s["file"]).is_file()}
            for s in specs
            if s.get("download_url") or (REPO / "samples/content-packs" / s["file"]).is_file()
        ]

    @app.post("/api/content-packs/{key}", status_code=201)
    def install(key: str):
        spec = next((s for s in packs() if s["id"] == key), None)
        if not spec:
            raise ValueError("内容包不存在。")
        path = REPO / "samples/content-packs" / spec["file"]
        if not path.is_file():
            raise ValueError("本机尚未安装此内容包，请从示例下载入口获取，再导入可编辑工程。")
        raw = path.read_bytes()
        if spec.get("sha256") and sha256(raw) != spec["sha256"]:
            raise ValueError("内容包与当前版本的校验值不一致，请重新下载。")
        return bundles.import_project(raw)
