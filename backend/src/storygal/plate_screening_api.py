"""Private workbench sidecar. Not reader config, a renderer, or a bundle extension."""

import json
from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import plate_screening as screening
from . import plate_timing
from .review import ConflictError

FIELDS = ("decision", *screening.FIELDS, "verification", "proposed_effect")
MAX_SHEET_BYTES = 2_000_000


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0)
    reader_revision: int = Field(ge=0)


class Judgment(Edit):
    plate_id: str = Field(min_length=1, max_length=80)
    proposed_effect: Literal["rain-wet-ground", "wave-impact-backwash"] | None = None
    decision: Literal["still", "motion", "deferred"]
    evidence: str = Field(min_length=1, max_length=300)
    observation: str = Field(min_length=1, max_length=1000)
    action: str = Field(min_length=1, max_length=1000)
    protect: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)
    verification: str = Field(default="", max_length=1000)


class Timing(Edit):
    plate_id: str = Field(min_length=1, max_length=80)
    binding: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["unchecked", "clear", "revise"]
    evidence: str = Field(max_length=300)
    reason: str = Field(max_length=1000)


class ImportSheet(Edit):
    worksheet: str = Field(max_length=MAX_SHEET_BYTES)
    exact_copy: bool = False


def read_row(db, pid):
    return db.execute(
        "SELECT revision,data,changed FROM private_plate_screenings WHERE project_id=?", (pid,)
    ).fetchone()


def timing_row(db, pid):
    return db.execute(
        "SELECT revision,data FROM private_plate_timings WHERE project_id=?", (pid,)
    ).fetchone()


def bindings(row):
    return {k: v for k, v in row.items() if k not in FIELDS}


def same_binding(a, b):
    return bindings(a) == bindings(b)


