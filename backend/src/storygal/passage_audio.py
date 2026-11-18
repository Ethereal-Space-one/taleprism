"""Shared lifecycle for independently reviewed, immutable, paragraph-bound WAVs.

Subclasses provide format/recipe validation and a fixed publication label. All
mutations use the reader revision, including pending edits and withdrawal.
"""

from pathlib import Path

from .text import sha256


class PassageAudio:
    table: str
    endpoint: str
    directory: str
    block_key: str
    origin: str
    label: str
    creator_fields: str
    max_size: int

    def __init__(self, reader):
        self.reader, self.store, self.review = reader, reader.store, reader.review
        with self.store.db() as db:
            db.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table}("
                "project_id TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(project_id,id))"
            )

    def url(self, pid, aid):
        return f"/api/projects/{pid}/reader/{self.endpoint}/{aid}/file"

    def state(self, pid):
        self.reader.load(pid)
        with self.store.db() as db:
            db.execute("BEGIN")
            revision = db.execute(
                "SELECT revision FROM reader_states WHERE project_id=?", (pid,)
            ).fetchone()[0]
            takes = self.review.rows(db, self.table, pid)
        fields = ("id byte_start byte_end status duration " + self.creator_fields).split()
        return {
            "revision": revision,
            "takes": [
                {k: t[k] for k in fields if k in t} | {"url": self.url(pid, t["id"])} for t in takes
            ],
        }

    def path(self, pid, aid) -> Path:
        with self.store.db() as db:
            row = self.review.item(db, self.table, pid, aid)
        path = self.store.project_dir(pid) / self.directory / (row["id"] + ".wav")
        error = self.label + "文件缺失或已改变，请更换或撤下后再导出。"
        if not path.is_file() or path.stat().st_size > self.max_size:
            raise ValueError(error)
        raw = path.read_bytes()
        if sha256(raw) != row["sha256"]:
            raise ValueError(error)
        canonical, duration = self.inspect_wav(raw)
        if canonical != raw or row["duration"] != duration:
            raise ValueError(error)
        return path

    def save_pending(self, pid, revision, row, wav, action):
        folder = self.store.project_dir(pid) / self.directory
        folder.mkdir(exist_ok=True)
        path = folder / (row["id"] + ".wav")
        try:
            path.write_bytes(wav)
            path.chmod(0o444)
            self.reader.mutate(
                pid, revision, action, lambda db, _: self.review.put(db, self.table, pid, row)
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return self.state(pid)

    def change(self, pid, revision, aid, status):
        def update(db, _):
            current = self.review.item(db, self.table, pid, aid)
            if current["status"] == "withdrawn" or current["status"] == status:
                raise ValueError("此版本已处理；撤下的版本不会重新自动启用。")
            if status == "accepted":
                self.path(pid, aid)
                blocks = {b["byte_start"]: b for b in self.reader.blocks(pid)}
                project = self.store.get(pid)
                self.validate_record(
                    current,
                    blocks,
                    project["canonical_sha256"],
                    project["sha256"],
                    current["duration"],
                )
                for old in self.review.rows(db, self.table, pid):
                    if old["status"] == "accepted" and old["byte_start"] == current["byte_start"]:
                        self.review.put(db, self.table, pid, old | {"status": "withdrawn"})
            elif status != "withdrawn":
                raise ValueError("声音状态无效。")
            self.review.put(db, self.table, pid, current | {"status": status})

        self.reader.mutate(pid, revision, self.directory + ".review", update)
        return self.state(pid)

    def public_cue(self, _row):
        return {}

    def public_credit(self, _row):
        return {}

    def attach(self, pid, blocks, media, issues, strict):
        with self.store.db() as db:
            takes = self.review.rows(db, self.table, pid)
        lookup = {b["byte_start"]: b for b in blocks}
        project = self.store.get(pid)
        for take in takes:
            if take["status"] != "accepted":
                continue
            try:
                self.path(pid, take["id"])
                self.validate_record(
                    take, lookup, project["canonical_sha256"], project["sha256"], take["duration"]
                )
                block = lookup[take["byte_start"]]
                if self.block_key in block or take["id"] in media:
                    raise ValueError("已接受的" + self.label + "与现有记录冲突。")
            except ValueError as exc:
                if strict:
                    raise
                issues.append(str(exc))
                continue
            aid = take["id"]
            block[self.block_key] = {
                "id": aid,
                "duration": take["duration"],
                "label": self.label,
                **self.public_cue(take),
            }
            media[aid] = {
                "id": aid,
                "sha256": take["sha256"],
                "duration": take["duration"],
                "origin": self.origin,
                "type": "audio",
                "url": self.url(pid, aid),
                **self.public_credit(take),
            }
