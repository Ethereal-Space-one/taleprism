from typing import Literal

from fastapi import BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from . import speech as speech_backend
from .speech import Speech


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)


class Profile(Input):
    voice: str
    speed: int = Field(ge=100, le=300)
    provider: Literal["macos-say", "openai-realtime"] = "macos-say"
    instructions: str = Field(default="", max_length=1000)


class Line(Input):
    selected: bool
    overrides: dict[str, str] = Field(default_factory=dict, max_length=100)
    instructions: str | None = Field(default=None, max_length=1000)


class Accept(Input):
    take_ids: dict[str, str]


class Generate(BaseModel):
    dialogue_id: str
    segment_key: str | None = None
    force: bool = False


def mount_speech(app, store, review):
    speech = Speech(store, review)
    app.state.speech = speech

    @app.get("/api/speech/capabilities")
    def capabilities():
        return speech_backend.capabilities()

    @app.get("/api/projects/{pid}/speech")
    def state(pid: str):
        return speech.state(pid)

    @app.patch("/api/projects/{pid}/speech/profiles/{cid}")
    def profile(pid: str, cid: str, body: Profile):
        speech.profile(
            pid, body.revision, cid, body.voice, body.speed, body.provider, body.instructions
        )
        return {"saved": True}

    @app.patch("/api/projects/{pid}/speech/lines/{did}")
    def line(pid: str, did: str, body: Line):
        speech.line(pid, body.revision, did, body.selected, body.overrides, body.instructions)
        return {"saved": True}

    @app.post("/api/projects/{pid}/speech/lines/{did}/accept")
    def accept(pid: str, did: str, body: Accept):
        speech.accept(pid, body.revision, did, body.take_ids)
        return {"saved": True}

    def work(pid, job_id, body):
        try:
            store.finish_job(
                job_id,
                result=speech.synthesize(pid, body.dialogue_id, body.segment_key, body.force),
            )
        except Exception as exc:  # noqa: BLE001 -- Task boundary, keep failure retryable.
            store.finish_job(
                job_id, error=str(exc) if type(exc) is ValueError else "配音任务失败，请重试此句。"
            )

    @app.post("/api/projects/{pid}/speech/generate", status_code=202)
    def generate(pid: str, body: Generate, background: BackgroundTasks):
        store.get(pid)
        job_id = store.start_job(pid, "speech")
        background.add_task(work, pid, job_id, body)
        return {"job_id": job_id}

    @app.get("/api/projects/{pid}/speech/takes/{take_id}")
    def audio(pid: str, take_id: str):
        store.get(pid)
        with store.db() as db:
            take = review.item(db, "speech_takes", pid, take_id)
        return FileResponse(speech.path(pid, take), media_type="audio/wav")

    return speech
