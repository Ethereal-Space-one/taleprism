import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .bundles import mount_bundles
from .delivery import Delivery
from .exporter import REPO, export_project
from .production import mount_production
from .reader_api import mount_reader
from .review_api import mount_review
from .settings import load_env
from .speech_api import mount_speech
from .storage import Store
from .text import MAX_BYTES, sha256
from .visual_api import mount_visual


def create_app(data_dir: Path | None = None) -> FastAPI:
    load_env(REPO / ".env")
    store = Store(data_dir or Path(os.environ.get("STORYGAL_DATA_DIR", REPO / "data")))

    @asynccontextmanager
    async def lifespan(_app):
        import fcntl

        with (store.root / ".instance.lock").open("a") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("此数据目录已有工作台正在运行，请使用已打开的窗口。") from None
            try:
                store.recover_interrupted()
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    app = FastAPI(title="Taleprism", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    review = mount_review(app, store)
    speech = mount_speech(app, store, review)
    visual = mount_visual(app, store, review)
    reader = mount_reader(app, store, review, speech)
    mount_production(app, reader)
    mount_bundles(app)
    delivery = Delivery(store, review, speech, visual, reader)
    app.state.delivery = delivery

    class DeliveryReview(BaseModel):
        model_config = ConfigDict(extra="forbid")
        checks: dict[str, bool]
        notes: str = Field(default="", max_length=2000)

    @app.get("/api/projects/{pid}/delivery")
    def delivery_state(pid: str):
        return delivery.state(pid)

    @app.post("/api/projects/{pid}/exports/{eid}/review")
    def delivery_review(pid: str, eid: str, body: DeliveryReview):
        return delivery.accept(pid, eid, body.checks, body.notes)

    @app.exception_handler(ValueError)
    async def invalid(_request, exc):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(KeyError)
    async def missing(_request, _exc):
        return JSONResponse(status_code=404, content={"detail": "项目或文件不存在。"})

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "version": "0.1.0",
            "engine_available": (REPO / "engine/webgal-4.6.5/index.html").exists(),
        }

    @app.get("/api/projects")
    def projects():
        return store.list_projects()

    @app.post("/api/projects", status_code=201)
    async def upload(
        file: Annotated[UploadFile, File()],
        rights_status: Annotated[str, Form()],
        encoding: Annotated[str, Form()] = "auto",
    ):
        if not (file.filename or "").lower().endswith(".txt"):
            raise ValueError("当前仅支持 TXT 文件。")
        raw = await file.read(MAX_BYTES + 1)
        return store.create(raw, file.filename or "source.txt", rights_status, encoding)

    @app.post("/api/samples/chibi", status_code=201)
    def sample():
        path = REPO / "samples/sanguo-chibi/三國演義_第049-050回_赤壁.txt"
        return store.create(path.read_bytes(), path.name, "public_domain", "utf-8")

    @app.post("/api/samples/last-light", status_code=201)
    def modern_sample():
        path = REPO / "samples/last-light/source.txt"
        return store.create(path.read_bytes(), "末班灯.txt", "owned", "utf-8")

    @app.get("/api/projects/{project_id}")
    def project(project_id: str):
        return store.get(project_id)

    @app.get("/api/projects/{project_id}/text")
    def text(project_id: str):
        store.verify(project_id)
        return {
            "text": (store.project_dir(project_id) / "source.utf8.txt")
            .read_bytes()
            .decode("utf-8"),
            "spans": store.parts(project_id, "spans"),
            "units": review.presentation(project_id)[0],
        }

    @app.get("/api/projects/{project_id}/source")
    def source(project_id: str):
        metadata = store.get(project_id)
        store.verify(project_id)
        return FileResponse(
            store.project_dir(project_id) / "original.txt", filename=metadata["filename"]
        )

    @app.post("/api/projects/{project_id}/verify")
    def verify(project_id: str):
        return store.verify(project_id)

    def run_export(project_id: str, job_id: str):
        try:
            result = export_project(store, project_id, job_id)
            store.finish_job(job_id, result=result)
        except Exception as exc:  # noqa: BLE001 -- Record all worker failures for retry in the UI.
            store.finish_job(
                job_id,
                error=str(exc)
                if type(exc) is ValueError
                else "导出未完成，临时产物已清理。请检查磁盘空间后重试。",
            )

    @app.post("/api/projects/{project_id}/exports", status_code=202)
    def export(project_id: str, background: BackgroundTasks, simplified: bool = False):
        _, config = reader.load(project_id)
        if (config.get("presentations") or config.get("map_entries")) and not simplified:
            raise ValueError(
                "本项目包含段内人物编排、事件呈现或地图入口，WebGAL 将简化为原有逐框表现。请优先导出独立阅读器，或明确选择简化导出。"
            )
        job_id = store.start_job(project_id)
        background.add_task(run_export, project_id, job_id)
        return {"job_id": job_id, "state": "running"}

    @app.get("/api/projects/{project_id}/jobs")
    def jobs(project_id: str):
        return store.jobs(project_id)

    def export_path(project_id: str, export_id: str) -> Path:
        store.get(project_id)
        try:
            if str(uuid.UUID(export_id)) != export_id:
                raise ValueError()
        except ValueError:
            raise KeyError() from None
        delivery.completed(project_id, export_id)
        path = store.project_dir(project_id) / "exports" / export_id
        if not path.is_dir():
            raise KeyError()
        return path

    @app.get("/api/projects/{project_id}/exports/{export_id}/download")
    def download(project_id: str, export_id: str):
        directory = export_path(project_id, export_id)
        archive = directory.with_suffix(".zip")
        job = delivery.completed(project_id, export_id)
        if not archive.is_file():
            raise ValueError("成品压缩包缺失，请重新导出。")
        expected = job["result"].get("archive_sha256")
        if expected and sha256(archive.read_bytes()) != expected:
            raise ValueError("成品压缩包校验失败，请重新导出。")
        return FileResponse(
            archive,
            filename="storygal-reader.zip"
            if job["kind"] == "reader_export"
            else "storygal-webgal.zip",
        )

    @app.get("/play/{project_id}/{export_id}/{asset_path:path}")
    def play(project_id: str, export_id: str, asset_path: str):
        directory = export_path(project_id, export_id).resolve()
        asset = (directory / asset_path).resolve()
        if not asset.is_relative_to(directory) or not asset.is_file():
            raise HTTPException(404)
        return FileResponse(asset, headers={"Cache-Control": "no-store"})

    dist = REPO / "frontend/dist"

    @app.get("/read/{pid}")
    def read(pid: str):
        store.get(pid)
        if not (dist / "index.html").is_file():
            raise ValueError("阅读器尚未构建，请重新运行启动程序。")
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-store"})

    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
