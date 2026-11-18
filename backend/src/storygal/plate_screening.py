"""Private editorial worksheet. A review is a decision, never a render instruction or receipt."""

import hashlib
import io
from copy import deepcopy
from typing import Annotated, Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .reader_motion import RainMotion, ShoreMotion

Id = Annotated[str, Field(min_length=1, max_length=256)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Text = Annotated[str, Field(max_length=1000)]
Decision = Literal["unassessed", "still", "deferred", "motion"]


class Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Judgment(Model):
    plate_id: Id
    decision: Decision
    evidence: Annotated[str, Field(max_length=300)]
    observation: Text
    action: Text
    protect: Text
    reason: Text
    proposed_effect: Literal["rain-wet-ground", "wave-impact-backwash"] | None = None
    verification: Text = ""  # Optional personal note, NOT evidence of actual playback.


class Plate(Judgment):
    image_asset_id: Id
    image_sha256: Digest
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    after_byte: int = Field(ge=1)
    paragraph_start: int = Field(ge=0)


class Worksheet(Model):
    schema_version: Literal[1]
    work_id: Id
    source_sha256: Digest
    plates: list[Plate] = Field(max_length=64)

    @field_validator("schema_version", mode="before")
    @classmethod
    def no_boolean(cls, v):
        if type(v) is not int:
            raise ValueError("schema_version must be the integer 1")
        return v

    @field_validator("plates")
    @classmethod
    def unique_ids(cls, rows):
        if len({r.plate_id for r in rows}) != len(rows):
            raise ValueError("duplicate worksheet plate_id")
        return rows


FIELDS = ("evidence", "observation", "action", "protect", "reason")
BINDING = (
    "plate_id",
    "image_asset_id",
    "image_sha256",
    "width",
    "height",
    "after_byte",
    "paragraph_start",
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def make_worksheet(book, source, read_image):
    """Inventory actual chapter illustrations (not every media image). Never infer intent."""
    try:
        project = book["project"]
        require(digest(source) == project["canonical_sha256"], "canonical source SHA-256 mismatch")
        source.decode("utf-8", errors="strict")
        blocks = book["blocks"]
        ends = {}
        last = 0
        for i, b in enumerate(blocks):
            start, end = b["byte_start"], b["byte_end"]
            require(
                type(start) is int and type(end) is int and last <= start < end <= len(source),
                f"paragraph {i + 1}: invalid or overlapping source byte boundaries",
            )
            gap = source[last:start].decode("utf-8")
            if not i:
                gap = gap.removeprefix("\ufeff")
            require(
                not gap.strip() and source[start:end].decode() == b["text"],
                f"paragraph {i + 1}: text differs from canonical UTF-8 bytes",
            )
            last = end
            ends[end] = start
        require(not source[last:].decode().strip(), "reader omitted canonical source text")
        rows, image_cache = [], {}
        previous = -1
        for p in book["config"].get("illustrations", []):
            pid, aid, pos = p["id"], p["image_asset_id"], p["after_byte"]
            require(
                type(pos) is int and pos in ends and pos > previous,
                f"{pid}: illustrations must follow unique, ordered paragraph ends",
            )
            previous = pos
            a = book["media"].get(aid)
            require(
                a
                and a.get("id") == aid
                and a.get("type") == "image"
                and a.get("status") != "rejected",
                f"{pid}: missing or invalid image {aid}",
            )
            if aid not in image_cache:
                raw = read_image(aid)
                sha = digest(raw)
                require(sha == a["sha256"], f"{pid}: actual image SHA-256 mismatch")
                try:
                    with Image.open(io.BytesIO(raw)) as im:
                        size = im.size
                        require(
                            not getattr(im, "is_animated", False),
                            f"{pid}: expected a still original image",
                        )
                        im.verify()
                except (OSError, Image.DecompressionBombError) as exc:
                    raise ValueError(f"{pid}: unreadable original image") from exc
                require(
                    type(a["width"]) is int
                    and type(a["height"]) is int
                    and size == (a["width"], a["height"]),
                    f"{pid}: actual image dimensions mismatch",
                )
                image_cache[aid] = sha, *size
            sha, w, h = image_cache[aid]
            rows.append(
                dict(
                    plate_id=pid,
                    image_asset_id=aid,
                    image_sha256=sha,
                    width=w,
                    height=h,
                    after_byte=pos,
                    paragraph_start=ends[pos],
                    decision="unassessed",
                    **dict.fromkeys(FIELDS, ""),
                )
            )
        return Worksheet(
            schema_version=1, work_id=project["id"], source_sha256=digest(source), plates=rows
        ).model_dump()
    except (KeyError, AttributeError, TypeError, UnicodeError) as exc:
        raise ValueError(f"invalid source/plate inventory: {exc}") from exc


def reconcile(current, previous):
    """Preserve only individually unchanged bindings. Different work IDs require deliberate adoption."""
    prior = Worksheet.model_validate(previous).model_dump()
    require(
        current["work_id"] == prior["work_id"], "different work_id; refusing automatic transfer"
    )
    out, messages = deepcopy(current), []
    old = {r["plate_id"]: r for r in prior["plates"]}
    same_source = current["source_sha256"] == prior["source_sha256"]
    for i, row in enumerate(out["plates"]):
        pid = row["plate_id"]
        earlier = old.pop(pid, None)
        if not earlier:
            messages.append(f"{pid}: new plate; unassessed")
        elif not same_source or any(row[k] != earlier[k] for k in BINDING):
            messages.append(f"{pid}: changed source/art/anchor/identity; reset to unassessed")
        else:
            out["plates"][i] = earlier
    messages += [f"{pid}: removed from edition" for pid in old]
    return out, messages


# Legacy renderer has exactly two shader recipes that aren't in reader.json. Mirror only
# their exact reviewed source, image and placement bindings, never a title/slug guess.
_CHIBI = "ad97df377de9a9f5f2680253666ec6d9a6d2b8be055ee94a92643a4b16043341"
_ARRIVAL = "1b2e65bfef863fa666d525aae620793d72038e0442ae4bb5a88f2e12ddbd5880"
_ARRIVAL_IMAGES = {
    "556de6cf96af3220dab851317af0bc2e6d290034d17b0a23ddc9575d45905145",
    "7bd8cc49a2a3dd412c876d6b20063c2496f2db4289a51937fa206e8c1060318f",
    "2dc65d6e43f987fdb4b908e43fb34fb37f66aaf8c271d21f6b40ea5658c4ddec",
}


def carriers_for_book(book, current, source):
    """Only known supported directions bound to these bytes; eligible is NOT observed active."""
    plates = {p["id"]: p for p in book["config"].get("illustrations", [])}
    carriers = {}
    for r in current["plates"]:
        pid, aid, pos = r["plate_id"], r["image_asset_id"], r["after_byte"]
        p, a = plates[pid], book["media"][aid]
        if a.get("status") != "accepted" and ("status" in a or book.get("preview") is not False):
            continue
        if "motion" in p:
            m = p["motion"]
            if m is None or not isinstance(m, dict) or m.get("reviewed") is not True:
                continue  # explicit static or unreviewed: no fallback to legacy sample motions.
            effect = m.get("effect")
            if effect not in ("rain-wet-ground", "wave-impact-backwash"):
                continue  # unsupported material: never compile a substitute.
            for k, value in (
                ("after_byte", pos),
                ("width", r["width"]),
                ("height", r["height"]),
                ("image_sha256", r["image_sha256"]),
                ("source_sha256", current["source_sha256"]),
            ):
                require(m.get(k) == value, f"{pid}: stale render binding: {k}")
            if "playback_only" in m:
                require(
                    m["playback_only"] is True and "note" not in m and "evidence" not in m,
                    f"{pid}: invalid playback-only render data",
                )
                # The public projection intentionally has no private editor notes. Reuse the
                # production geometry validator; these placeholders are not editorial proof.
                model = {k: v for k, v in m.items() if k != "playback_only"}
                model.update(note="render-only", evidence="render-only")
            else:
                model = m
            try:
                spec = (RainMotion if effect == "rain-wet-ground" else ShoreMotion).model_validate(
                    model
                )
            except ValueError as exc:
                raise ValueError(f"{pid}: invalid {effect} render geometry: {exc}") from exc
            if "playback_only" not in m:
                require(
                    any(
                        b["byte_end"] <= pos and spec.evidence in b["text"] for b in book["blocks"]
                    ),
                    f"{pid}: render evidence not in a preceding paragraph",
                )
            carriers[pid] = effect
        elif (r["width"], r["height"]) == (1672, 941):
            sha = r["image_sha256"]
            if (
                current["source_sha256"] == _ARRIVAL
                and pos == 526
                and pid == "plan-arrival"
                and sha in _ARRIVAL_IMAGES
            ):
                carriers[pid] = "rain-wet-ground"
            chibi_ids = {"river-overlook", "plan-river-overlook"}
            quote = "三江口周瑜縱火".encode()
            if (
                current["source_sha256"] == _CHIBI
                and pid in chibi_ids
                and len(chibi_ids & plates.keys()) == 1
                and r["paragraph_start"] == 0
                and pos == 63
                and source[:pos].count(quote) == source.count(quote) == 1
                and aid == "da59592b-3675-45ae-aefe-867b01d0a2e3"
                and sha == "e615364cdee1f0fad4236afbf44aa1d5b0bd338cba14acaa01c2cf2506042c07"
            ):
                carriers[pid] = "wave-impact-backwash"
    return carriers


def assess(current, sheet, source, *, carriers=None, active=()):
    """Inspect complete coverage, separately reporting editorial intent, capability and observation."""
    errors, details = [], []
    counts = dict.fromkeys(
        ("total", "screened", "unassessed", "still", "deferred", "motion", "active"), 0
    )
    counts["total"] = len(current["plates"])
    # Fail before examining any stale or malformed human data. Never repair it implicitly.
    normalized, messages = reconcile(current, sheet)
    require(not messages, "stale or incomplete worksheet: " + "; ".join(messages))
    require(
        sheet["source_sha256"] == digest(source) == current["source_sha256"],
        "stale or changed canonical source",
    )
    carriers, active = carriers or {}, set(active)
    require(
        set(carriers) <= {r["plate_id"] for r in current["plates"]}
        and set(carriers.values()) <= {"rain-wet-ground", "wave-impact-backwash"}
        and active <= set(carriers),
        "unverified plate or unsupported carrier in observations",
    )
    for row in normalized["plates"]:
        pid, choice = row["plate_id"], row["decision"]
        effect = carriers.get(pid)
        faults, span = [], None
        status = {
            "unassessed": "unassessed",
            "still": "still",
            "deferred": "deferred-static",
            "motion": "candidate",
        }[choice]
        if choice == "unassessed":
            faults.append("not screened; inspect original pixels and available source")
        else:
            for k in FIELDS:
                if not row[k].strip().strip("\ufeff").strip():
                    faults.append(f"missing {k}")
            ev = row["evidence"].encode()
            at = source.rfind(ev, 0, row["after_byte"]) if ev and row["evidence"].strip() else -1
            if at < 0:
                faults.append("evidence is not an exact UTF-8 quotation available by after_byte")
            else:
                span = [at, at + len(ev)]
        proposal = row["proposed_effect"]
        if choice == "motion":
            if not (effect or proposal):
                faults.append(
                    "name a supported proposed_effect; use deferred if the needed carrier does not exist"
                )
            elif effect and proposal and effect != proposal:
                faults.append(
                    f"proposed_effect {proposal} conflicts with the bound treatment {effect}"
                )
        elif proposal is not None:
            faults.append("proposed_effect is only for a motion candidate")
        if effect and choice in ("deferred", "still"):
            faults.append(f"{choice} conflicts with an eligible {effect} treatment")
        if pid in active:
            counts["active"] += 1
            status = "active" if choice == "motion" else "conflict"
        counts[choice] += 1
        if not faults:
            counts["screened"] += 1
        errors.extend(f"{pid}: {fault}" for fault in faults)
        details.append(
            {
                "plate_id": pid,
                "decision": choice,
                "status": status,
                "carrier": effect,
                "proposed_effect": proposal,
                "evidence_bytes": span,
                "errors": faults,
            }
        )
    return {"ok": not errors, "errors": errors, "counts": counts, "plates": details}
