"""Project-scoped character identities, dialogue review and accepted visual assets."""

import io
import itertools
import json
import re
import uuid
import warnings

from PIL import Image, UnidentifiedImageError

from . import llm
from .storage import Store, now
from .text import sha256


class ConflictError(ValueError):
    pass


def uid() -> str:
    return str(uuid.uuid4())


def evidence(spans: list[dict], ids: list[int]) -> list[dict]:
    selected = {s["id"]: s for s in spans}
    if not ids or any(i not in selected for i in ids):
        raise ValueError("模型引用了不存在的原文证据，本轮未应用。")
    return [
        {"byte_start": selected[i]["byte_start"], "byte_end": selected[i]["byte_end"]}
        for i in sorted(set(ids))
    ]


def top_dialogues(data: bytes) -> list[dict]:
    text = data.decode("utf-8")
    offsets = [0]
    for c in text:
        offsets.append(offsets[-1] + len(c.encode("utf-8")))
    pairs = {"「": "」", "『": "』", "“": "”", '"': '"'}
    stack: list[str] = []
    start = 0
    result = []
    for i, c in enumerate(text):
        if stack and c == stack[-1]:
            stack.pop()
            if not stack and text[start + 1 : i].strip():
                prefix_start = (
                    max(
                        text.rfind("\n", 0, start),
                        text.rfind("。", 0, start),
                        text.rfind("，", 0, start),
                        text.rfind("」", 0, start),
                        text.rfind("”", 0, start),
                    )
                    + 1
                )
                prefix = text[prefix_start:start]
                match = re.fullmatch(
                    r"\s*([\u3400-\u9fffA-Za-z·]{1,8}?)(?:笑|問|问|答|喝|怒|哭|又)?(?:曰|道|說|说|問|问|喊)[：:]?\s*",
                    prefix,
                )
                label = match[1] if match else None
                if label in {
                    "他",
                    "她",
                    "我",
                    "你",
                    "乃",
                    "便",
                    "遂",
                    "又",
                    "答",
                    "眾",
                    "众",
                    "於是",
                    "于是",
                }:
                    label = None
                hint = None
                if label and match:
                    label_start = prefix_start + match.start(1)
                    hint = {
                        "byte_start": offsets[label_start],
                        "byte_end": offsets[label_start + len(label)],
                    }
                result.append(
                    {
                        "id": uid(),
                        "byte_start": offsets[start + 1],
                        "byte_end": offsets[i],
                        "outer_start": offsets[start],
                        "outer_end": offsets[i + 1],
                        "text": text[start + 1 : i],
                        "label": label,
                        "attribution": hint,
                        "speaker_id": None,
                        "suggested_speaker_id": None,
                        "status": "pending",
                        "confidence": 0.65 if label else 0,
                        "evidence": [],
                        "reviewer": None,
                        "reviewed_at": None,
                        "origin": "rules",
                    }
                )
        elif c in pairs:
            if not stack:
                start = i
            stack.append(pairs[c])
    return result


