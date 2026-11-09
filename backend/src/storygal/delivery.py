"""Delivery readiness and explicit, export-scoped human review records."""

import json
import shutil

from .exporter import BUNDLE, BUNDLE_HASH, ENGINE, REPO
from .review import ConflictError
from .storage import now
from .text import sha256

REVIEW_CHECKS = {"source", "speakers", "audio", "visual", "end"}


class Delivery:
    def __init__(self, store, review, speech, visual, reader=None):
        self.store, self.review, self.speech, self.visual = store, review, speech, visual
        self.reader = reader
        with store.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS delivery_reviews(
                project_id TEXT, export_id TEXT, data TEXT NOT NULL,
                PRIMARY KEY(project_id,export_id))""")

    def versions(self, pid, reader=False):
        with self.store.db() as db:
            result = {}
            for table, key in [
                ("review_states", "review_revision"),
                ("speech_states", "speech_revision"),
                ("reader_states", "reader_revision")
                if reader
                else ("visual_states", "visual_revision"),
            ]:
                row = db.execute(
                    f"SELECT revision FROM {table} WHERE project_id=?", (pid,)
                ).fetchone()
                result[key] = row[0] if row else 0
            return result

    def completed(self, pid, eid):
        job = next((j for j in self.store.jobs(pid) if j["id"] == eid), None)
        if not job or job["kind"] not in {"export", "reader_export"} or job["state"] != "completed":
            raise KeyError()
        return job

    def state(self, pid):
        metadata = self.store.get(pid)
        jobs = self.store.jobs(pid)
        latest = next(
            (
                j
                for j in jobs
                if j["kind"] in {"export", "reader_export"} and j["state"] == "completed"
            ),
            None,
        )
        reader_export = bool(self.reader and (not latest or latest["kind"] == "reader_export"))
        checks, warnings = [], []

        def check(key, label, target, fn):
            try:
                detail = fn()
                checks.append(
                    {"id": key, "label": label, "target": target, "passed": True, "detail": detail}
                )
            except (ValueError, KeyError, OSError) as exc:
                # Known errors are actionable; filesystem exceptions should not expose local paths.
                detail = (
                    str(exc) if isinstance(exc, ValueError) else "素材缺失，请修复或停用后重试。"
                )
                checks.append(
                    {"id": key, "label": label, "target": target, "passed": False, "detail": detail}
                )

        check(
            "source",
            "原文保真",
            "text",
            lambda: self.store.verify(pid) and "原始字节、编码与分段通过校验。",
        )
        units, review = [], {"pending_count": 0}
        try:
            if checks[0]["passed"]:
                units, review = self.review.presentation(pid)
        except (ValueError, KeyError, OSError):
            checks.append(
                {
                    "id": "presentation",
                    "label": "人物与显示分段",
                    "target": "review",
                    "passed": False,
                    "detail": "人物标注或源文件无法读取，请检查人物审校。",
                }
            )

        def figures():
            if not units:
                raise ValueError("请先修复原文或人物标注，再检查素材。")
            ids = {u["figure_asset_id"] for u in units if u.get("figure_asset_id")}
            for aid in ids:
                self.review.asset_path(pid, aid)
            return f"本次使用 {len(ids)} 张已接受立绘。"

        def audio():
            if not units:
                raise ValueError("请先修复原文或人物标注，再检查配音。")
            _, takes = self.speech.for_export(pid, [dict(u) for u in units])
            return f"本次使用 {len(takes)} 个已接受语音片段。"

        def visual():
            if not units:
                raise ValueError("请先修复原文或人物标注，再检查图页。")
            _, events = self.visual.for_export(pid, units)
            return f"本次使用 {len(events)} 张已接受图页。"

        def engine():
            if not (ENGINE / "index.html").is_file() or not (ENGINE / BUNDLE).is_file():
                raise ValueError("缺少固定版本引擎，请重新运行启动程序。")
            if sha256((ENGINE / BUNDLE).read_bytes()) != BUNDLE_HASH:
                raise ValueError("引擎文件校验失败，请重新下载引擎。")
            if (
                not shutil.which("node")
                or not (REPO / "tools/webgal-verify/node_modules/webgal-parser").is_dir()
            ):
                raise ValueError("缺少导出检查工具，请重新运行启动程序。")
            return "固定引擎与导出检查工具已就绪。"

        check("figures", "人物立绘", "review", figures)
        check("audio", "已选配音", "speech", audio)

        def reader_build():
            if not (REPO / "frontend/dist/index.html").is_file():
                raise ValueError("请重新构建阅读器。")
            return "阅读器已构建。"

        if reader_export and self.reader:
            check(
                "reader",
                "阅读器封面与场景",
                "reader",
                lambda: (
                    self.reader.content(pid, strict=True)
                    and "封面、场景、人物和音频可用于当前阅读器。"
                ),
            )
            check(
                "engine",
                "阅读器构建",
                "delivery",
                reader_build,
            )
        else:
            check("visual", "已启用图页", "visual", visual)
            check("engine", "播放与打包工具", "delivery", engine)
        if review["pending_count"]:
            warnings.append(
                {
                    "target": "review",
                    "detail": f"仍有 {review['pending_count']} 句对白待审；未确认归属的对白不自动挂角色或配音。",
                }
            )
        if metadata["rights_status"] == "local_test":
            warnings.append(
                {
                    "target": "text",
                    "detail": "此项目标记为仅本地测试，分享前请核实原文及素材的使用范围。",
                }
            )
        if self.reader:
            editorial = self.reader.editorial.state(pid)
            for issue in editorial["issues"]:
                current = self.versions(pid, reader=True)
                if issue["state"] == "open" or issue.get("versions") != current:
                    warnings.append(
                        {
                            "target": "reader",
                            "detail": "制作意见待处理或内容已变需重新核对：" + issue["note"][:120],
                        }
                    )
        versions = self.versions(pid, reader=reader_export)
        with self.store.db() as db:
            records = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT data FROM delivery_reviews WHERE project_id=? ORDER BY rowid DESC",
                    (pid,),
                )
            ]
        return {
            "ready": all(c["passed"] for c in checks),
            "checks": checks,
            "warnings": warnings,
            "versions": versions,
            "latest": latest,
            "stale": bool(
                latest and any(latest["result"].get(k, 0) != v for k, v in versions.items())
            ),
            "records": records,
            "tasks": jobs[:12],
        }

    def accept(self, pid, eid, checks, notes):
        if set(checks) != REVIEW_CHECKS or not all(v is True for v in checks.values()):
            raise ValueError("请明确完成全部五项复核；没有使用的音频或图页也应核实为无。")
        job = self.completed(pid, eid)
        archive = self.store.project_dir(pid) / "exports" / (eid + ".zip")
        if not archive.is_file():
            raise ValueError("成品压缩包缺失，请重新导出后复核。")
        archive_hash = sha256(archive.read_bytes())
        if job["result"].get("archive_sha256") not in {None, archive_hash}:
            raise ValueError("成品压缩包已变化，请重新导出后复核。")
        versions = self.versions(pid, reader=job["kind"] == "reader_export")
        if any(job["result"].get(k, 0) != v for k, v in versions.items()):
            raise ConflictError("制作状态已变，请导出当前版本并复核后记录。")
        editorial = (
            self.reader.editorial.state(pid) if self.reader else {"revision": 0, "issues": []}
        )
        if any(
            i["state"] == "open" or i.get("versions") != self.versions(pid, reader=True)
            for i in editorial["issues"]
        ):
            raise ValueError(
                "请先处理制作意见、记录延期理由，并核对内容更新后的意见，再完成最终复核。"
            )
        record = {
            "editorial_revision": editorial["revision"],
            "export_id": eid,
            "checks": checks,
            "notes": notes,
            "reviewer": "local_user",
            "reviewed_at": now(),
            "versions": versions,
            "archive_sha256": archive_hash,
        }
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT revision FROM reader_editorial WHERE project_id=?", (pid,)
            ).fetchone()
            if (row[0] if row else 0) != editorial["revision"]:
                raise ConflictError("制作意见已变，请重新检查后复核。")
            # Mutations use this same database, so the check and record are serialized.
            for table, key in [
                ("review_states", "review_revision"),
                ("speech_states", "speech_revision"),
                ("visual_states", "visual_revision"),
                ("reader_states", "reader_revision"),
            ]:
                if key not in versions:
                    continue
                row = db.execute(
                    f"SELECT revision FROM {table} WHERE project_id=?", (pid,)
                ).fetchone()
                if row and row[0] != versions[key]:
                    raise ConflictError("制作状态已变，请重新导出并复核。")
            db.execute(
                "INSERT OR REPLACE INTO delivery_reviews VALUES(?,?,?)",
                (pid, eid, json.dumps(record, ensure_ascii=False)),
            )
            self.review.audit(db, pid, "delivery.review", None, record)
        return record
