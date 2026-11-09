from typing import Annotated, Literal

from fastapi import BackgroundTasks, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .reader import Reader
from .reader_editorial import Editorial
from .reader_presentation import chibi


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=80)
    start_byte: int = Field(ge=0)
    asset_id: str
    character_ids: list[str] = Field(default_factory=list, max_length=3)


class Cast(BaseModel):
    model_config = ConfigDict(extra="forbid")
    character_id: str
    figure_asset_id: str
    slot: Literal["left", "right"]


class Presentation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    start_byte: int = Field(ge=0)
    scene_id: str
    kind: Literal["environment", "dialogue", "event"]
    image_asset_id: str
    place_label: str = Field(default="", max_length=80)
    time_label: str = Field(default="", max_length=40)
    cast: list[Cast] = Field(default_factory=list, max_length=2)


class MapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    byte_start: int = Field(ge=0)
    byte_end: int = Field(ge=0)
    label: str = Field(min_length=1, max_length=80)
    phase_id: Literal["opposition", "fire", "retreat"]
    place_ids: list[str] = Field(default_factory=list, max_length=10)


class Illustration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    after_byte: int = Field(ge=0)
    image_asset_id: str
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)


class Issue(Input):
    id: str | None = None
    anchor: int = Field(ge=0)
    category: Literal["visual", "cast", "audio", "map", "reading"]
    note: str = Field(min_length=1, max_length=2000)
    state: Literal["open", "resolved", "deferred"] = "open"
    reason: str = Field(default="", max_length=1000)


class Configuration(Input):
    title: str = Field(min_length=1, max_length=180)
    subtitle: str = Field(default="", max_length=180)
    cover_asset_id: str | None = None
    scenes: list[Scene] = Field(default_factory=list, max_length=64)
    map_profile: Literal["chibi"] | None = None
    presentations: list[Presentation] = Field(default_factory=list, max_length=512)
    map_entries: list[MapEntry] = Field(default_factory=list, max_length=128)
    reading_layout: Literal["split", "illustrated"] = "split"
    illustrations: list[Illustration] = Field(default_factory=list, max_length=64)


class Acceptance(Input):
    status: Literal["pending", "accepted", "rejected"]


def mount_reader(app, store, review, speech):
    reader = Reader(store, review, speech)
    app.state.reader = reader
    editorial = Editorial(reader)
    reader.editorial = editorial

    @app.get("/api/projects/{pid}/reader/editorial")
    def editorial_state(pid: str):
        return editorial.state(pid)

    @app.post("/api/projects/{pid}/reader/editorial")
    def editorial_save(pid: str, body: Issue):
        return editorial.save(pid, body.revision, body.model_dump(exclude={"revision"}))

    @app.post("/api/projects/{pid}/reader/choreography/sample")
    def choreography(pid: str, body: Input):
        _, config = reader.load(pid)
        reader.save(pid, body.revision, chibi(reader, pid, config))
        return reader.state(pid)

    @app.post("/api/projects/{pid}/reader/choreography/expanded-sample")
    def expanded_choreography(pid: str, body: Input):
        from .reader_casting import expanded_chibi

        _, config = reader.load(pid)
        reader.save(pid, body.revision, expanded_chibi(reader, pid, config))
        return reader.state(pid)

    @app.post("/api/projects/{pid}/reader/choreography/second-sample")
    def second_choreography(pid: str, body: Input):
        from .reader_casting import expanded_chibi

        _, config = reader.load(pid)
        reader.save(pid, body.revision, expanded_chibi(reader, pid, config, second_batch=True))
        return reader.state(pid)

    @app.post("/api/projects/{pid}/reader/narrative/sample")
    def narrative_import(pid: str, body: Input):
        from .reader_narrative import import_candidates

        return import_candidates(reader, pid, body.revision)

    @app.post("/api/projects/{pid}/reader/choreography/narrative-sample")
    def narrative_choreography(pid: str, body: Input):
        from .reader_narrative import narrative_chibi

        _, config = reader.load(pid)
        reader.save(pid, body.revision, narrative_chibi(reader, pid, config))
        return reader.state(pid)

    @app.get("/api/projects/{pid}/reader")
    def state(pid: str):
        return reader.state(pid)

    @app.get("/api/projects/{pid}/reader/content")
    def content(pid: str):
        return reader.content(pid)

    @app.patch("/api/projects/{pid}/reader")
    def configure(pid: str, body: Configuration):
        reader.save(pid, body.revision, body.model_dump(exclude={"revision"}))
        return {"saved": True}

    @app.post("/api/projects/{pid}/reader/sample")
    def sample(pid: str, body: Input):
        return reader.sample(pid, body.revision)

    @app.post("/api/projects/{pid}/reader/assets", status_code=201)
    async def upload(
        pid: str,
        revision: Annotated[int, Form()],
        kind: Annotated[Literal["cover", "scene"], Form()],
        license_text: Annotated[str, Form(max_length=1000)],
        file: Annotated[UploadFile, File()],
    ):
        return reader.upload(pid, revision, await file.read(12_000_001), kind, license_text)

    @app.patch("/api/projects/{pid}/reader/assets/{aid}")
    def accept(pid: str, aid: str, body: Acceptance):
        reader.accept(pid, body.revision, aid, body.status)
        return {"saved": True}

    @app.get("/api/projects/{pid}/reader/assets/{aid}")
    def image(pid: str, aid: str):
        return FileResponse(reader.path(pid, aid), media_type="image/png")

    def work(pid, jid):
        from .reader_export import export_reader

        try:
            store.finish_job(jid, result=export_reader(reader, pid, jid))
        except Exception as exc:  # noqa: BLE001 -- Persist failures and keep published snapshots intact.
            store.finish_job(
                jid,
                error=str(exc)
                if type(exc) is ValueError
                else "阅读器导出未完成，请检查磁盘空间后重试。",
            )

    @app.post("/api/projects/{pid}/reader/exports", status_code=202)
    def export(pid: str, background: BackgroundTasks):
        jid = store.start_job(pid, "reader_export")
        background.add_task(work, pid, jid)
        return {"job_id": jid}

    return reader