class ScreeningDesk:
    def __init__(self, reader):
        self.reader, self.store = reader, reader.store
        with self.store.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS private_plate_screenings(
                project_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                data TEXT NOT NULL, changed TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS private_plate_timings(
                project_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL)""")

    def inventory(self, pid):
        # Use the actual adopted chapter plates, not prompts, unselected uploads or
        # guesses from display titles. A hash/dimension mismatch is an error.
        revision, config = self.reader.load(pid)
        raw = self.reader.review.source(pid)
        blocks = self.reader.blocks(pid)
        used = {p["image_asset_id"] for p in config["illustrations"]}
        assets = self.reader.state_assets(pid) if used else []
        media = {a["id"]: a | {"type": "image"} for a in assets if a["id"] in used}
        book = {"project": self.store.get(pid), "blocks": blocks, "config": config, "media": media}
        current = screening.make_worksheet(
            book, raw, lambda aid: self.reader.path(pid, aid).read_bytes()
        )
        return current, book, raw, revision

    def snapshot(self, pid):
        current, book, raw, reader_revision = self.inventory(pid)
        with self.store.db() as db:
            stored = read_row(db, pid)
            stored_timing = timing_row(db, pid)
        revision = stored[0] if stored else 0
        old = json.loads(stored[1]) if stored else current
        sheet, notices = screening.reconcile(current, old)
        before = {r["plate_id"]: r for r in old["plates"]}
        ids = {r["plate_id"] for r in current["plates"]}
        changed = set(json.loads(stored[2]) if stored else []) & ids
        for row in current["plates"]:
            prior = before.get(row["plate_id"])
            if (
                prior
                and prior["decision"] != "unassessed"
                and (
                    old["source_sha256"] != current["source_sha256"] or not same_binding(row, prior)
                )
            ):
                changed.add(row["plate_id"])
        carriers = screening.carriers_for_book(book, current, raw)
        report = screening.assess(current, sheet, raw, carriers=carriers)
        timing_display, timing = plate_timing.assess(book, current, stored_timing)
        paragraphs = {b["byte_end"]: b["text"] for b in book["blocks"]}
        display = {
            r["plate_id"]: {
                **timing_display[r["plate_id"]],
                "paragraph": paragraphs[r["after_byte"]],
                "carrier": carriers.get(r["plate_id"]),
            }
            for r in current["plates"]
        }
        data = {
            "revision": revision,
            "reader_revision": reader_revision,
            "worksheet": sheet,
            "changed": sorted(changed),
            "notices": notices,
            "display": display,
            "report": report,
            "timing": timing,
        }
        return data, current, raw

    def state(self, pid):
        return self.snapshot(pid)[0]

    def check_versions(self, db, pid, revision, reader_revision):
        stored = read_row(db, pid)
        row = db.execute("SELECT revision FROM reader_states WHERE project_id=?", (pid,)).fetchone()
        if (stored[0] if stored else 0) != revision or (row[0] if row else 0) != reader_revision:
            raise ConflictError("审图单或底图编排已更新；请重新读取，再对照当前图文。")

    def check_timing_version(self, db, pid, revision):
        stored = timing_row(db, pid)
        if (stored[0] if stored else 0) != revision:
            raise ConflictError("揭示时机判断已变，请重新核对。")
        return stored

    def edit_timing(self, pid, body):
        state, _, raw = self.snapshot(pid)
        timing = state["timing"]
        row = timing["plates"].get(body.plate_id)
        if (
            not row
            or body.binding != row["binding"]
            or body.revision != timing["revision"]
            or body.reader_revision != state["reader_revision"]
        ):
            raise ConflictError("揭示时机或图文已变；没有覆盖，请重新核对当前版本。")
        value = plate_timing.judgment(
            body, raw, state["display"][body.plate_id]["display_after_byte"]
        )
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            stored = self.check_timing_version(db, pid, body.revision)
            reader_row = db.execute(
                "SELECT revision FROM reader_states WHERE project_id=?", (pid,)
            ).fetchone()
            if reader_row[0] != body.reader_revision:
                raise ConflictError("底图编排已变，请重新核对当前图文。")
            prior = json.loads(stored[1]) if stored else {}
            next_rows = {k: v for k, v in prior.items() if k in timing["plates"]}
            if body.status == "unchecked":
                next_rows.pop(body.plate_id, None)
            else:
                next_rows[body.plate_id] = value
            if next_rows != prior:
                db.execute(
                    "INSERT OR REPLACE INTO private_plate_timings VALUES(?,?,?)",
                    (pid, body.revision + 1, json.dumps(next_rows, ensure_ascii=False)),
                )
        return self.state(pid)

    def edit(self, pid, body):
        state, current, raw = self.snapshot(pid)
        sheet = deepcopy(state["worksheet"])
        if (body.revision, body.reader_revision) != (state["revision"], state["reader_revision"]):
            raise ConflictError("审图单或底图编排已更新；本次输入没有覆盖新记录。")
        changed = set(state["changed"])
        if isinstance(body, Judgment):
            row = next((r for r in sheet["plates"] if r["plate_id"] == body.plate_id), None)
            if not row:
                raise ValueError("该插图已不在当前编排。")
            row.update({k: getattr(body, k) for k in FIELDS})
            touched = {body.plate_id}
        else:
            try:
                incoming = screening.Worksheet.model_validate_json(body.worksheet).model_dump()
            except ValueError:
                raise ValueError("请选择字段有效、无重复行的第一版私有审图单 JSON。") from None
            remote = {r["plate_id"]: r for r in incoming["plates"]}
            # Even in the same project, file import is exact-set only. A stale
            # sidecar never overwrites valid judgments or fills a changed plate.
            if current["source_sha256"] != incoming["source_sha256"] or (
                set(remote) != {r["plate_id"] for r in current["plates"]}
                or any(not same_binding(r, remote[r["plate_id"]]) for r in current["plates"])
            ):
                raise ValueError("审图单与本版原文、实图或位置不一致；没有导入，请重新审图。")
            if incoming["work_id"] != current["work_id"] and not body.exact_copy:
                raise ConflictError(
                    "审图单属于另一工程。仅在确认这是完整还原的相同作品时允许移入。"
                )
            touched = set()
            for row in sheet["plates"]:
                other = remote[row["plate_id"]]
                if other["decision"] == "unassessed":
                    if any(other[k] for k in FIELDS[1:]):
                        raise ValueError("未审图行不能携带既有判断。")
                    continue
                values = {k: other[k] for k in FIELDS}
                if row["decision"] != "unassessed" and any(row[k] != v for k, v in values.items()):
                    raise ValueError("本机有不同的有效判断；请逐幅编辑，导入不会覆盖。")
                row.update(values)
                touched.add(row["plate_id"])
        # A still/deferred decision may disagree with an existing renderer:
        # allow saving that editorial judgment, but the *formal gate* reports
        # the unresolved contradiction. Never bless it or turn the renderer off.
        motion_carriers = {
            r["plate_id"]: state["display"][r["plate_id"]]["carrier"]
            for r in sheet["plates"]
            if r["decision"] == "motion" and state["display"][r["plate_id"]]["carrier"]
        }
        validation = screening.assess(current, sheet, raw, carriers=motion_carriers)
        for r in validation["plates"]:
            if r["plate_id"] in touched and r["errors"]:
                raise ValueError("无法保存本幅判断：" + "；".join(r["errors"]))
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.check_versions(db, pid, body.revision, body.reader_revision)
            if sheet == state["worksheet"] and not (changed & touched):
                return state
            db.execute(
                "INSERT OR REPLACE INTO private_plate_screenings VALUES(?,?,?,?)",
                (
                    pid,
                    body.revision + 1,
                    json.dumps(sheet, ensure_ascii=False),
                    json.dumps(sorted(changed - touched)),
                ),
            )
        return self.state(pid)


def mount_screening(app, reader):
    desk = ScreeningDesk(reader)
    base = "/api/projects/{pid}/plate-screening"

    @app.get(base)
    def state(pid: str):
        return desk.state(pid)

    @app.put(base + "/plate")
    def save(pid: str, body: Judgment):
        return desk.edit(pid, body)

    @app.put(base + "/timing")
    def timing(pid: str, body: Timing):
        return desk.edit_timing(pid, body)

    @app.post(base + "/import")
    def import_sheet(pid: str, body: ImportSheet):
        return desk.edit(pid, body)

    return desk
