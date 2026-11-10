"""Stored speech metadata is distinct from revision-bearing API requests."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .openai_speech import VOICES


class StoredProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    voice: str = Field(min_length=1, max_length=200)
    speed: int = Field(ge=100, le=300)
    provider: Literal["macos-say", "openai-realtime"] = "macos-say"
    instructions: str = Field(default="", max_length=1000)
    # Historical model IDs remain portable even when the local provider has changed.
    model: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")

    @model_validator(mode="after")
    def validate_provider(self):
        if not self.voice.strip() or self.voice != self.voice.strip():
            raise ValueError("音色名称无效。")
        if self.provider == "openai-realtime":
            if not self.model or self.voice not in VOICES:
                raise ValueError("云端配音必须保留有效的模型与音色。")
        elif self.instructions:
            raise ValueError("本机语音不支持表演说明。")
        return self


class StoredTakeProfile(StoredProfile):
    # A generated take combines the character and line directions with a newline.
    instructions: str = Field(default="", max_length=2001)


def validate_take_profile(take):
    profile = StoredTakeProfile.model_validate(take["profile"])
    if not isinstance(take["model"], str):
        raise ValueError("声音模型记录无效。")  # noqa: TRY004 -- surfaced as an invalid bundle (400).
    # Legacy local takes record the producing engine in provider, while their
    # profile has no provider selector. Do not reinterpret that provenance.
    if "openai-realtime" in {profile.provider, take["provider"]}:
        if take["provider"] != profile.provider:
            raise ValueError("声音记录的配音后端与音色配置不一致。")
        if take["model"] != profile.model:
            raise ValueError("声音记录的模型与音色配置不一致。")
