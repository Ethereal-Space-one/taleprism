import json
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .text import Span, assert_span_coverage, build_units, decode_source, sha256, split_spans

RIGHTS = {"owned", "authorized", "public_domain", "local_test"}


def now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, metadata TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS spans (
                    project_id TEXT, id INTEGER, data TEXT NOT NULL,
                    PRIMARY KEY(project_id, id)
                );
                CREATE TABLE IF NOT EXISTS units (
                    project_id TEXT, id INTEGER, data TEXT NOT NULL,
                    PRIMARY KEY(project_id, id)
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, state TEXT NOT NULL,
                    created_at TEXT NOT NULL, error TEXT, result TEXT
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
            if "kind" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'export'")

    def recover_interrupted(self):
        """Called only after the application acquires the exclusive data-directory lock."""
        with self.db() as db:
            interrupted = list(
                db.execute("SELECT id,project_id,kind FROM jobs WHERE state='running'")
            )
            db.execute(
                "UPDATE jobs SET state='failed', error='应用上次退出时任务中断，原文与已接受素材已保留，请重试此项任务。' WHERE state='running'"
            )
        for job in interrupted:
            if job["kind"] not in {"export", "reader_export"}:
                continue
            parent = self.project_dir(job["project_id"]) / "exports"
            try:
                for suffix in ["", ".partial"]:
                    shutil.rmtree(parent / (job["id"] + suffix), ignore_errors=True)
                for suffix in [".zip", ".zip.partial"]:
                    (parent / (job["id"] + suffix)).unlink(missing_ok=True)
            except OSError:
                pass  # Unpublished paths remain inaccessible even if filesystem cleanup fails.

    @contextmanager
    def db(self):
        with sqlite3.connect(self.root / "storygal.sqlite", timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            yield conn

    def project_dir(self, project_id: str) -> Path:
        try:
            if str(uuid.UUID(project_id)) != project_id:
                raise ValueError()
        except ValueError:
            raise KeyError("项目不存在。") from None
        return self.root / "projects" / project_id

    def create(self, raw: bytes, filename: str, rights: str, encoding: str) -> dict:
        if rights not in RIGHTS:
            raise ValueError("请选择文本权利状态。")
        selected, canonical = decode_source(raw, encoding)
        spans = split_spans(canonical)
        units = build_units(canonical)
        project_id = str(uuid.uuid4())
        directory = self.project_dir(project_id)
        directory.mkdir(parents=True)
        for name, content in [("original.txt", raw), ("source.utf8.txt", canonical)]:
            path = directory / name
            path.write_bytes(content)
            path.chmod(0o444)
        metadata = {
            "id": project_id,
            "filename": Path(filename.replace("\\", "/")).name[:180],
            "encoding": selected,
            "rights_status": rights,
            "sha256": sha256(raw),
            "canonical_sha256": sha256(canonical),
            "byte_length": len(raw),
            "canonical_byte_length": len(canonical),
            "character_count": len(canonical.decode("utf-8")),
            "span_count": len(spans),
            "unit_count": len(units),
            "created_at": now(),
        }
        with self.db() as db:
            db.execute("INSERT INTO projects VALUES (?, ?)", (project_id, json.dumps(metadata)))
            db.executemany(
                "INSERT INTO spans VALUES (?, ?, ?)",
                [(project_id, s.id, s.model_dump_json()) for s in spans],
            )
            db.executemany(
                "INSERT INTO units VALUES (?, ?, ?)",
                [(project_id, u.id, u.model_dump_json()) for u in units],
            )
        return metadata

    def list_projects(self) -> list[dict]:
        with self.db() as db:
            return [
                json.loads(r[0])
                for r in db.execute("SELECT metadata FROM projects ORDER BY rowid DESC")
            ]

    def get(self, project_id: str) -> dict:
        self.project_dir(project_id)
        with self.db() as db:
            row = db.execute("SELECT metadata FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError("项目不存在。")
        return json.loads(row[0])

    def parts(self, project_id: str, kind: str) -> list[dict]:
        self.get(project_id)
        if kind not in {"spans", "units"}:
            raise ValueError("未知记录类型。")
        with self.db() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    f"SELECT data FROM {kind} WHERE project_id=? ORDER BY id", (project_id,)
                )
            ]

    def verify(self, project_id: str) -> dict:
        metadata = self.get(project_id)
        directory = self.project_dir(project_id)
        raw = (directory / "original.txt").read_bytes()
        canonical = (directory / "source.utf8.txt").read_bytes()
        if sha256(raw) != metadata["sha256"] or sha256(canonical) != metadata["canonical_sha256"]:
            raise ValueError("源文件哈希校验失败，原文可能被修改。")
        if canonical.decode("utf-8").encode(metadata["encoding"]) != raw:
            raise ValueError("编码往返校验失败。")
        assert_span_coverage(canonical, [Span(**s) for s in self.parts(project_id, "spans")])
        expected = [u.model_dump() for u in build_units(canonical)]
        if expected != self.parts(project_id, "units"):
            raise ValueError("显示单元校验失败。")
        return {
            "source_hash": True,
            "encoding_roundtrip": True,
            "span_coverage": True,
            "display_text": True,
            "whitespace_policy": "仅隐藏初始 BOM、换行和每行首尾空白；原文件完整保留。",
        }

    def start_job(self, project_id: str, kind: str = "export") -> str:
        self.get(project_id)
        if kind not in {"export", "reader_export", "analysis", "speech"}:
            raise ValueError("未知任务类型。")
        job_id = str(uuid.uuid4())
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM jobs WHERE project_id=? AND kind=? AND state='running'",
                (project_id, kind),
            ).fetchone():
                raise ValueError("同类任务正在执行，请等待完成。")
            db.execute(
                "INSERT INTO jobs(id,project_id,state,created_at,kind) VALUES (?, ?, 'running', ?, ?)",
                (job_id, project_id, now(), kind),
            )
        return job_id

    def finish_job(self, job_id: str, result: dict | None = None, error: str | None = None):
        with self.db() as db:
            db.execute(
                "UPDATE jobs SET state=?, error=?, result=? WHERE id=?",
                ("failed" if error else "completed", error, json.dumps(result), job_id),
            )

    def jobs(self, project_id: str) -> list[dict]:
        self.get(project_id)
        with self.db() as db:
            rows = db.execute(
                "SELECT * FROM jobs WHERE project_id=? ORDER BY rowid DESC", (project_id,)
            )
            return [
                dict(r) | {"result": json.loads(r["result"]) if r["result"] else None} for r in rows
            ]
