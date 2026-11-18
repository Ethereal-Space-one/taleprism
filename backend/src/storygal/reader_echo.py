"""The only reader-facing echo data: two exact, non-ambiguous spans of original prose."""

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class EchoAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    paragraph: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=160)


class EchoFold(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    earlier: EchoAnchor
    later: EchoAnchor


def validate_echo_fold(value, blocks):
    """Return only the public pair. Validate again even for restored/persisted data."""
    if value is None:
        return None
    try:
        fold = EchoFold.model_validate(value)
    except ValidationError:
        raise ValueError("回声折页只能包含前后两处原文的段号与短引句。") from None
    a, b = fold.earlier, fold.later
    if b.paragraph - a.paragraph < 2 or b.paragraph > len(blocks):
        raise ValueError("回声折页须选本章前后两段，中间至少隔一段。")
    if any(p.get("heading") for p in blocks[a.paragraph : b.paragraph]):
        raise ValueError("回声折页的两处引句须在同一章内。")
    for anchor in (a, b):
        source = blocks[anchor.paragraph - 1]["text"]
        pos = source.find(anchor.quote)
        if (
            not anchor.quote.replace("\ufeff", "").strip()
            or pos < 0
            or source.find(anchor.quote, pos + 1) >= 0
        ):
            raise ValueError("回声折页的引句须逐字来自指定段落，并且在该段只出现一次。")
    return fold.model_dump()
