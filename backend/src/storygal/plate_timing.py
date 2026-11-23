"""Private, human-authored reveal judgments on actual placed art and reader-facing copy.

A UTF-8 quote before disclosure is a mechanical prerequisite, not a semantic verdict.
No worksheet import, model, renderer or public bundle consumes these records.
"""

import json
from importlib.resources import files

from .plate_screening import BINDING, digest

# Paired with the standalone Reader's resolvePlatePresentations(); the browser's
# golden-fixture check compares every published recipe field to this packaged data.
_RECIPE = json.loads(files(__package__).joinpath("chibi_plate_presentation.json").read_bytes())


def presentation(book, plate, paragraph_indices, recipe):
    """Resolve only the Reader's exactly bound curated description / delayed display."""
    end = plate["after_byte"]
    description = plate.get("description", "")
    alt = description or plate["title"]
    blocks = book["blocks"]
    idx = paragraph_indices[end]
    source = blocks[idx]

    if book["project"]["canonical_sha256"] == recipe["canonicalHash"]:
        matches = [e for e in recipe["plates"] if plate["id"] in (e["id"], e.get("appliedId"))]
        if len(matches) == 1:
            entry = matches[0]
            aliases = (entry["id"], entry.get("appliedId"))
            media = book["media"][plate["image_asset_id"]]
            quote = entry["evidence"]
            if (
                sum(p["id"] in aliases for p in book["config"]["illustrations"]) == 1
                and end == entry["sourceEnd"]
                and source["byte_start"] == entry["sourceStart"]
                and media["id"] == entry["imageAsset"]
                and media["sha256"] == entry["imageHash"]
                and ("status" not in media or media["status"] == "accepted")
                and source["text"].count(quote) == 1
                and not any(quote in b["text"] for j, b in enumerate(blocks) if j != idx)
            ):
                alt = entry["visualDescription"]
                delay = entry.get("displayAfter")
                if delay and source["text"].endswith(delay["introduction"]):
                    expected = delay["paragraphs"]
                    following = blocks[idx + 1 : idx + 1 + len(expected)]
                    if (
                        expected
                        and len(expected) == len(following)
                        and all(
                            (b["byte_start"], b["byte_end"], b["text"])
                            == (e["start"], e["end"], e["text"])
                            for b, e in zip(following, expected, strict=True)
                        )
                    ):
                        end = following[-1]["byte_end"]
    return {
        "title": plate["title"],  # Visible figcaption and gallery label.
        "description": description,
        "alt": alt,
        "display_after_byte": end,
        "display_paragraph": blocks[paragraph_indices[end]]["text"],
    }


def fingerprint(value):
    return digest(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def assess(book, current, stored):
    """Checked identities only; never guess whether a picture or text gives too much away."""
    revision, saved = (stored[0], json.loads(stored[1])) if stored else (0, {})
    config = {p["id"]: p for p in book["config"]["illustrations"]}
    indices = {b["byte_end"]: i for i, b in enumerate(book["blocks"])}
    display, rows = {}, {}
    counts = {"total": len(current["plates"]), "unchecked": 0, "clear": 0, "revise": 0}
    for r in current["plates"]:
        pid = r["plate_id"]
        view = presentation(book, config[pid], indices, _RECIPE)
        display[pid] = view
        binding = fingerprint(
            [
                "timing-v1",
                current["work_id"],
                current["source_sha256"],
                *[r[k] for k in BINDING],
                view["display_after_byte"],
                view["title"],
                view["description"],
                view["alt"],
            ]
        )
        prior = saved.get(pid)
        if prior and prior["binding"] == binding:
            row = prior | {"stale": False}
        else:
            row = {
                "binding": binding,
                "status": "unchecked",
                "evidence": "",
                "reason": "",
                "stale": bool(prior),
            }
        rows[pid] = row
        counts[row["status"]] += 1
    return display, {
        "revision": revision,
        "ok": counts["total"] == counts["clear"],
        "counts": counts,
        "plates": rows,
        "inventory_binding": fingerprint([r["binding"] for r in rows.values()]),
    }


def _has_text(value):
    return bool(value.strip().strip("\ufeff").strip())


def judgment(body, raw, end):
    if body.status == "unchecked":
        if body.evidence or body.reason:
            raise ValueError("重置为未审时不能保留旧的引文或理由。")
    else:
        if not _has_text(body.evidence) or raw.rfind(body.evidence.encode(), 0, end) < 0:
            raise ValueError("引文必须逐字出自读者在本幅出现时已经读到的原文。")
        if not _has_text(body.reason):
            raise ValueError("请说明实际画面、图题或替代说明为何符合此处，或指出需修改的细节。")
    return {
        "status": body.status,
        "evidence": body.evidence,
        "reason": body.reason,
        "binding": body.binding,
    }
