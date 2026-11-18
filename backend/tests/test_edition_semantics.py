"""Self-contained negative controls: a cryptographically consistent file can be the wrong edition."""

import copy
import hashlib
import io
import json
import sys
import wave
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from check_edition_semantics import inspect, variant
from reissue_autoplay import loadzip


def h(b):
    return hashlib.sha256(b).hexdigest()


def sealed(files, model):
    data = json.dumps(model, ensure_ascii=False).encode()
    files = {
        **files,
        "index.html": b'<script id="taleprism-story" type="application/json">'
        + data
        + b"</script>",
        "reader.json": data,
    }
    inventory = {k: {"bytes": len(v), "sha256": h(v)} for k, v in files.items()}
    files["storygal-delivery.json"] = json.dumps({"files": inventory}).encode()
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in sorted(files.items()):
            z.writestr(k, v)
    raw = target.getvalue()
    loadzip(raw)  # every failure below happens DESPITE a matching inventory
    return raw


@pytest.fixture
def gold():
    src = b"Rain.\n\nDone."
    wav = io.BytesIO()
    with wave.open(wav, "wb") as f:
        f.setparams((2, 2, 24000, 0, "NONE", ""))
        f.writeframes(bytes(4 * 288000))
    files = {
        "licenses/Taleprism-MIT.txt": (ROOT / "LICENSE").read_bytes(),
        "storygal-source/source.utf8.txt": src,
        "storygal-source/original.txt": src,
        "media/rain.wav": wav.getvalue(),
        "media/p.png": b"synthetic review asset",
    }
    media = {
        "w": {
            "type": "audio",
            "origin": "paragraph_soundscape",
            "url": "./media/rain.wav",
            "sha256": h(files["media/rain.wav"]),
        },
        "p": {"type": "image", "url": "./media/p.png", "sha256": h(files["media/p.png"])},
    }
    m = {
        "project": {"id": "fixed", "sha256": h(src), "canonical_sha256": h(src)},
        "preview": False,
        "config": {
            "title": "Fixture",
            "illustrations": [{"id": "checked", "after_byte": 5, "image_asset_id": "p"}],
        },
        "presentations": [],
        "map_entries": [],
        "media": media,
        "blocks": [
            {
                "byte_start": 0,
                "byte_end": 5,
                "text": "Rain.",
                "soundscape": {"id": "w", "description": "rain", "duration": 12},
            },
            {"byte_start": 7, "byte_end": 12, "text": "Done."},
        ],
    }
    spec = {
        "source_sha256": h(src),
        "title": "Fixture",
        "public_work_id": "fixed",
        "paragraphs": 2,
        "presentations": 0,
        "map_entries": 0,
        "image_members": 1,
        "illustrations": [
            {"id": "checked", "after_byte": 5, "image_sha256": media["p"]["sha256"], "motion": None}
        ],
        "narrations": [],
        "dialogue_audio": [],
        "echo": None,
        "soundscapes": [
            {
                "paragraph": 1,
                "byte": 0,
                "description": "rain",
                "duration": 12,
                "sha256": media["w"]["sha256"],
            }
        ],
    }
    return files, m, spec


def test_contract_accepts_expected_payload(gold):
    files, model, spec = gold
    assert inspect(sealed(files, model), spec)["storygal-source/original.txt"] == b"Rain.\n\nDone."


@pytest.mark.parametrize(
    "fault",
    [
        "dropped-even-when-all-bytes-match",
        "missing-wav",
        "wrong-plate",
        "wrong-quote-target",
        "wrong-paragraph",
        "orphan-audio",
        "unexpected-dialogue",
        "wrong-public-work",
    ],
)
def test_per_book_intent_not_just_digest(gold, fault):
    files, model, spec = gold
    if fault == "dropped-even-when-all-bytes-match":
        # The exact historical failure: published ZIP == staged ZIP, yet both
        # omitted the agreed sound. Remove every reference and reseal cleanly.
        del model["blocks"][0]["soundscape"], model["media"]["w"], files["media/rain.wav"]
    elif fault == "missing-wav":
        del files["media/rain.wav"]
    elif fault == "wrong-plate":
        model["config"]["illustrations"][0]["after_byte"] = 12
    elif fault == "wrong-quote-target":
        model["config"]["echo_fold"] = {"later": {"paragraph": 1, "quote": "Rain."}}
    elif fault == "wrong-paragraph":
        model["blocks"][1]["soundscape"] = model["blocks"][0].pop("soundscape")
    elif fault == "orphan-audio":
        files["media/unapproved.wav"] = files["media/rain.wav"]
    elif fault == "unexpected-dialogue":
        model["blocks"][0]["audio"] = [{"take_id": "w"}]
    else:
        model["project"]["id"] = "a-different-public-book"
    raw = sealed(files, model)
    assert h(raw) == h(bytes(raw))
    with pytest.raises((ValueError, KeyError)):
        inspect(raw, spec)


def test_only_explicit_cold_aliases_allowed(gold):
    _, _, spec = gold
    assert variant(spec, "chibi", True)["illustrations"][0]["id"] == "plan-checked"
    assert variant(spec, "last-light", True) == copy.deepcopy(spec)
    assert spec["illustrations"][0]["id"] == "checked"
