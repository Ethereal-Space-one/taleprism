from typing import Annotated, Literal

from fastapi import File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .visual import REPO, Visual


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Version(Strict):
    revision: int = Field(ge=0)


class Node(Strict):
    id: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=20)
    evidence_span_ids: list[int] = Field(min_length=1, max_length=100)


class Edge(Strict):
    from_id: str
    to_id: str
    label: str = Field(min_length=1, max_length=20)
    evidence_span_ids: list[int] = Field(min_length=1, max_length=100)
    directed: bool = False


class Graph(Strict):
    nodes: list[Node] = Field(min_length=1, max_length=4)
    edges: list[Edge] = Field(default_factory=list, max_length=6)


class Item(Version):
    kind: Literal["illustration", "diagram"]
    title: str = Field(min_length=1, max_length=80)
    anchor_byte: int = Field(ge=0)
    evidence_span_ids: list[int] = Field(min_length=1, max_length=100)
    graph: Graph | None = None


class Settings(Version):
    style: Literal["ink", "gongbi", "cel"]
    budget: int = Field(ge=0, le=6)


class Approval(Version):
    status: Literal["accepted", "draft", "rejected"]
    enabled: bool = False
    evidence_confirmed: bool = False


def mount_visual(app, store, review):
    visual = Visual(store, review)
    app.state.visual = visual

    @app.get("/api/projects/{pid}/visual")
    def state(pid: str):
        return visual.state(pid)

    @app.patch("/api/projects/{pid}/visual/settings")
    def settings(pid: str, body: Settings):
        visual.settings(pid, body.revision, body.style, body.budget)
        return {"saved": True}

    @app.post("/api/projects/{pid}/visual/propose")
    def propose(pid: str, body: Version):
        return visual.propose(pid, body.revision)

    @app.post("/api/projects/{pid}/visual/items", status_code=201)
    def create(pid: str, body: Item):
        return visual.save(pid, body.revision, body.model_dump(exclude={"revision"}))

    @app.put("/api/projects/{pid}/visual/items/{item_id}")
    def update(pid: str, item_id: str, body: Item):
        return visual.save(pid, body.revision, body.model_dump(exclude={"revision"}), item_id)

    @app.post("/api/projects/{pid}/visual/items/{item_id}/render")
    def render(pid: str, item_id: str, body: Version):
        state = visual.state(pid)
        if not any(i["id"] == item_id and i["kind"] == "diagram" for i in state["items"]):
            raise ValueError("此入口仅用于程序图解。")
        return visual.asset(pid, body.revision, item_id)

    @app.post("/api/projects/{pid}/visual/items/{item_id}/upload", status_code=201)
    async def upload(
        pid: str,
        item_id: str,
        file: Annotated[UploadFile, File()],
        revision: Annotated[int, Form()],
        license_text: Annotated[str, Form()],
    ):
        if not any(
            i["id"] == item_id and i["kind"] == "illustration" for i in visual.state(pid)["items"]
        ):
            raise ValueError("此入口仅接收情节插图；图解请使用程序生成。")
        return visual.asset(pid, revision, item_id, await file.read(12_000_001), license_text)

    @app.post("/api/projects/{pid}/visual/items/{item_id}/codex-sample", status_code=201)
    def sample(pid: str, item_id: str, body: Version):
        state = visual.state(pid)
        item = next((i for i in state["items"] if i["id"] == item_id), None)
        if not item:
            raise KeyError()
        source = "".join(e["quote"] for e in item["evidence"])
        if (
            state["style"] != "ink"
            or item["kind"] != "illustration"
            or "船" not in source
            or not any(t in source for t in ["火船", "發火", "发火"])
        ):
            raise ValueError("本候选只适用于有火船／船只发火证据的水墨淡彩插图。")
        return visual.asset(
            pid,
            body.revision,
            item_id,
            (REPO / "samples/scenes/chibi-fire-ink-v1.png").read_bytes(),
            "Codex 内置 image_gen 生成；本地情节图候选，需人工核对原文与使用范围。",
            origin="codex_imagegen",
        )

    @app.patch("/api/projects/{pid}/visual/items/{item_id}/review")
    def approve(pid: str, item_id: str, body: Approval):
        visual.accept(
            pid, body.revision, item_id, body.status, body.enabled, body.evidence_confirmed
        )
        return {"saved": True}

    @app.get("/api/projects/{pid}/visual/assets/{asset_id}.png")
    def image(pid: str, asset_id: str):
        return FileResponse(visual.path(pid, asset_id), media_type="image/png")

    @app.get("/api/projects/{pid}/visual/assets/{asset_id}.svg")
    def svg(pid: str, asset_id: str):
        return FileResponse(
            visual.path(pid, asset_id, True),
            media_type="image/svg+xml",
            headers={
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"
            },
        )

    @app.post("/api/projects/{pid}/visual/sample-diagram", status_code=201)
    def example(pid: str, body: Version):
        spans = store.parts(pid, "spans")
        text = visual.review.source(pid).decode()
        paragraph = next(
            (
                m
                for m in __import__("re").finditer(r"[^\r\n]+", text)
                if "曹操與張遼" in m[0] and "烏林" in m[0]
            ),
            None,
        )
        if not paragraph:
            raise ValueError(
                "此样例仅适用于包含「曹操與張遼」与「烏林」原文段落的项目。可导入赤壁样例。"
            )
        start = len(text[: paragraph.start()].encode())
        end = start + len(paragraph[0].rstrip(" \t\u3000").encode())
        ids = [
            s["id"]
            for s in spans
            if start <= s["byte_start"] and s["byte_end"] <= end and s["kind"] != "whitespace"
        ]
        anchor = next(u["byte_end"] for u in review.presentation(pid)[0] if u["byte_end"] >= end)
        graph = {
            "nodes": [
                {"id": key, "label": label, "evidence_span_ids": ids}
                for key, label in [("cao", "曹操"), ("zhang", "張遼"), ("wulin", "烏林")]
            ],
            "edges": [
                {
                    "from_id": "cao",
                    "to_id": "zhang",
                    "label": "與",
                    "evidence_span_ids": ids,
                    "directed": False,
                },
                {
                    "from_id": "cao",
                    "to_id": "wulin",
                    "label": "奔",
                    "evidence_span_ids": ids,
                    "directed": True,
                },
            ],
        }
        return visual.save(
            pid,
            body.revision,
            {
                "kind": "diagram",
                "title": "曹操、張遼與烏林：原文示意",
                "anchor_byte": anchor,
                "evidence_span_ids": ids,
                "graph": graph,
            },
        )

    return visual
