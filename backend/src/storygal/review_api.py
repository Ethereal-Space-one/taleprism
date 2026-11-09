from typing import Annotated, Literal

from fastapi import BackgroundTasks, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import llm
from .review import ConflictError, Review


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CharacterInput(Input):
    revision: int = Field(ge=0)
    display_name: str = Field(min_length=1, max_length=40)
    aliases: list[str] = Field(default_factory=list, max_length=40)
    description: str = Field(default="", max_length=2000)
    status: Literal["candidate", "confirmed", "rejected"] = "confirmed"


class MergeInput(Input):
    revision: int = Field(ge=0)
    target_id: str


class AssignmentInput(Input):
    revision: int = Field(ge=0)
    dialogue_ids: list[str] = Field(min_length=1, max_length=500)
    speaker_id: str | None


class AssetInput(Input):
    revision: int = Field(ge=0)
    status: Literal["pending", "accepted", "rejected"]
    active: bool = False


class AnalysisInput(Input):
    allow_remote: Literal[True]


class SampleAssetInput(Input):
    revision: int = Field(ge=0)
    sample_key: str = Field(min_length=1, max_length=40)


def mount_review(app, store):
    review = Review(store)
    app.state.review = review

    @app.exception_handler(ConflictError)
    async def conflict(_request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/api/llm/status")
    def model_status():
        return llm.configuration() | {"configured": bool(llm.api_key())}

    @app.post("/api/projects/{project_id}/characters/{character_id}/codex-sample", status_code=201)
    def codex_sample(project_id: str, character_id: str, body: SampleAssetInput):
        from .character_samples import import_candidate

        return import_candidate(review, project_id, character_id, body.revision, body.sample_key)

    @app.get("/api/projects/{project_id}/characters/{character_id}/codex-samples")
    def codex_samples(project_id: str, character_id: str):
        from .character_samples import candidates

        character = next(
            (c for c in review.state(project_id)["characters"] if c["id"] == character_id), None
        )
        if not character:
            raise KeyError()
        return candidates(character)

    @app.get("/api/projects/{project_id}/review")
    def state(project_id: str):
        return review.state(project_id)

    @app.post("/api/projects/{project_id}/characters", status_code=201)
    def create_character(project_id: str, body: CharacterInput):
        return review.character(
            project_id,
            body.revision,
            body.display_name,
            body.aliases,
            body.description,
            status=body.status,
        )

    @app.patch("/api/projects/{project_id}/characters/{character_id}")
    def update_character(project_id: str, character_id: str, body: CharacterInput):
        return review.character(
            project_id,
            body.revision,
            body.display_name,
            body.aliases,
            body.description,
            character_id,
            status=body.status,
        )

    @app.post("/api/projects/{project_id}/characters/{character_id}/merge")
    def merge(project_id: str, character_id: str, body: MergeInput):
        review.merge(project_id, body.revision, character_id, body.target_id)
        return {"merged_into": body.target_id}

    @app.patch("/api/projects/{project_id}/dialogues")
    def assign(project_id: str, body: AssignmentInput):
        review.assign(project_id, body.revision, body.dialogue_ids, body.speaker_id)
        return {"updated": len(set(body.dialogue_ids))}

    @app.post("/api/projects/{project_id}/characters/{character_id}/assets", status_code=201)
    async def upload(
        project_id: str,
        character_id: str,
        file: Annotated[UploadFile, File()],
        revision: Annotated[int, Form()],
        kind: Annotated[str, Form()],
        license_text: Annotated[str, Form()],
    ):
        raw = await file.read(10_000_001)
        return review.upload_asset(project_id, revision, character_id, raw, kind, license_text)

    @app.patch("/api/projects/{project_id}/assets/{asset_id}")
    def accept(project_id: str, asset_id: str, body: AssetInput):
        review.accept_asset(project_id, body.revision, asset_id, body.status, body.active)
        return {"updated": asset_id}

    @app.get("/api/projects/{project_id}/assets/{asset_id}/file")
    def image(project_id: str, asset_id: str):
        return FileResponse(review.asset_path(project_id, asset_id), media_type="image/png")

    @app.get("/api/projects/{project_id}/audit")
    def audit(project_id: str):
        store.get(project_id)
        with store.db() as db:
            rows = db.execute(
                "SELECT id,action,actor,created_at,before_data,after_data FROM review_audit WHERE project_id=? ORDER BY id DESC LIMIT 300",
                (project_id,),
            )
            return [dict(r) for r in rows]

    def run_analysis(project_id: str, job_id: str):
        try:
            store.finish_job(job_id, result=review.analyze(project_id))
        except Exception as exc:  # noqa: BLE001 -- Persist worker failure for retry.
            # Known validation errors are sanitized; unexpected errors must not reveal input/config.
            store.finish_job(
                job_id,
                error=str(exc)
                if type(exc) is ValueError
                else "角色抽取未完成，本轮未应用。请检查配置后重试。",
            )

    @app.post("/api/projects/{project_id}/analysis", status_code=202)
    def analysis(project_id: str, _body: AnalysisInput, background: BackgroundTasks):
        review.ensure(project_id)
        if not llm.api_key():
            raise ValueError("未找到 DeepSeek 密钥，请在本机配置 DEEPSEEK_API_KEY。")
        job_id = store.start_job(project_id, kind="analysis")
        background.add_task(run_analysis, project_id, job_id)
        return {"job_id": job_id, "state": "running"}

    return review
