"""Paragraph-based reading, persistent scene anchors and reviewed local media."""

import io
import itertools
import json
import re
import uuid
import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from . import reader_presentation as presentation
from .review import ConflictError
from .text import sha256, visible_text

REPO = Path(__file__).resolve().parents[3]


def paragraphs(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8")
    result = []
    for match in re.finditer(r"[^\r\n]+", text):
        line = match.group()
        stripped = line.removeprefix("\ufeff") if match.start() == 0 else line
        body = stripped.strip(" \t\u3000")
        if not body:
            continue
        start = len(text[: match.start()].encode()) + len(
            line[: len(line) - len(stripped.lstrip(" \t\u3000"))].encode()
        )
        result.append(
            {
                "id": f"p-{start}",
                "byte_start": start,
                "byte_end": start + len(body.encode()),
                "text": body,
                "heading": bool(re.match(r"第.{1,12}[回章]", body)),
            }
        )
    if "".join(p["text"] for p in result) != visible_text(text):
        raise ValueError("阅读段落与原文不一致。")
    return result


class Reader:
    def __init__(self, store, review, speech):
        self.store, self.review, self.speech = store, review, speech
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS reader_states(project_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reader_assets(project_id TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(project_id,id));
            """)

    def blocks(self, pid):
        self.store.verify(pid)
        return paragraphs(self.review.source(pid))

    def load(self, pid):
        project = self.store.get(pid)
        default = {
            "title": project["filename"].removesuffix(".txt"),
            "subtitle": "",
            "cover_asset_id": None,
            "scenes": [],
            "map_profile": None,
        }
        with self.store.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO reader_states VALUES(?,0,?)",
                (pid, json.dumps(default, ensure_ascii=False)),
            )
            row = db.execute(
                "SELECT revision,data FROM reader_states WHERE project_id=?", (pid,)
            ).fetchone()
        return row[0], presentation.normalize(json.loads(row[1]))

    def mutate(self, pid, revision, action, fn):
        self.load(pid)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT revision,data FROM reader_states WHERE project_id=?", (pid,)
            ).fetchone()
            if row[0] != revision:
                raise ConflictError("阅读器配置已更新，请刷新后重试。")
            data = json.loads(row[1])
            before = json.loads(row[1])
            result = fn(db, data)
            db.execute(
                "UPDATE reader_states SET revision=revision+1,data=? WHERE project_id=?",
                (json.dumps(data, ensure_ascii=False), pid),
            )
            self.review.audit(db, pid, action, before, data)
        return result

    def state_assets(self, pid):
        with self.store.db() as db:
            return self.review.rows(db, "reader_assets", pid)

    def version_state(self, db, pid):
        result = {}
        for table, key in [
            ("reader_states", "reader_revision"),
            ("review_states", "review_revision"),
            ("speech_states", "speech_revision"),
            ("production_states", "production_revision"),
        ]:
            row = db.execute(f"SELECT revision FROM {table} WHERE project_id=?", (pid,)).fetchone()
            result[key] = row[0] if row else 0
        return result

    def state(self, pid):
        revision, config = self.load(pid)
        with self.store.db() as db:
            assets = self.review.rows(db, "reader_assets", pid)
        review = self.review.state(pid)
        return {
            "revision": revision,
            "figures": [
                a
                for a in review["assets"]
                if a["kind"] != "reference" and a["status"] != "rejected"
            ],
            "config": config,
            "issues": self.publication_issues(pid, config, review),
            "chibi_sample": self.is_chibi(pid),
            "assets": [a | {"url": f"/api/projects/{pid}/reader/assets/{a['id']}"} for a in assets],
            "paragraphs": [
                {
                    "byte_start": p["byte_start"],
                    "byte_end": p["byte_end"],
                    "text": p["text"],
                    "preview": p["text"][:45],
                }
                for p in self.blocks(pid)
            ],
        }

    def is_chibi(self, pid):
        sample = REPO / "samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt"
        return self.store.get(pid)["canonical_sha256"] == sha256(sample.read_bytes())

    def validate(self, pid, config, check_characters=True, *, for_restore=False):
        starts = {p["byte_start"] for p in self.blocks(pid)}
        scenes = config["scenes"]
        if len(scenes) > 64 or len({s["id"] for s in scenes}) != len(scenes):
            raise ValueError("场景最多 64 个，场景编号不能重复。")
        if scenes and (
            scenes[0]["start_byte"] != min(starts)
            or any(a["start_byte"] >= b["start_byte"] for a, b in itertools.pairwise(scenes))
        ):
            raise ValueError("场景必须按段落顺序排列，第一场景须从首段开始。")
        with self.store.db() as db:
            assets = {a["id"]: a for a in self.review.rows(db, "reader_assets", pid)}
        if (
            config["cover_asset_id"]
            and assets.get(config["cover_asset_id"], {}).get("kind") != "cover"
        ):
            raise ValueError("封面素材不属于本项目或类型不正确。")
        characters = {c["id"]: c for c in self.review.state(pid)["characters"]}
        confirmed = {cid for cid, c in characters.items() if c["status"] == "confirmed"}
        for scene in scenes:
            if scene["start_byte"] not in starts:
                raise ValueError("场景锚点必须位于当前原文段落开头。")
            if assets.get(scene["asset_id"], {}).get("kind") != "scene":
                raise ValueError("场景素材不属于本项目或类型不正确。")
            if not set(scene["character_ids"]) <= characters.keys():
                raise ValueError("场景人物不存在或不属于本项目。")
            if (
                check_characters
                and not for_restore
                and not set(scene["character_ids"]) <= confirmed
            ):
                raise ValueError("场景人物需为已确认角色，请在人物页确认后再保存。")
        if config["map_profile"] and not self.is_chibi(pid):
            raise ValueError("赤壁地图目前仅适用于完整赤壁样例。")

    def publication_issues(self, pid, config, review=None):
        """Describe current approval problems without changing saved editorial choices."""
        review = review if review is not None else self.review.state(pid)
        characters = {c["id"]: c for c in review["characters"]}
        used = {cid for scene in config["scenes"] for cid in scene["character_ids"]}
        used.update(
            member["character_id"] for p in config.get("presentations", []) for member in p["cast"]
        )
        return [
            f"人物“{characters[cid]['display_name']}”尚未确认，仍保留其编排；请在人物页确认或替换。"
            if cid in characters
            else "编排引用的人物不存在或不属于本项目。"
            for cid in sorted(used)
            if cid not in characters or characters[cid]["status"] != "confirmed"
        ]

    def save(self, pid, revision, config):
        config = presentation.normalize(config)
        self.validate(pid, config)
        presentation.validate(self, pid, config)
        return self.mutate(
            pid, revision, "reader.configure", lambda _db, data: (data.clear(), data.update(config))
        )

    def path(self, pid, aid):
        self.store.get(pid)
        with self.store.db() as db:
            asset = self.review.item(db, "reader_assets", pid, aid)
        path = self.store.project_dir(pid) / "reader-assets" / (aid + ".png")
        if not path.is_file() or sha256(path.read_bytes()) != asset["sha256"]:
            raise ValueError("阅读器图片缺失或已修改，请重新上传。")
        return path

    def upload(self, pid, revision, raw, kind, license_text):
        if not raw or len(raw) > 12_000_000 or not license_text.strip():
            raise ValueError("请提供不超过 12 MB 的图像及来源说明。")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format not in {"PNG", "JPEG", "WEBP"} or max(image.size) > 4096:
                        raise ValueError("仅支持最长边不超过 4096 的 PNG、JPEG 或 WebP。")
                    output = io.BytesIO()
                    image.convert("RGB").save(output, "PNG")
                    content, size = output.getvalue(), image.size
        except (
            OSError,
            UnidentifiedImageError,
            Image.DecompressionBombWarning,
            Image.DecompressionBombError,
        ):
            raise ValueError("图片无法读取。") from None
        aid = str(uuid.uuid4())
        asset = {
            "id": aid,
            "kind": kind,
            "status": "pending",
            "sha256": sha256(content),
            "license": license_text.strip(),
            "width": size[0],
            "height": size[1],
            "origin": "user_upload",
        }
        directory = self.store.project_dir(pid) / "reader-assets"
        directory.mkdir(exist_ok=True)
        path = directory / (aid + ".png")
        path.write_bytes(content)
        path.chmod(0o444)
        try:
            self.mutate(
                pid,
                revision,
                "reader.upload",
                lambda db, _data: self.review.put(db, "reader_assets", pid, asset),
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return asset

    def accept(self, pid, revision, aid, status):
        if status == "accepted":
            self.path(pid, aid)

        def update(db, _data):
            asset = self.review.item(db, "reader_assets", pid, aid)
            asset["status"] = status
            self.review.put(db, "reader_assets", pid, asset)

        self.mutate(pid, revision, "reader.asset_review", update)

    def sample(self, pid, revision):
        if not self.is_chibi(pid):
            raise ValueError("这组封面、场景和地图只适用于赤壁样例。")
        if self.load(pid)[0] != revision:
            raise ConflictError("阅读器配置已更新，请刷新后重试。")
        files = {
            "cover": ("cover-v1.png", "cover"),
            "tent": ("tent-v2.png", "scene"),
            "altar": ("altar-v1.png", "scene"),
            "fleet": ("fleet-v1.png", "scene"),
            "forest": ("forest-v1.png", "scene"),
            "fire": ("../scenes/chibi-fire-ink-v1.png", "scene"),
        }
        directory = self.store.project_dir(pid) / "reader-assets"
        directory.mkdir(exist_ok=True)
        assets, created = {}, []
        try:
            with self.store.db() as db:
                existing = self.review.rows(db, "reader_assets", pid)
            if any(not (REPO / "samples/reader" / name).is_file() for name, _kind in files.values()):
                raise ValueError("本机没有赤壁原始素材；请导入完整赤壁工程，或上传自己的图片。")
            for key, (name, kind) in files.items():
                content = (REPO / "samples/reader" / name).read_bytes()
                digest = sha256(content)
                reusable = next(
                    (a for a in existing if a.get("sample_key") == key and a["sha256"] == digest),
                    None,
                )
                if reusable:
                    self.path(pid, reusable["id"])
                    assets[key] = reusable
                    continue
                with Image.open(io.BytesIO(content)) as image:
                    size = image.size
                    image.verify()
                aid = str(uuid.uuid4())
                assets[key] = {
                    "id": aid,
                    "kind": kind,
                    "status": "pending",
                    "sha256": digest,
                    "width": size[0],
                    "height": size[1],
                    "sample_key": key,
                    "origin": "codex_imagegen",
                    "license": "Codex 内置生图候选；来源与提示词见 samples/reader/，待制作人审查。",
                }
                path = directory / (aid + ".png")
                path.write_bytes(content)
                path.chmod(0o444)
                created.append(path)
            blocks = self.blocks(pid)
            chars = {
                c["display_name"]: c["id"]
                for c in self.review.state(pid)["characters"]
                if c["status"] == "confirmed"
            }
            specs = [
                (None, "帐中问疾", "tent", ["孔明", "周瑜"]),
                ("孔明辭別出帳", "南屏山·祭风", "altar", ["孔明"]),
                ("且說周瑜請程普", "江上待风", "tent", ["周瑜"]),
                ("是日看看近夜", "东风起", "fleet", []),
                ("話分兩頭", "夏口军帐", "tent", ["孔明"]),
                ("卻說曹操在大寨中", "江北水寨", "fleet", []),
                ("黃蓋用刀一招", "火起江面", "fire", []),
                ("縱馬加鞭", "山林败走", "forest", []),
                ("於是引眾入南郡", "南郡歇兵", "tent", []),
                ("卻說關雲長放了曹操", "夏口复命", "tent", ["孔明"]),
            ]
            scenes = []
            for marker, title, key, cast in specs:
                block = (
                    blocks[0] if marker is None else next(b for b in blocks if marker in b["text"])
                )
                scenes.append(
                    {
                        "id": str(uuid.uuid4()),
                        "title": title,
                        "start_byte": block["byte_start"],
                        "asset_id": assets[key]["id"],
                        "character_ids": [chars[n] for n in cast if n in chars],
                    }
                )
            config = {
                "title": "赤壁",
                "subtitle": "七星坛祭风 · 三江口纵火",
                "cover_asset_id": assets["cover"]["id"],
                "scenes": scenes,
                "map_profile": "chibi",
            }

            def update(db, data):
                for asset in assets.values():
                    self.review.put(db, "reader_assets", pid, asset)
                data.clear()
                data.update(config)

            self.mutate(pid, revision, "reader.sample", update)
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise
        return self.state(pid)

    def content(self, pid, strict=False):
        blocks = self.blocks(pid)
        revision, config = self.load(pid)
        self.validate(pid, config, check_characters=strict)
        presentation.validate(self, pid, config, for_restore=not strict)
        review = self.review.state(pid)
        speech = self.speech.state(pid)
        media, issues = {}, self.publication_issues(pid, config, review)
        if not config.get("presentations") and any(
            len(s["character_ids"]) > 2 for s in config["scenes"]
        ):
            if strict:
                raise ValueError("旧场景超过两名人物，请在章节编排中明确左右在场人物后导出。")
            issues.append("旧场景超过两名人物，预览暂取前两名；请在章节编排明确选择后导出。")
        with self.store.db() as db:
            assets = {a["id"]: a for a in self.review.rows(db, "reader_assets", pid)}
        used = {s["asset_id"] for s in config["scenes"]}
        used.update(p["image_asset_id"] for p in config.get("presentations", []))
        used.update(p["image_asset_id"] for p in config.get("illustrations", []))
        if config["cover_asset_id"]:
            used.add(config["cover_asset_id"])
        for aid in used:
            asset = assets[aid]
            try:
                self.path(pid, aid)
                if strict and asset["status"] != "accepted":
                    raise ValueError("封面或场景图片尚未接受，请在阅读器配置页审查。")
                if asset["status"] == "rejected":
                    raise ValueError("当前配置使用了已拒绝的图片，请替换素材。")
                media[aid] = asset | {
                    "url": f"/api/projects/{pid}/reader/assets/{aid}",
                    "type": "image",
                }
            except ValueError as exc:
                if strict:
                    raise
                issues.append(str(exc))
        characters = {}
        references = {
            a["character_id"]
            for a in review["assets"]
            if a["status"] == "accepted" and a["kind"] in {"reference", "reference_and_figure"}
        }
        figures = {
            a["id"]: a
            for a in review["assets"]
            if a["status"] == "accepted" and a["kind"] != "reference"
        }
        for char in review["characters"]:
            if char["status"] != "confirmed":
                continue
            aid = char["active_figure_id"]
            figure = figures.get(aid) if char["id"] in references else None
            if figure and figure["character_id"] != char["id"]:
                raise ValueError("立绘角色关联不正确。")
            if figure:
                try:
                    self.review.asset_path(pid, aid)
                    media[aid] = figure | {"type": "figure"}
                except ValueError as exc:
                    if strict:
                        raise
                    issues.append(str(exc))
            characters[char["id"]] = {
                "id": char["id"],
                "name": char["display_name"],
                "figure_id": aid if figure and aid in media else None,
            }
        for p in config.get("presentations", []):
            for member in p["cast"]:
                aid = member["figure_asset_id"]
                figure = next((a for a in review["assets"] if a["id"] == aid), None)
                if not figure or figure["status"] == "rejected":
                    if strict:
                        raise ValueError("呈现立绘已失效。")
                    issues.append("部分呈现立绘已失效。")
                    continue
                try:
                    if member["character_id"] not in references:
                        raise ValueError("呈现人物尚无已接受参考图。")
                    if not strict and figure["status"] != "accepted":
                        issues.append("呈现立绘仍待接受，请到人物页审查。")
                    if strict and figure["status"] != "accepted":
                        raise ValueError("呈现立绘尚未接受。")
                    self.review.asset_path(pid, aid)
                    media[aid] = figure | {"type": "figure"}
                except ValueError as exc:
                    if strict:
                        raise
                    issues.append(str(exc))
        audio = []
        for line in speech["lines"]:
            if not line["selected"]:
                continue
            if not line["eligible"] or not line["profile"]:
                if strict:
                    raise ValueError("已选语音的角色归属或音色无效，请修正或取消配音。")
                issues.append("部分配音的角色或音色需要修正，正文仍可阅读。")
                continue
            for segment in line["segments"]:
                take = segment["accepted"]
                if not take:
                    if strict:
                        raise ValueError("已选配音尚未接受或已经过期。")
                    issues.append("部分已选语音尚未接受或已过期，暂不播放。")
                    continue
                try:
                    self.speech.path(pid, take)
                except ValueError as exc:
                    if strict:
                        raise
                    issues.append(str(exc))
                    continue
                media[take["id"]] = take | {"type": "audio"}
                audio.append(
                    {
                        "take_id": take["id"],
                        "byte_start": segment["byte_start"],
                        "byte_end": segment["byte_end"],
                        "speaker_id": line["speaker_id"],
                        "duration": take["duration"],
                    }
                )
        dialogues = [
            d
            for d in review["dialogues"]
            if d["status"] == "reviewed" and d["speaker_id"] in characters
        ]
        raw = self.review.source(pid)
        for block in blocks:
            start, end = block["byte_start"], block["byte_end"]
            ds = [d for d in dialogues if d["outer_start"] < end and d["outer_end"] > start]
            clips = [a for a in audio if a["byte_start"] < end and a["byte_end"] > start]
            boundaries = sorted(
                {
                    start,
                    end,
                    *(
                        p["start_byte"]
                        for p in config.get("presentations", [])
                        if start < p["start_byte"] < end
                    ),
                    *(max(start, d["outer_start"]) for d in ds),
                    *(min(end, d["outer_end"]) for d in ds),
                    *(max(start, a["byte_start"]) for a in clips),
                    *(min(end, a["byte_end"]) for a in clips),
                }
            )
            runs = []
            for left, right in itertools.pairwise(boundaries):
                d = next(
                    (d for d in ds if d["outer_start"] <= left and d["outer_end"] >= right), None
                )
                clip = next(
                    (a for a in clips if a["byte_start"] <= left and a["byte_end"] >= right), None
                )
                runs.append(
                    {
                        "byte_start": left,
                        "byte_end": right,
                        "text": raw[left:right].decode(),
                        "speaker_id": d["speaker_id"] if d else None,
                        "take_id": clip["take_id"] if clip else None,
                    }
                )
            if "".join(r["text"] for r in runs) != block["text"]:
                raise ValueError("阅读器文字片段回拼失败。")
            block.update(runs=runs, audio=clips)
        map_data = None
        if config["map_profile"] == "chibi":
            map_data = json.loads((REPO / "samples/reader/chibi-map.json").read_text())
            fire = next(b for b in blocks if "黃蓋用刀一招" in b["text"])
            retreat = next(b for b in blocks if "縱馬加鞭" in b["text"])
            for phase, key in zip(map_data["phases"], ["opposition", "fire", "retreat"]):
                phase["id"] = key
            map_data["phase_anchors"] = [
                blocks[0]["byte_start"],
                fire["byte_start"] + len(fire["text"].split("黃蓋用刀一招")[0].encode()),
                retreat["byte_start"],
            ]
        with self.store.db() as db:
            production_revision = self.version_state(db, pid)["production_revision"]
        versions = {
            "reader_revision": revision,
            "review_revision": review["revision"],
            "speech_revision": speech["revision"],
            "production_revision": production_revision,
        }
        presentations = config.get("presentations") or presentation.legacy_presentations(
            config, characters
        )
        return {
            "schema_version": 3 if config.get("illustrations") else 2,
            "presentations": presentations,
            "map_entries": config.get("map_entries", []),
            "project": {
                k: self.store.get(pid)[k]
                for k in [
                    "id",
                    "filename",
                    "sha256",
                    "canonical_sha256",
                    "rights_status",
                    "character_count",
                ]
            },
            "versions": versions,
            "config": config,
            "blocks": blocks,
            "characters": characters,
            "media": media,
            "map": map_data,
            "issues": sorted(set(issues)),
            "preview": bool(issues)
            or any(a["status"] != "accepted" for a in assets.values() if a["id"] in used)
            or any(a.get("status") != "accepted" for a in media.values() if a["type"] == "figure"),
            "checks": {"source": True, "paragraph_text": True},
        }
