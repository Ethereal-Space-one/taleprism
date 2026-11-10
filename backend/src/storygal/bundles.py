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


class Bundles:
    def __init__(self, app):
        self.app, self.store = app, app.state.store

    def export(self, pid):
        a = self.app.state
        a.review.ensure(pid)
        for component in [a.reader, a.speech, a.visual, a.production]:
            component.load(pid)
        self.store.verify(pid)
        files = {}
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
        for name in ["original.txt", "source.utf8.txt"]:
            files[name] = (self.store.project_dir(pid) / name).read_bytes()
        for table, (directory, ext) in MEDIA.items():
            for asset in rows[table]:
                relative = directory + "/" + asset["id"] + ext
                files[relative] = (self.store.project_dir(pid) / relative).read_bytes()
                if sha256(files[relative]) != asset["sha256"]:
                    raise ValueError("工程图片或声音已损坏，请先修复再打包。")
                if table == "visual_assets" and asset.get("svg_sha256"):
                    relative = directory + "/" + asset["id"] + ".svg"
                    files[relative] = (self.store.project_dir(pid) / relative).read_bytes()
                    if sha256(files[relative]) != asset["svg_sha256"]:
                        raise ValueError("图解源文件校验失败。")
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
        files["project.json"] = encoded(document)
        files["README.txt"] = (
            "Taleprism 可编辑工程。请在制作台导入工程包，不要手动运行包内文件。包含原文、制作状态与媒体；不含密钥、模型缓存、工作日志或个人阅读进度。\n".encode()
        )
        files["manifest.json"] = encoded(
            {
                "format": "storygal-project-inventory",
                "version": 1,
                "files": {name: sha256(raw) for name, raw in files.items()},
            }
        )
        if sum(map(len, files.values())) > LIMIT:
            raise ValueError("工程超过160MB，请减少未用素材后再导出。")
        with self.store.db() as db:
            current = {
                t: db.execute(f"SELECT revision FROM {t} WHERE project_id=?", (pid,)).fetchone()[0]
                for t in STATE_TABLES
            }
            current_review = db.execute(
                "SELECT revision FROM review_states WHERE project_id=?", (pid,)
            ).fetchone()[0]
        if current_review != review_revision or any(
            current[t] != states[t]["revision"] for t in STATE_TABLES
        ):
            raise ValueError("打包期间工程发生修改，请重试。")
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for name, raw in files.items():
                z.writestr(name, raw)
        return out.getvalue()

    def inspect(self, raw):
        if len(raw) > LIMIT:
            raise ValueError("工程包超过160MB。")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                infos = z.infolist()
                names = [i.filename for i in infos]
                if (
                    len(infos) > 3000
                    or len(set(names)) != len(names)
                    or sum(i.file_size for i in infos) > LIMIT
                ):
                    raise ValueError("工程包文件重复或解压大小超过限制。")
                if any(
                    i.is_dir()
                    or not re.fullmatch(r"(?:[a-z0-9-]+/)?[a-zA-Z0-9_.-]+", i.filename)
                    or ".." in i.filename
                    or (i.external_attr >> 16) & 0o170000 == 0o120000
                    for i in infos
                ):
                    raise ValueError("工程包包含不允许的路径或链接。")
                if any(
                    i.filename in {"manifest.json", "project.json"} and i.file_size > 5_000_000
                    for i in infos
                ):
                    raise ValueError("工程清单过大。")
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
            allowed = {"original.txt", "source.utf8.txt", "project.json", "README.txt"}
            for table, records in doc["records"].items():
                if (
                    not isinstance(records, list)
                    or len(records) > 5000
                    or len({r["id"] for r in records}) != len(records)
                ):
                    raise ValueError("工程记录重复或超出限制。")
                for row in records:
                    if not ID.fullmatch(row["id"]) or not set(row) <= set(FIELDS[table].split()):
                        raise ValueError("工程记录编号或字段无效。")
                    if table in MEDIA:
                        directory, ext = MEDIA[table]
                        name = directory + "/" + row["id"] + ext
                        allowed.add(name)
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
            UnicodeDecodeError,
            ElementTree.ParseError,
            OSError,
        ) as exc:
            raise ValueError("工程包结构或素材损坏，未导入任何项目。") from exc

    def import_project(self, raw):
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
