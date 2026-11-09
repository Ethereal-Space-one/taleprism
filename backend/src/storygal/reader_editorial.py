"""Private project review notes, deliberately separate from public reader content."""

import json
import uuid

from .review import ConflictError
from .storage import now


class Editorial:
    def __init__(self, reader):
        self.reader = reader
        with reader.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS reader_editorial(project_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL)"
            )

    def state(self, pid):
        self.reader.store.get(pid)
        with self.reader.store.db() as db:
            row = db.execute(
                "SELECT revision,data FROM reader_editorial WHERE project_id=?", (pid,)
            ).fetchone()
        return (
            {"revision": row[0], "issues": json.loads(row[1])}
            if row
            else {"revision": 0, "issues": []}
        )

    def save(self, pid, revision, issue):
        raw = self.reader.review.source(pid)
        if not any(
            b["byte_start"] <= issue["anchor"] < b["byte_end"] for b in self.reader.blocks(pid)
        ):
            raise ValueError("意见位置必须属于当前原文。")
        try:
            raw[: issue["anchor"]].decode()
        except UnicodeDecodeError:
            raise ValueError("意见位置必须是完整字符。") from None
        if issue["state"] == "deferred" and not issue["reason"].strip():
            raise ValueError("延期事项必须记录理由。")
        with self.reader.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO reader_editorial VALUES(?,0,'[]')", (pid,))
            row = db.execute(
                "SELECT revision,data FROM reader_editorial WHERE project_id=?", (pid,)
            ).fetchone()
            if row[0] != revision:
                raise ConflictError("制作意见已更新，请保留草稿并刷新。")
            issues = json.loads(row[1])
            if issue.get("id") and not any(i["id"] == issue["id"] for i in issues):
                raise ValueError("制作意见不存在。")
            issue = {
                **issue,
                "id": issue.get("id") or str(uuid.uuid4()),
                "updated_at": now(),
                "versions": self.reader.version_state(db, pid),
            }
            issues = [i for i in issues if i["id"] != issue["id"]] + [issue]
            db.execute(
                "UPDATE reader_editorial SET revision=revision+1,data=? WHERE project_id=?",
                (json.dumps(issues, ensure_ascii=False), pid),
            )
            self.reader.review.audit(db, pid, "reader.editorial", None, issue)
        return self.state(pid)
