"""Evidence-bound visual events. Immutable assets, explicit acceptance, no source edits."""

import io
import json
import math
import re
import uuid
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from .review import ConflictError, Review
from .text import sha256

STYLES = {
    "ink": {
        "name": "水墨淡彩",
        "prompt": "Chinese ink-and-watercolor narrative illustration, restrained indigo and warm parchment tones, fine brush texture",
        "paper": "#f4eee0",
        "ink": "#263b3a",
    },
    "gongbi": {
        "name": "古典工笔",
        "prompt": "Chinese gongbi narrative illustration, precise fine linework, mineral pigments and restrained cinnabar details",
        "paper": "#f7efdf",
        "ink": "#603d32",
    },
    "cel": {
        "name": "柔和赛璐璐",
        "prompt": "original historical visual novel illustration, refined linework and soft cel shading, subdued colors",
        "paper": "#e9eff3",
        "ink": "#283d57",
    },
}
REPO = Path(__file__).resolve().parents[3]


def canonical_hash(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def render_diagram(graph: dict, style: str) -> tuple[bytes, bytes]:
    """SVG and PNG share coordinates and labels; no generated model text."""
    palette = STYLES[style]
    font_path = REPO / "engine/webgal-4.6.5/assets/SourceHanSerifCN-Regular-B_f-kQ2u.ttf"
    if not font_path.exists():
        raise ValueError("缺少中文绘图字体，请先下载固定版本 WebGAL 引擎。")
    fonts = {s: ImageFont.truetype(str(font_path), s) for s in [24, 28, 34, 42]}
    image = Image.new("RGB", (1920, 1080), palette["paper"])
    draw = ImageDraw.Draw(image)
    svg = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width="1920",
        height="1080",
        viewBox="0 0 1920 1080",
    )
    ET.SubElement(svg, "rect", width="1920", height="1080", fill=palette["paper"])

    def text(x, y, value, size=28, centered=False):
        width = draw.textlength(value, font=fonts[size])
        left = x - width / 2 if centered else x
        draw.text((left, y), value, fill=palette["ink"], font=fonts[size])
        node = ET.SubElement(
            svg,
            "text",
            x=str(x),
            y=str(y + size),
            fill=palette["ink"],
            attrib={
                "font-size": str(size),
                "font-family": "Source Han Serif CN, serif",
                "text-anchor": "middle" if centered else "start",
            },
        )
        node.text = value

    text(120, 70, "根据原文整理的示意图", 42)
    text(120, 145, "关系与行动示意；不表示真实地理方位、距离或比例。", 28)
    nodes = graph["nodes"]
    positions = {
        n["id"]: (240 + i * (1440 / max(1, len(nodes) - 1)) if len(nodes) > 1 else 960, 540)
        for i, n in enumerate(nodes)
    }
    for i, edge in enumerate(graph["edges"]):
        x1, y1 = positions[edge["from_id"]]
        x2, y2 = positions[edge["to_id"]]
        distance = abs(x2 - x1)
        control_y = 540 - (170 + (i % 3) * 90) if i % 2 == 0 else 540 + (170 + (i % 3) * 90)
        points = []
        for step in range(81):
            t = step / 80
            points.append(
                (
                    (1 - t) ** 2 * x1 + 2 * (1 - t) * t * ((x1 + x2) / 2) + t * t * x2,
                    (1 - t) ** 2 * y1 + 2 * (1 - t) * t * control_y + t * t * y2,
                )
            )
        # Endpoints stop at node boundaries so arrows remain visible.
        cut = min(0.3, 135 / max(distance, 1))
        points = points[int(cut * 80) : int((1 - cut) * 80) + 1]
        draw.line(points, fill=palette["ink"], width=4)
        ET.SubElement(
            svg,
            "polyline",
            points=" ".join(f"{x:.1f},{y:.1f}" for x, y in points),
            fill="none",
            stroke=palette["ink"],
            attrib={"stroke-width": "4"},
        )
        if edge.get("directed", False):
            end, prev = points[-1], points[-3]
            angle = math.atan2(end[1] - prev[1], end[0] - prev[0])
            arrow = [
                end,
                (end[0] - 22 * math.cos(angle - 0.5), end[1] - 22 * math.sin(angle - 0.5)),
                (end[0] - 22 * math.cos(angle + 0.5), end[1] - 22 * math.sin(angle + 0.5)),
            ]
            draw.polygon(arrow, fill=palette["ink"])
            ET.SubElement(
                svg,
                "polygon",
                points=" ".join(f"{x:.1f},{y:.1f}" for x, y in arrow),
                fill=palette["ink"],
            )
        middle = points[len(points) // 2]
        text(middle[0], middle[1] - 44, edge["label"], 28, True)
    for node in nodes:
        x, y = positions[node["id"]]
        box = (x - 135, y - 75, x + 135, y + 75)
        draw.rounded_rectangle(
            box, radius=12, fill=palette["paper"], outline=palette["ink"], width=3
        )
        ET.SubElement(
            svg,
            "rect",
            x=str(x - 135),
            y=str(y - 75),
            width="270",
            height="150",
            rx="12",
            fill=palette["paper"],
            stroke=palette["ink"],
            attrib={"stroke-width": "3"},
        )
        parts = [node["label"][n : n + 7] for n in range(0, len(node["label"]), 7)]
        for row, part in enumerate(parts):
            text(x, y - 28 + row * 40 - (len(parts) - 1) * 20, part, 34, True)
    text(120, 925, "标签及连线均绑定原文引句，需在制作台逐项审核。", 28)
    text(120, 985, "图示布局仅为阅读辅助，不增加原文事实。", 24)
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return ET.tostring(svg, encoding="utf-8", xml_declaration=True), stream.getvalue()


class Visual:
    def __init__(self, store, review: Review):
        self.store, self.review = store, review
        with store.db() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS visual_states(project_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,data TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS visual_assets(project_id TEXT,id TEXT,data TEXT NOT NULL,PRIMARY KEY(project_id,id));
            """)

    def load(self, pid):
        self.store.get(pid)
        with self.store.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO visual_states VALUES (?,0,?)",
                (pid, json.dumps({"style": "ink", "budget": 3, "items": []})),
            )
            row = db.execute(
                "SELECT revision,data FROM visual_states WHERE project_id=?", (pid,)
            ).fetchone()
        return row[0], json.loads(row[1])

    def mutate(self, pid, revision, action, fn, asset_record=None):
        self.load(pid)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT revision,data FROM visual_states WHERE project_id=?", (pid,)
            ).fetchone()
            if row[0] != revision:
                raise ConflictError("视觉计划已更新，请刷新后重试。")
            data = json.loads(row[1])
            before = json.loads(row[1])
            result = fn(data)
            if asset_record:
                self.review.put(db, "visual_assets", pid, asset_record)
            db.execute(
                "UPDATE visual_states SET revision=revision+1,data=? WHERE project_id=?",
                (json.dumps(data, ensure_ascii=False), pid),
            )
            self.review.audit(db, pid, action, before, data)
        return result

    def refs(self, pid, ids):
        spans = {s["id"]: s for s in self.store.parts(pid, "spans")}
        if (
            not ids
            or len(ids) > 100
            or any(i not in spans or spans[i]["kind"] == "whitespace" for i in ids)
        ):
            raise ValueError("请选择 1–100 条有效原文引句。")
        return [spans[i] for i in sorted(set(ids))]

    def proof(self, pid, ids, label=None):
        refs = self.refs(pid, ids)
        if label and (
            not label.strip() or len(label) > 20 or not any(label in s["text"] for s in refs)
        ):
            raise ValueError("标签须为原文引句中逐字出现的 1–20 个字符。")
        return refs

    def validate(self, pid, item):
        if item["kind"] not in {"illustration", "diagram"}:
            raise ValueError("视觉项目类型不支持。")
        if (item["kind"] == "diagram") != (item.get("graph") is not None):
            raise ValueError("图解必须有节点与连线定义；插图不应附带图解定义。")
        refs = self.refs(pid, item["evidence_span_ids"])
        if item["kind"] == "diagram":
            graph = item["graph"]
            nodes = graph["nodes"]
            edges = graph["edges"]
            if not 1 <= len(nodes) <= 4 or len(edges) > 6:
                raise ValueError("图解限制为 1–4 个节点、最多 6 条连线。")
            if len({n["id"] for n in nodes}) != len(nodes) or any(
                not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", n["id"]) for n in nodes
            ):
                raise ValueError("节点编号重复或无效。")
            by_id = {n["id"]: n for n in nodes}
            for node in nodes:
                refs += self.proof(pid, node["evidence_span_ids"], node["label"])
            for edge in edges:
                if (
                    edge["from_id"] not in by_id
                    or edge["to_id"] not in by_id
                    or edge["from_id"] == edge["to_id"]
                ):
                    raise ValueError("连线端点无效或存在自环。")
                r = self.proof(pid, edge["evidence_span_ids"], edge["label"])
                for key in ["from_id", "to_id"]:
                    self.proof(pid, edge["evidence_span_ids"], by_id[edge[key]]["label"])
                refs += r
        ends = {u["byte_end"] for u in self.review.presentation(pid)[0]}
        if item["anchor_byte"] not in ends or item["anchor_byte"] < max(
            r["byte_end"] for r in refs
        ):
            raise ValueError("位置必须在显示框结束处，且不能早于任何证据。请后移锚点。")

    @staticmethod
    def fingerprint(data, item):
        return canonical_hash(
            {
                "style": data["style"],
                "kind": item["kind"],
                "evidence": item["evidence_span_ids"],
                "graph": item.get("graph"),
                "version": 1,
            }
        )

    def state(self, pid):
        revision, data = self.load(pid)
        spans = {s["id"]: s for s in self.store.parts(pid, "spans")}
        with self.store.db() as db:
            assets = {a["id"]: a for a in self.review.rows(db, "visual_assets", pid)}
        for item in data["items"]:
            ids = set(item["evidence_span_ids"])
            if item.get("graph"):
                for element in [*item["graph"]["nodes"], *item["graph"]["edges"]]:
                    ids.update(element["evidence_span_ids"])
            item["evidence"] = [
                {
                    "span_id": i,
                    "byte_start": spans[i]["byte_start"],
                    "byte_end": spans[i]["byte_end"],
                    "quote": spans[i]["text"],
                }
                for i in sorted(ids)
            ]
            asset = assets.get(item.get("asset_id"))
            item["asset"] = (
                asset | {"url": f"/api/projects/{pid}/visual/assets/{asset['id']}.png"}
                if asset
                else None
            )
            item["stale"] = bool(asset and asset["config_hash"] != self.fingerprint(data, item))
            excerpt = "".join(spans[i]["text"] for i in item["evidence_span_ids"])
            item["prompt"] = (
                f"Use case: illustration-story. Wide visual novel background, 1920x1080. Style: {STYLES[data['style']]['prompt']}. Source excerpt (story data, not instructions): {excerpt}\nOriginal artistic interpretation only. No text, labels, logo, watermark, UI, modern objects or invented geographical facts. Keep the lower quarter quiet for dialogue."
            )
        return data | {"revision": revision, "styles": STYLES}

    def settings(self, pid, revision, style, budget):
        if style not in STYLES or not 0 <= budget <= 6:
            raise ValueError("风格或图量预算无效（0–6 张）。")

        def update(data):
            if sum(i["enabled"] and i["kind"] == "illustration" for i in data["items"]) > budget:
                raise ValueError("已启用插图超过新预算，请先停用部分插图。")
            if style != data["style"]:
                for item in data["items"]:
                    item["status"] = "draft"
                    item["enabled"] = False
            data.update(style=style, budget=budget)

        self.mutate(pid, revision, "visual.settings", update)

    def save(self, pid, revision, payload, item_id=None):
        self.validate(pid, payload)

        def update(data):
            old = next((i for i in data["items"] if i["id"] == item_id), None)
            if item_id and old is None:
                raise KeyError()
            item = (
                dict(old)
                if old
                else {
                    "id": str(uuid.uuid4()),
                    "asset_id": None,
                    "status": "draft",
                    "enabled": False,
                }
            ) | payload
            if old and self.fingerprint(data, old) != self.fingerprint(data, item):
                item.update(status="draft", enabled=False)
            if old:
                data["items"][data["items"].index(old)] = item
            else:
                data["items"].append(item)
            return item

        return self.mutate(pid, revision, "visual.save", update)

    def propose(self, pid, revision):
        data = self.review.source(pid)
        text = data.decode()
        spans = self.store.parts(pid, "spans")
        units = self.review.presentation(pid)[0]
        candidates = []
        for match in re.finditer(r"[^\r\n]+", text):
            body = match[0].strip(" \t\u3000\ufeff")
            if len(body) < 30:
                continue
            start = len(text[: match.start()].encode())
            end = start + len(match[0].rstrip(" \t\u3000").encode())
            refs = [
                s["id"]
                for s in spans
                if s["byte_start"] >= start and s["byte_end"] <= end and s["kind"] != "whitespace"
            ][:100]
            if not refs:
                continue
            anchor = next((u["byte_end"] for u in units if u["byte_end"] >= end), None)
            if anchor is None:
                continue
            score = 2 if re.search(r"卻說|却说|且說|且说|忽|次日|火船|東風", body[:120]) else 1
            candidates.append(
                (
                    score,
                    {
                        "kind": "illustration",
                        "title": body[:28],
                        "evidence_span_ids": refs,
                        "anchor_byte": anchor,
                        "graph": None,
                    },
                )
            )

        def update(state):
            existing = {
                tuple(i["evidence_span_ids"]) for i in state["items"] if i["kind"] == "illustration"
            }
            added = 0
            for _, candidate in sorted(candidates, key=lambda x: -x[0]):
                if added >= state["budget"]:
                    break
                if tuple(candidate["evidence_span_ids"]) in existing:
                    continue
                state["items"].append(
                    candidate
                    | {
                        "id": str(uuid.uuid4()),
                        "asset_id": None,
                        "status": "draft",
                        "enabled": False,
                    }
                )
                existing.add(tuple(candidate["evidence_span_ids"]))
                added += 1
            return {"added": added}

        return self.mutate(pid, revision, "visual.propose", update)

    def asset(self, pid, revision, item_id, raw=None, license_text="", origin="user_upload"):
        current_revision, data = self.load(pid)
        if current_revision != revision:
            raise ConflictError("视觉计划已更新，请刷新后重试。")
        item = next((i for i in data["items"] if i["id"] == item_id), None)
        if not item:
            raise KeyError()
        fingerprint = self.fingerprint(data, item)
        if item["kind"] == "diagram" and item.get("asset_id"):
            with self.store.db() as db:
                existing = self.review.item(db, "visual_assets", pid, item["asset_id"])
            if existing["config_hash"] == fingerprint:
                try:
                    self.path(pid, existing["id"])
                    self.path(pid, existing["id"], True)
                except ValueError:
                    pass
                else:
                    return existing | {"reused": True}
        svg = None
        if item["kind"] == "diagram":
            self.validate(pid, item)
            svg, content = render_diagram(item["graph"], data["style"])
            license_text = "程序依据本项目原文绘制的示意图；源文本权利状态沿用项目记录。"
            origin = "deterministic_svg"
        else:
            if (
                not raw
                or len(raw) > 12_000_000
                or not license_text.strip()
                or len(license_text) > 1000
            ):
                raise ValueError("需要不超过 12 MB 的图片与来源许可。")
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(raw)) as image:
                        if image.format not in {"PNG", "JPEG", "WEBP"} or max(image.size) > 4096:
                            raise ValueError("图片格式或尺寸无效。")
                        output = io.BytesIO()
                        image.convert("RGB").save(output, "PNG")
                        content = output.getvalue()
            except (
                OSError,
                UnidentifiedImageError,
                Image.DecompressionBombWarning,
                Image.DecompressionBombError,
            ):
                raise ValueError("无法读取图片。") from None
        asset = {
            "id": str(uuid.uuid4()),
            "sha256": sha256(content),
            "svg_sha256": sha256(svg) if svg else None,
            "config_hash": fingerprint,
            "license": license_text.strip(),
            "origin": origin,
        }
        directory = self.store.project_dir(pid) / "visual"
        directory.mkdir(exist_ok=True)

        def update(state):
            target = next((i for i in state["items"] if i["id"] == item_id), None)
            if not target or self.fingerprint(state, target) != fingerprint:
                raise ConflictError("生成期间计划已更新，请重新生成。")
            path = directory / (asset["id"] + ".png")
            path.write_bytes(content)
            path.chmod(0o444)
            if svg:
                path = directory / (asset["id"] + ".svg")
                path.write_bytes(svg)
                path.chmod(0o444)
            target.update(asset_id=asset["id"], status="draft", enabled=False)
            return asset

        try:
            return self.mutate(pid, revision, "visual.asset", update, asset_record=asset)
        except Exception:
            for extension in [".png", ".svg"]:
                path = directory / (asset["id"] + extension)
                if path.exists():
                    path.chmod(0o644)
                    path.unlink()
            raise

    def path(self, pid, asset_id, svg=False):
        self.store.get(pid)
        with self.store.db() as db:
            asset = self.review.item(db, "visual_assets", pid, asset_id)
        path = self.store.project_dir(pid) / "visual" / (asset["id"] + (".svg" if svg else ".png"))
        expected = asset["svg_sha256"] if svg else asset["sha256"]
        if not expected or not path.is_file() or sha256(path.read_bytes()) != expected:
            raise ValueError("视觉资产缺失或已修改，请重新生成或上传。")
        if not svg:
            with Image.open(path) as image:
                image.verify()
        return path

    def accept(self, pid, revision, item_id, status, enabled, evidence_confirmed=False):
        if status not in {"accepted", "draft", "rejected"}:
            raise ValueError("审核状态无效。")
        _, state = self.load(pid)
        item = next((i for i in state["items"] if i["id"] == item_id), None)
        if not item:
            raise KeyError()
        if status == "accepted":
            self.validate(pid, item)
            self.path(pid, item.get("asset_id", ""))
            with self.store.db() as db:
                asset = self.review.item(db, "visual_assets", pid, item["asset_id"])
            if asset["config_hash"] != self.fingerprint(state, item):
                raise ValueError("图像已过期，请重新生成或上传后确认。")
            if item["status"] == "accepted" and item.get("evidence_confirmed"):
                evidence_confirmed = True
            if item["kind"] == "diagram" and not evidence_confirmed:
                raise ValueError("请先逐项核实节点和连线引句，再确认图解。")
        if enabled and status != "accepted":
            raise ValueError("只有已接受项目可以启用。")

        def update(data):
            target = next(i for i in data["items"] if i["id"] == item_id)
            if (
                enabled
                and target["kind"] == "illustration"
                and sum(
                    i["enabled"] and i["kind"] == "illustration" and i["id"] != item_id
                    for i in data["items"]
                )
                >= data["budget"]
            ):
                raise ValueError("启用插图数量超过本章预算。")
            target.update(
                status=status,
                enabled=enabled,
                evidence_confirmed=evidence_confirmed if status == "accepted" else False,
            )

        self.mutate(pid, revision, "visual.review", update)

    def for_export(self, pid, units):
        state = self.state(pid)
        events = []
        for item in state["items"]:
            if not item["enabled"]:
                continue
            if item["status"] != "accepted" or item["stale"] or not item["asset"]:
                raise ValueError("已启用视觉项目未完成确认或已经过期。")
            # A changed pagination may move the anchor later, never earlier than evidence.
            unit = next((u for u in units if u["byte_end"] >= item["anchor_byte"]), None)
            if unit is None:
                raise ValueError("无法解析视觉锚点。")
            self.path(pid, item["asset_id"])
            if item["kind"] == "diagram":
                self.path(pid, item["asset_id"], svg=True)
            events.append(
                {
                    "item_id": item["id"],
                    "kind": item["kind"],
                    "after_unit_id": unit["id"],
                    "asset_id": item["asset_id"],
                }
            )
        return state, events
