"""A new catalog sound cannot justify a change to an old reader's original or arrangement."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from chibi_source import digest, encoded, read_zip, verify_inventory
from reissue_reader import pack, reissue

from storygal.portable_reader import DATA_TAG, TEMPLATE, embed_story


def book(work_id):
    src = "夜。".encode()
    block = {
        "byte_start": 0,
        "byte_end": len(src),
        "text": "夜。",
        "heading": False,
        "runs": ["夜。"],
    }
    image = b"existing image"
    media = {
        "type": "figure",
        "sha256": digest(image),
        "url": "./media/p.png",
        "credit": {"name": "artist"},
    }
    plate = {
        "id": "plate-" + work_id,
        "title": "灯",
        "image_asset_id": "asset",
        "after_byte": len(src),
        "alt": "灯在屋里",
    }
    return {
        "project": {
            "id": work_id,
            "canonical_sha256": digest(src),
            "filename": "novel.txt",
            "rights_status": "owned",
        },
        "blocks": [block],
        "media": {"asset": media},
        "config": {"title": "夜", "illustrations": [plate]},
        "characters": [],
    }


SOURCE = "夜。".encode()


def archive(story, original=SOURCE, image=b"existing image"):
    files = {
        "reader.json": encoded(story),
        "storygal-source/original.txt": original,
        "storygal-source/source.utf8.txt": original,
        "index.html": embed_story(TEMPLATE, story).encode(),
        "media/p.png": image,
    }
    files["storygal-delivery.json"] = encoded(
        {
            "schema_version": 1,
            "files": {k: {"bytes": len(v), "sha256": digest(v)} for k, v in files.items()},
        }
    )
    return pack(files)


def test_stable_identity_pair():
    a, b = book("old"), book("new")
    b["blocks"][0]["soundscape"] = {"label": "段落声景"}
    baseline = archive(a)
    content, report = reissue(baseline, archive(b), digest(baseline))
    files = read_zip(content)
    verify_inventory(files)
    bookdata = json.loads(files["reader.json"])
    assert (
        bookdata["project"]["id"] == "old"
        and bookdata["config"]["illustrations"][0]["id"] == "plate-old"
    )
    assert bookdata["blocks"][0]["soundscape"] and report["sound_blocks"] == [0]
    assert (
        json.loads(files["index.html"].decode().split(DATA_TAG)[1].split("</script>")[0])
        == bookdata
    )


@pytest.mark.parametrize(
    "fault", ["hash", "source", "figure", "credit", "plate", "dialogue", "characters"]
)
def test_refuse_to_rewrite_an_existing_work(fault):
    base = archive(book("old"))
    target = copy.deepcopy(book("new"))
    kw = {}
    if fault == "source":
        kw["original"] = b"changed"
    if fault == "figure":
        kw["image"] = b"changed"
    if fault == "credit":
        target["media"]["asset"]["credit"] = {"name": "replacement"}
    if fault == "plate":
        target["config"]["illustrations"][0]["alt"] = "different"
    if fault == "dialogue":
        target["blocks"][0]["runs"] = []
    if fault == "characters":
        target["characters"].append({})
    with pytest.raises(ValueError):
        reissue(base, archive(target, **kw), "incorrect" if fault == "hash" else digest(base))


def test_missing_source_supplement_is_not_silently_exported_or_copied():
    prior = read_zip(archive(book("old")))
    prior["licenses/calibration-card.txt"] = b"Sample attribution"
    inv = json.loads(prior["storygal-delivery.json"])
    inv["files"]["licenses/calibration-card.txt"] = {
        "bytes": 18,
        "sha256": digest(b"Sample attribution"),
    }
    prior["storygal-delivery.json"] = encoded(inv)
    baseline = pack(prior)
    with pytest.raises(ValueError, match="license missing"):
        reissue(baseline, archive(book("new")), digest(baseline))