class Review:
    def __init__(self, store: Store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS review_states (project_id TEXT PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 0, last_analysis TEXT);
                CREATE TABLE IF NOT EXISTS characters (project_id TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(project_id,id));
                CREATE TABLE IF NOT EXISTS dialogues (project_id TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(project_id,id));
                CREATE TABLE IF NOT EXISTS assets (project_id TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(project_id,id));
                CREATE TABLE IF NOT EXISTS review_audit (id INTEGER PRIMARY KEY, project_id TEXT, action TEXT, actor TEXT, created_at TEXT, before_data TEXT, after_data TEXT);
                CREATE TABLE IF NOT EXISTS analysis_cache (cache_key TEXT PRIMARY KEY, data TEXT NOT NULL, usage TEXT NOT NULL);
            """)

    def source(self, project_id: str) -> bytes:
        self.store.get(project_id)
        return (self.store.project_dir(project_id) / "source.utf8.txt").read_bytes()

    @staticmethod
    def put(db, table: str, project_id: str, item: dict):
        db.execute(
            f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?)",
            (project_id, item["id"], json.dumps(item, ensure_ascii=False)),
        )

    @staticmethod
    def rows(db, table: str, project_id: str) -> list[dict]:
        result = [
            json.loads(r[0])
            for r in db.execute(
                f"SELECT data FROM {table} WHERE project_id=? ORDER BY rowid", (project_id,)
            )
        ]
        return sorted(result, key=lambda d: d["outer_start"]) if table == "dialogues" else result

    @staticmethod
    def item(db, table: str, project_id: str, item_id: str) -> dict:
        row = db.execute(
            f"SELECT data FROM {table} WHERE project_id=? AND id=?", (project_id, item_id)
        ).fetchone()
        if row is None:
            raise KeyError("记录不存在。")
        return json.loads(row[0])

    @staticmethod
    def audit(db, project_id: str, action: str, before, after, actor="local-user"):
        db.execute(
            "INSERT INTO review_audit(project_id,action,actor,created_at,before_data,after_data) VALUES (?,?,?,?,?,?)",
            (
                project_id,
                action,
                actor,
                now(),
                json.dumps(before, ensure_ascii=False),
                json.dumps(after, ensure_ascii=False),
            ),
        )

    def ensure(self, project_id: str):
        self.store.verify(project_id)
        with self.store.db() as db:
            if db.execute(
                "SELECT 1 FROM review_states WHERE project_id=?", (project_id,)
            ).fetchone():
                return
        dialogues = top_dialogues(self.source(project_id))
        characters: dict[str, dict] = {}
        for dialogue in dialogues:
            label = dialogue["label"]
            if label:
                if label not in characters:
                    characters[label] = {
                        "id": uid(),
                        "display_name": label,
                        "aliases": [],
                        "description": "",
                        "evidence": [],
                        "status": "candidate",
                        "active_figure_id": None,
                        "origin": "rules",
                        "merged_into": None,
                    }
                character = characters[label]
                if dialogue["attribution"] not in character["evidence"]:
                    character["evidence"].append(dialogue["attribution"])
                dialogue["suggested_speaker_id"] = character["id"]
                dialogue["evidence"] = [dialogue["attribution"]]
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM review_states WHERE project_id=?", (project_id,)
            ).fetchone():
                return
            db.execute("INSERT INTO review_states(project_id) VALUES (?)", (project_id,))
            for character in characters.values():
                self.put(db, "characters", project_id, character)
            for dialogue in dialogues:
                self.put(db, "dialogues", project_id, dialogue)

    def state(self, project_id: str) -> dict:
        self.ensure(project_id)
        with self.store.db() as db:
            db.execute("BEGIN")
            row = db.execute(
                "SELECT revision,last_analysis FROM review_states WHERE project_id=?", (project_id,)
            ).fetchone()
            characters = self.rows(db, "characters", project_id)
            dialogues = self.rows(db, "dialogues", project_id)
            assets = self.rows(db, "assets", project_id)
        for asset in assets:
            asset["url"] = f"/api/projects/{project_id}/assets/{asset['id']}/file"
        data = self.source(project_id)
        for item in [*characters, *dialogues]:
            item["evidence"] = [
                e | {"quote": data[e["byte_start"] : e["byte_end"]].decode("utf-8")}
                for e in item["evidence"]
            ]
        for dialogue in dialogues:
            dialogue["context_before"] = data[
                max(0, dialogue["outer_start"] - 240) : dialogue["outer_start"]
            ].decode("utf-8", errors="ignore")
            dialogue["context_after"] = data[
                dialogue["outer_end"] : dialogue["outer_end"] + 180
            ].decode("utf-8", errors="ignore")
        return {
            "revision": row["revision"],
            "last_analysis": json.loads(row["last_analysis"]) if row["last_analysis"] else None,
            "characters": characters,
            "dialogues": dialogues,
            "assets": assets,
            "pending_count": sum(d["status"] == "pending" for d in dialogues),
        }

    @staticmethod
    def lock(db, project_id: str, revision: int):
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT revision FROM review_states WHERE project_id=?", (project_id,)
        ).fetchone()
        if row is None or row[0] != revision:
            raise ConflictError("审校内容已更新，请刷新后再修改。")
        db.execute("UPDATE review_states SET revision=revision+1 WHERE project_id=?", (project_id,))

    @staticmethod
    def invalidate_speech_acceptance(db, project_id: str, dialogue_ids: list[str]):
        """Revoke acceptance in the same transaction as an actual speaker change."""
        if (
            not dialogue_ids
            or not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='speech_states'"
            ).fetchone()
        ):
            return  # Review can also be used without initializing speech.
        row = db.execute(
            "SELECT data FROM speech_states WHERE project_id=?", (project_id,)
        ).fetchone()
        if row is None:
            return
        data = json.loads(row[0])
        for did in dialogue_ids:
            if did in data["lines"]:
                data["lines"][did].pop("accepted", None)
        # Bump even without accepted audio: an in-flight accept may have validated
        # the old speaker. Keep takes and all other line/profile settings intact.
        db.execute(
            "UPDATE speech_states SET revision=revision+1,data=? WHERE project_id=?",
            (json.dumps(data, ensure_ascii=False), project_id),
        )

    @staticmethod
    def labels(name: str, aliases: list[str]) -> tuple[str, list[str]]:
        name = name.strip()
        labels = [name, *aliases]
        if len(labels) > 41 or any(
            not label.strip() or len(label) > 40 or any(ord(c) < 32 for c in label)
            for label in labels
        ):
            raise ValueError("姓名与别名需为 1–40 个字符，别名最多 40 个。")
        return name, sorted({a.strip() for a in aliases} - {name})

    def character(
        self,
        project_id: str,
        revision: int,
        name: str,
        aliases: list[str],
        description: str,
        character_id: str | None = None,
        status="confirmed",
    ) -> dict:
        self.ensure(project_id)
        name, aliases = self.labels(name, aliases)
        if status not in {"candidate", "confirmed", "rejected"} or len(description) > 2000:
            raise ValueError("角色状态或身份说明不正确。")
        with self.store.db() as db:
            self.lock(db, project_id, revision)
            before = self.item(db, "characters", project_id, character_id) if character_id else None
            if before and before.get("merged_into"):
                raise ValueError("该角色已合并，请编辑合并后的角色。")
            item = (
                dict(before)
                if before
                else {
                    "id": uid(),
                    "evidence": [],
                    "active_figure_id": None,
                    "origin": "manual",
                    "merged_into": None,
                }
            )
            item.update(
                display_name=name, aliases=aliases, description=description.strip(), status=status
            )
            self.put(db, "characters", project_id, item)
            if before and before["status"] != status:
                from .production import invalidate_reference_checks

                invalidate_reference_checks(
                    db, project_id, item["id"], character_status_changed=True
                )
            self.audit(db, project_id, "character.update", before, item)
        return item

    def merge(self, project_id: str, revision: int, source_id: str, target_id: str):
        self.ensure(project_id)
        if source_id == target_id:
            raise ValueError("请选择另一个角色作为合并目标。")
        with self.store.db() as db:
            self.lock(db, project_id, revision)
            source = self.item(db, "characters", project_id, source_id)
            target = self.item(db, "characters", project_id, target_id)
            before = {"source": dict(source), "target": dict(target)}
            if source.get("merged_into") or target.get("merged_into"):
                raise ValueError("不能再次合并已合并的角色。")
            _, target["aliases"] = self.labels(
                target["display_name"],
                target["aliases"] + source["aliases"] + [source["display_name"]],
            )
            target["evidence"] = list(
                {
                    (e["byte_start"], e["byte_end"]): e
                    for e in target["evidence"] + source["evidence"]
                }.values()
            )
            target["status"] = "confirmed"
            if not target["active_figure_id"]:
                target["active_figure_id"] = source["active_figure_id"]
            source.update(status="merged", merged_into=target_id, active_figure_id=None)
            changed_dialogues = []
            for table in ["dialogues", "assets"]:
                for record in self.rows(db, table, project_id):
                    if table == "dialogues" and record["speaker_id"] == source_id:
                        changed_dialogues.append(record["id"])
                    for field in (
                        ["speaker_id", "suggested_speaker_id"]
                        if table == "dialogues"
                        else ["character_id"]
                    ):
                        if record.get(field) == source_id:
                            record[field] = target_id
                    self.put(db, table, project_id, record)
            self.invalidate_speech_acceptance(db, project_id, changed_dialogues)
            self.put(db, "characters", project_id, source)
            self.put(db, "characters", project_id, target)
            from .production import invalidate_reference_checks

            invalidate_reference_checks(db, project_id, source_id, character_status_changed=True)
            active_changed = before["target"]["active_figure_id"] != target["active_figure_id"]
            status_changed = before["target"]["status"] != target["status"]
            if active_changed or status_changed:
                invalidate_reference_checks(
                    db,
                    project_id,
                    target_id,
                    active_changed=active_changed,
                    character_status_changed=status_changed,
                )
            self.audit(
                db, project_id, "character.merge", before, {"source": source, "target": target}
            )

    def assign(
        self, project_id: str, revision: int, dialogue_ids: list[str], speaker_id: str | None
    ):
        self.ensure(project_id)
        if not dialogue_ids or len(dialogue_ids) > 500:
            raise ValueError("请选择 1–500 条对白。")
        with self.store.db() as db:
            self.lock(db, project_id, revision)
            if speaker_id:
                character = self.item(db, "characters", project_id, speaker_id)
                if character["status"] != "confirmed":
                    raise ValueError("请先确认角色身份，再为对白指定说话人。")
            changed_dialogues = []
            for dialogue_id in dict.fromkeys(dialogue_ids):
                item = self.item(db, "dialogues", project_id, dialogue_id)
                before = dict(item)
                if item["speaker_id"] != speaker_id:
                    changed_dialogues.append(dialogue_id)
                item.update(
                    speaker_id=speaker_id,
                    status="reviewed",
                    reviewer="local-user",
                    reviewed_at=now(),
                )
                self.put(db, "dialogues", project_id, item)
                self.audit(db, project_id, "dialogue.assign", before, item)
            self.invalidate_speech_acceptance(db, project_id, changed_dialogues)

    def upload_asset(
        self,
        project_id: str,
        revision: int,
        character_id: str,
        raw: bytes,
        kind: str,
        license_text: str,
        origin: str = "user_upload",
        *,
        label: str = "",
        sample_key: str | None = None,
        portrait_state: str = "base",
    ) -> dict:
        self.ensure(project_id)
        if (
            len(raw) > 10_000_000
            or not raw
            or kind not in {"reference", "figure", "reference_and_figure"}
        ):
            raise ValueError("请选择不超过 10 MB 的 PNG、JPEG 或 WebP 图像。")
        if not license_text.strip() or len(license_text) > 1000:
            raise ValueError("请填写图像来源和使用许可（最多 1,000 字）。")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as image:
                    if (
                        image.format not in {"PNG", "JPEG", "WEBP"}
                        or image.width > 4096
                        or image.height > 4096
                    ):
                        raise ValueError("图片格式不支持或边长超过 4096 像素。")
                    image.load()
                    width, height = image.size
                    normalized = io.BytesIO()
                    image.convert("RGBA").save(normalized, "PNG")
                    content = normalized.getvalue()
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            raise ValueError("无法读取图像，请选择有效的 PNG、JPEG 或 WebP。") from None
        asset = {
            "id": uid(),
            "character_id": character_id,
            "kind": kind,
            "status": "pending",
            "sha256": sha256(content),
            "width": width,
            "height": height,
            "license": license_text.strip(),
            "origin": origin,
            "label": label,
            "sample_key": sample_key,
            "portrait_state": portrait_state,
            "created_at": now(),
        }
        with self.store.db() as db:
            self.lock(db, project_id, revision)
            character = self.item(db, "characters", project_id, character_id)
            if character["status"] in {"merged", "rejected"}:
                raise ValueError("请为有效角色上传图像。")
            for existing in self.rows(db, "assets", project_id):
                if all(existing[k] == asset[k] for k in ["character_id", "sha256", "kind"]):
                    return existing
            directory = self.store.project_dir(project_id) / "assets"
            directory.mkdir(exist_ok=True)
            file = directory / (asset["id"] + ".png")
            file.write_bytes(content)
            file.chmod(0o444)
            self.put(db, "assets", project_id, asset)
            self.audit(db, project_id, "asset.upload", None, asset)
        return asset

    def asset_path(self, project_id: str, asset_id: str):
        self.store.get(project_id)
        with self.store.db() as db:
            asset = self.item(db, "assets", project_id, asset_id)
        path = self.store.project_dir(project_id) / "assets" / (asset["id"] + ".png")
        if not path.is_file() or sha256(path.read_bytes()) != asset["sha256"]:
            raise ValueError("角色图像不存在或哈希不一致，请重新上传。")
        return path

    def accept_asset(
        self, project_id: str, revision: int, asset_id: str, status: str, active: bool
    ):
        self.ensure(project_id)
        if status not in {"accepted", "rejected", "pending"}:
            raise ValueError("图像审核状态不正确。")
        self.asset_path(project_id, asset_id)
        with self.store.db() as db:
            self.lock(db, project_id, revision)
            item = self.item(db, "assets", project_id, asset_id)
            before = dict(item)
            character = self.item(db, "characters", project_id, item["character_id"])
            previous_active = character["active_figure_id"]
            if active and (
                status != "accepted"
                or character["status"] != "confirmed"
                or item["kind"] == "reference"
            ):
                raise ValueError("只可启用已确认角色的已接受立绘。")
            if (
                active
                and item["kind"] == "figure"
                and not any(
                    a["character_id"] == character["id"]
                    and a["status"] == "accepted"
                    and a["kind"] in {"reference", "reference_and_figure"}
                    for a in self.rows(db, "assets", project_id)
                )
            ):
                raise ValueError("请先接受该角色的参考图。")
            item["status"] = status
            if active:
                character["active_figure_id"] = asset_id
            elif character["active_figure_id"] == asset_id:
                character["active_figure_id"] = None
            if item["kind"] in {"reference", "reference_and_figure"} and status != "accepted":
                other_references = [
                    a
                    for a in self.rows(db, "assets", project_id)
                    if a["id"] != asset_id
                    and a["character_id"] == character["id"]
                    and a["status"] == "accepted"
                    and a["kind"] in {"reference", "reference_and_figure"}
                ]
                if not other_references:
                    character["active_figure_id"] = None
            self.put(db, "assets", project_id, item)
            self.put(db, "characters", project_id, character)
            active_changed = previous_active != character["active_figure_id"]
            status_changed = before["status"] != status
            if active_changed or status_changed:
                from .production import invalidate_reference_checks

                invalidate_reference_checks(
                    db,
                    project_id,
                    character["id"],
                    asset_id=asset_id if status_changed else None,
                    active_changed=active_changed,
                )
            self.audit(db, project_id, "asset.review", before, item | {"active": active})

    def payloads(self, project_id: str) -> list[dict]:
        state = self.state(project_id)
        spans = self.store.parts(project_id, "spans")
        dialogues = state["dialogues"]
        result = []
        # Context overlaps across chunks; stable byte anchors are resolved by the application.
        for i in range(0, max(1, len(dialogues)), 32):
            batch = dialogues[i : i + 32]
            start = max(0, (batch[0]["outer_start"] - 1500) if batch else 0)
            end = (batch[-1]["outer_end"] + 1500) if batch else len(self.source(project_id))
            selected = [s for s in spans if s["byte_end"] > start and s["byte_start"] < end]
            result.append(
                {
                    "spans": [{"id": s["id"], "text": s["text"]} for s in selected],
                    "dialogues": [
                        {
                            "id": d["id"],
                            "span_ids": [
                                s["id"]
                                for s in selected
                                if s["byte_end"] > d["outer_start"]
                                and s["byte_start"] < d["outer_end"]
                            ],
                        }
                        for d in batch
                    ],
                    "known_characters": [
                        {"name": c["display_name"], "aliases": c["aliases"]}
                        for c in state["characters"]
                        if c["status"] == "confirmed"
                    ],
                }
            )
        return result

    def validate_proposal(self, proposal: dict, payload: dict, project_id: str):
        parsed = llm.AnalysisProposal.model_validate(proposal)
        spans = {s["id"]: s["text"] for s in payload["spans"]}
        valid_ids = set(spans)
        dialogue_ids = {d["id"] for d in payload["dialogues"]}
        if (
            len(parsed.speakers) != len(dialogue_ids)
            or {s.dialogue_id for s in parsed.speakers} != dialogue_ids
        ):
            raise ValueError("模型对白编号有遗漏或重复，本轮未应用。")
        names = {label for c in payload["known_characters"] for label in [c["name"], *c["aliases"]]}
        for c in parsed.characters:
            self.labels(c.name, c.aliases)
            if not set(c.evidence_span_ids) <= valid_ids:
                raise ValueError("模型角色证据引用无效，本轮未应用。")
            runs = []
            previous = None
            for span_id in sorted(set(c.evidence_span_ids)):
                if previous is None or span_id != previous + 1:
                    runs.append(spans[span_id])
                else:
                    runs[-1] += spans[span_id]
                previous = span_id
            if any(not any(label in quote for quote in runs) for label in [c.name, *c.aliases]):
                raise ValueError("模型角色或别名缺少逐字原文依据，本轮未应用。")
            names.update([c.name, *c.aliases])
        for speaker in parsed.speakers:
            if not set(speaker.evidence_span_ids) <= valid_ids or (
                speaker.speaker_name is not None and speaker.speaker_name not in names
            ):
                raise ValueError("模型说话人或证据引用无效，本轮未应用。")
        return parsed.model_dump()

    def analyze(self, project_id: str) -> dict:
        payloads = self.payloads(project_id)
        config = llm.configuration()
        proposals = []
        cached = 0
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for payload in payloads:
            cache_key = sha256(
                json.dumps(
                    {"payload": payload, "config": config}, ensure_ascii=False, sort_keys=True
                ).encode()
            )
            with self.store.db() as db:
                hit = db.execute(
                    "SELECT data,usage FROM analysis_cache WHERE cache_key=?", (cache_key,)
                ).fetchone()
            if hit:
                proposal = json.loads(hit[0])
                cached += 1
            else:
                proposal, consumed = llm.analyze(payload)
                proposal = self.validate_proposal(proposal, payload, project_id)
                for field in usage:
                    usage[field] += consumed.get(field, 0)
                with self.store.db() as db:
                    db.execute(
                        "INSERT OR REPLACE INTO analysis_cache VALUES (?, ?, ?)",
                        (cache_key, json.dumps(proposal, ensure_ascii=False), json.dumps(consumed)),
                    )
            proposals.append(self.validate_proposal(proposal, payload, project_id))
        return self.apply_proposals(
            project_id,
            proposals,
            config | {"requests": len(payloads) - cached, "cache_hits": cached, "usage": usage},
        )

    def apply_proposals(self, project_id: str, proposals: list[dict], info: dict):
        spans = self.store.parts(project_id, "spans")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            characters = self.rows(db, "characters", project_id)
            for proposal in proposals:
                for candidate in proposal["characters"]:
                    matches = [
                        c
                        for c in characters
                        if not c.get("merged_into")
                        and candidate["name"] in [c["display_name"], *c["aliases"]]
                    ]
                    if len(matches) == 1:
                        item = matches[0]
                        if item["status"] != "candidate":
                            continue  # Manual identity decisions are authoritative.
                        item["aliases"] = sorted(
                            set(item["aliases"] + candidate["aliases"]) - {item["display_name"]}
                        )
                    elif len(matches) > 1:
                        continue
                    else:
                        item = {
                            "id": uid(),
                            "display_name": candidate["name"],
                            "aliases": candidate["aliases"],
                            "description": "",
                            "evidence": [],
                            "status": "candidate",
                            "active_figure_id": None,
                            "origin": "llm",
                            "merged_into": None,
                        }
                        characters.append(item)
                    item["evidence"] = list(
                        {
                            (e["byte_start"], e["byte_end"]): e
                            for e in item["evidence"]
                            + evidence(spans, candidate["evidence_span_ids"])
                        }.values()
                    )
                    self.put(db, "characters", project_id, item)
            for proposal in proposals:
                for speaker in proposal["speakers"]:
                    item = self.item(db, "dialogues", project_id, speaker["dialogue_id"])
                    if item["status"] == "reviewed":
                        continue
                    matches = [
                        c
                        for c in characters
                        if c["status"] not in {"merged", "rejected"}
                        and speaker["speaker_name"] in [c["display_name"], *c["aliases"]]
                    ]
                    item.update(
                        suggested_speaker_id=matches[0]["id"] if len(matches) == 1 else None,
                        confidence=speaker["confidence"] if len(matches) == 1 else 0,
                        evidence=evidence(spans, speaker["evidence_span_ids"]),
                        origin="llm",
                    )
                    self.put(db, "dialogues", project_id, item)
            info = info | {"completed_at": now()}
            db.execute(
                "UPDATE review_states SET revision=revision+1,last_analysis=? WHERE project_id=?",
                (json.dumps(info), project_id),
            )
            self.audit(db, project_id, "analysis.apply", None, info, actor=info.get("model", "llm"))
        return info

    def presentation(self, project_id: str) -> tuple[list[dict], dict]:
        state = self.state(project_id)
        base_units = self.store.parts(project_id, "units")
        characters = {c["id"]: c for c in state["characters"] if c["status"] == "confirmed"}
        assets = {
            a["id"]: a
            for a in state["assets"]
            if a["status"] == "accepted" and a["kind"] != "reference"
        }
        has_reference = {
            a["character_id"]
            for a in state["assets"]
            if a["status"] == "accepted" and a["kind"] in {"reference", "reference_and_figure"}
        }
        # Preserve P0 pagination until there are actual human speaker decisions.
        if not any(d["status"] == "reviewed" for d in state["dialogues"]):
            return base_units, state
        data = self.source(project_id)
        units = []
        for unit in base_units:
            boundaries = sorted(
                {
                    unit["byte_start"],
                    unit["byte_end"],
                    *[
                        d["outer_end"]
                        for d in state["dialogues"]
                        if unit["byte_start"] < d["outer_end"] < unit["byte_end"]
                    ],
                }
            )
            for start, end in itertools.pairwise(boundaries):
                overlapping = [
                    d
                    for d in state["dialogues"]
                    if d["outer_start"] < end and d["outer_end"] > start
                ]
                character = None
                if len(overlapping) == 1 and overlapping[0]["status"] == "reviewed":
                    character = characters.get(overlapping[0]["speaker_id"])
                asset = (
                    assets.get(character["active_figure_id"])
                    if character and character["id"] in has_reference
                    else None
                )
                if asset and asset["character_id"] != character["id"]:
                    raise ValueError("立绘角色关联不正确。")
                units.append(
                    {
                        "id": len(units),
                        "byte_start": start,
                        "byte_end": end,
                        "text": data[start:end].decode("utf-8"),
                        "speaker_id": character["id"] if character else None,
                        "speaker_name": character["display_name"] if character else None,
                        "figure_asset_id": asset["id"] if asset else None,
                    }
                )
        if "".join(u["text"] for u in units) != "".join(u["text"] for u in base_units):
            raise ValueError("说话人显示单元改变了原文。")
        return units, state
