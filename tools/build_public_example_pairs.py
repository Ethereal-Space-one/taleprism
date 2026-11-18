"""Build the 0.9.1 public example pairs, offline, from four official v0.3.3 archives.

Download the four taleprism-v0.3.3-{chibi,last-light}-{reader,project}.zip assets
from https://github.com/Ethereal-Space-one/taleprism/releases/tag/v0.3.3.
After npm --prefix frontend run build:
    uv run --project backend python tools/build_public_example_pairs.py --inputs OLD --output OUT
Only named, hash-pinned public editions are accepted. No existing workspace, private
edition, external provider, voice synthesis, user records or upload. Only the two
reviewed, hash-pinned procedural ambience recipes are rendered.
"""

import argparse
import copy
import json
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from build_chibi_demo import pack, sync_reader_data
from chibi_source import digest, encoded, read_zip, verify_inventory
from classic_example_sound import SOUNDS
from release_version import PREFIX, VERSION

ROOT = Path(__file__).resolve().parents[1]
# The two pairs and the additional provenance below are from the published 0.3.3
# release manifest (883cf91f2d848e4f23bf5f548766e155a635022d5a85d9031f5ab85d2782c3e0).
PINS = {
    "last-light": {
        "project": "2412e00dc8f9db7dac51c0bc77e65a55673e47ed7363de30beaf5e6b10c800e6",
        "reader": "a6ae881a78e18be2e9eb15fb29b5d17447ca55c4cb4803232d8773363d816aef",
        "source": "1b2e65bfef863fa666d525aae620793d72038e0442ae4bb5a88f2e12ddbd5880",
        "work": "2a036de9-32f1-4ad5-b9bd-f6f4d8d570ae",
        "media": 6,
        "plates": 3,
    },
    "chibi": {
        "project": "88731837a5605474ec09c6d0b2b3939b0221a1973384c0c664b3c7b3be94e750",
        "reader": "8fa45fbd577b17c4175906c4950ea5857dda3eb1e60f470675926357beac3c2e",
        "source": "ad97df377de9a9f5f2680253666ec6d9a6d2b8be055ee94a92643a4b16043341",
        "work": "fde5c24b-6a65-4fc4-9955-2bac34a9d958",
        "media": 27,
        "plates": 12,
    },
}
# The existing published Last Light media credits explicitly request that these
# authorship/generation records travel with the art. Pin only known public text.
LAST_LIGHT_CREDITS = {
    "PROVENANCE.md": "30d9d5455012be56ec0da8a248d00888b73c8db97869b719f13604b6e3dd7fa3",
    "prompts.json": "6aceeb14c35f83372b34e8764b3dedadc3ef2fbc8af172e9f78da27d90a5fcc2",
    "scene-prompts.json": "9c610effddfbc86e796fba20fa7aecb252f10cb24ffdd958791510a2819160d7",
    "continuity-prompts-v2.json": "ad6c119de9b97360f01f021a8475b97d57463dc420af415a95bd5279d1328c47",
    "continuity-review.json": "5cb20d934ae0f097d03ed110eccb62745f5b7ce4174ebdebb55639650a9e5787",
}
SOURCE_NOTE = {
    "chibi": "赤壁 · v0.3.3 原文、27 张既有图片、55 段呈现及 12 个旧插图标记保留。第十二段「忽聽風聲響，旗旛轉動」有一次十二秒合成风声，其余段落不铺底。历史地图为阅读示意；作者最终美术复核未完成。",
    "last-light": "末班灯 · v0.3.3 原文、3 幅插图及全部 6 张既有图片保留。第二段「傍晚的雨斜着落进站台」有一次十二秒合成细雨。没有车辆、朗读或系统配音；旧制作记录不代表本包有配音。",
}
RIGHTS = "阅读器代码的 MIT 许可不替代原文、图像或既有来源说明。\nThe software license does not change manuscript or artwork rights.\n"


def require(yes, reason):
    if not yes:
        raise ValueError(reason)


def checked_file(path, sha):
    require(
        path.is_file() and path.stat().st_size <= 160_000_000,
        f"Missing or oversized input: {path.name}",
    )
    raw = path.read_bytes()
    require(digest(raw) == sha, f"Wrong input SHA-256: {path.name}")
    return raw


def credits(example):
    if example != "last-light":
        return {}
    return {
        "storygal-source/samples/last-light/" + name: checked_file(
            ROOT / "samples/last-light" / name, sha
        )
        for name, sha in LAST_LIGHT_CREDITS.items()
    }


def project_archive(example, files, mit, material):
    manifest = json.loads(files["manifest.json"])
    require(
        manifest["files"]
        == {k: digest(v) for k, v in files.items() if k != "manifest.json"},
        "Prior editable inventory mismatch",
    )
    model = json.loads(files["project.json"])
    require(
        model["version"] == 2
        and not model["records"]["speech_takes"]
        and model["states"]["speech_states"]["data"] == {"profiles": {}, "lines": {}}
        and not any(
            k.startswith(("audio/", "narrations/", "soundscapes/")) for k in files
        ),
        "Unexpected voice, audio or changed editable type",
    )
    sound = SOUNDS[example]
    source, original = files["source.utf8.txt"], files["original.txt"]
    require(
        digest(source) == PINS[example]["source"],
        "Unexpected source for approved sound",
    )
    record, wav = sound.accepted_record(source, original)
    require(
        "reader_editorial" not in model["states"],
        "Unexpected historical editorial state",
    )
    model["version"] = 6
    model["records"]["soundscape_takes"] = [record]
    model["states"]["reader_states"]["revision"] += 1
    files["project.json"] = encoded(model)
    files[sound.project_wav] = wav
    old = files["README.txt"]
    # The historical importer has a strict member allowlist. Keep all production
    # records and art; add one bound sound record/WAV and keep provenance in README.
    files["README.txt"] = (
        (
            f"Taleprism v{VERSION} · 公开可编辑示例 / Public editable example\n"
            + SOURCE_NOTE[example]
            + "\n从制作台导入此 ZIP，不是读者版。\n"
            + RIGHTS
            + "声景由 Taleprism 程序合成，并非现场录音。此公开工程仅含该段已采用的声音，不含声景候选、撤回记录或私人制作意见。\n"
            + "以下为 v0.3.3 历史随包说明；其中的无声说明只适用于当时的版本。\n"
        ).encode()
        + b"\n"
        + old
        + b"\n\n"
        + mit
    )
    for name, raw in material.items():
        files["README.txt"] += ("\n\n=== " + name + " ===\n").encode() + raw
    # V6 requires truthful issue coverage of *this* public derivative, not a
    # claim that anybody's separate workspace was reviewed or contained no issues.
    manifest["editorial_count"] = 0
    for name in ("project.json", "README.txt", sound.project_wav):
        manifest["files"][name] = digest(files[name])
    files["manifest.json"] = encoded(manifest)
    return pack(files)


def cold_export(editable, directory):
    from fastapi.testclient import TestClient
    from storygal.app import create_app

    with TestClient(create_app(directory)) as c:
        restored = c.post(
            "/api/project-bundles", files={"file": ("project.zip", editable)}
        )
        restored.raise_for_status()
        result = restored.json()
        require(
            not result.get("restore_issues"),
            "Public editable has unresolved restore issues",
        )
        base = "/api/projects/" + result["id"]
        check = c.get(base + "/bundle")
        check.raise_for_status()  # full snapshot, structural/media validation, including fresh restore
        matches = [
            ex
            for ex, spec in PINS.items()
            if spec["source"] == result["canonical_sha256"]
        ]
        require(len(matches) == 1, "Not a pinned public sample source")
        sound = SOUNDS[matches[0]]
        roundtrip = read_zip(check.content)
        restored_doc = json.loads(roundtrip["project.json"])
        takes = restored_doc["records"].get("soundscape_takes", [])
        require(
            restored_doc["version"] == 6
            and len(takes) == 1
            and takes[0]
            == sound.accepted_record(
                roundtrip["source.utf8.txt"], roundtrip["original.txt"]
            )[0]
            and digest(roundtrip[sound.project_wav]) == sound.sha256
            and not restored_doc["records"]["speech_takes"]
            and "reader_editorial" not in restored_doc["states"],
            "Ordinary project re-export did not retain the sole accepted sound",
        )
        require(
            c.get(base + "/delivery").json()["records"] == [],
            "Unexpected final delivery claim",
        )
        job = c.post(base + "/reader/exports")
        job.raise_for_status()
        job = c.get(base + "/jobs").json()[0]
        require(
            job["state"] == "completed",
            "Clean 0.9 reader export failed: " + str(job.get("error")),
        )
        built = c.get(job["result"]["download_url"])
        built.raise_for_status()
        return built.content


def seal_reader(example, raw, previous, mit, material):
    p = PINS[example]
    inv_old = verify_inventory(previous)
    files = read_zip(raw)
    inv = verify_inventory(files)
    before, fresh = [json.loads(d["reader.json"]) for d in (previous, files)]
    d = copy.deepcopy(fresh)
    require(
        files.get("licenses/Taleprism-MIT.txt") == mit,
        "Fresh exporter lacks complete Taleprism MIT",
    )
    for name in (
        "react.txt",
        "react-dom.txt",
        "scheduler.txt",
        "opencc-js.txt",
        "opencc-js-Apache-2.0.txt",
        "opencc-js-THIRD_PARTY_LICENSES.md",
    ):
        require(
            bool(files.get("licenses/" + name)),
            "Missing bundled dependency notice: " + name,
        )
    require(
        {k for k in files if k.startswith("assets/")}
        == {"assets/reader.js", "assets/reader.css"},
        "Unexpected runtime files",
    )
    canonical = files["storygal-source/source.utf8.txt"]
    require(
        digest(canonical)
        == p["source"]
        == digest(files["storygal-source/original.txt"]),
        "Source changed",
    )
    d["project"]["id"] = before["project"]["id"]
    require(
        d["project"] == before["project"] and d["project"]["id"] == p["work"],
        "Work identity changed",
    )
    sound = SOUNDS[example]
    require(
        d["schema_version"] == 5 and before["schema_version"] == 3,
        "Expected V5 sound edition",
    )
    require(
        d["versions"]
        == before["versions"]
        | {"reader_revision": before["versions"]["reader_revision"] + 1},
        "Revision drift",
    )
    for key in (
        "characters",
        "presentations",
        "map",
        "map_entries",
        "preview",
        "issues",
    ):
        require(d[key] == before[key], "Publication metadata mismatch: " + key)
    require(len(d["blocks"]) == len(before["blocks"]), "Paragraph count changed")
    end = 0
    for block, historical in zip(d["blocks"], before["blocks"], strict=True):
        require(
            block
            == historical
            | {"source_gap_before": canonical[end : block["byte_start"]].decode()}
            | (
                {"soundscape": sound.cue}
                if historical["byte_start"] == sound.start
                else {}
            ),
            "Original anchors or whitespace changed",
        )
        end = block["byte_end"]
    plates, historic = d["config"]["illustrations"], before["config"]["illustrations"]
    require(len(plates) == len(historic) == p["plates"], "Illustration set changed")
    for plate, old in zip(plates, historic, strict=True):
        require(
            plate["id"] == (("plan-" if example == "chibi" else "") + old["id"]),
            "Unexpected illustration ID migration",
        )
        plate["id"] = old["id"]
    require(d["config"] == before["config"], "Arrangement changed")
    require(
        len(before["media"]) == p["media"]
        and d["media"].keys() == before["media"].keys() | {sound.id}
        and d["media"][sound.id] == sound.media
        and digest(files[sound.reader_wav]) == sound.sha256
        and [k for k in files if k.endswith(".wav")] == [sound.reader_wav]
        and [
            (b["byte_start"], b["byte_end"]) for b in d["blocks"] if b.get("soundscape")
        ]
        == [(sound.start, sound.end)],
        "Unexpected media or approved sound projection",
    )
    for aid, old in before["media"].items():
        asset = d["media"][aid]
        require(
            asset["type"] in ("image", "figure")
            and asset["url"] == "./media/" + aid + ".png"
            and asset.items() <= old.items()
            and old.get("license") == asset.get("license")
            and files[asset["url"][2:]] == previous[old["url"][2:]]
            and digest(files[asset["url"][2:]]) == asset["sha256"],
            "Media or published attribution changed: " + aid,
        )
    for name, value in previous.items():
        if name.startswith("storygal-source/"):
            require(
                name not in files or files[name] == value,
                "Existing provenance changed: " + name,
            )
            files[name] = value
    old_mit = previous.get("licenses/Taleprism-MIT.txt")
    if old_mit and old_mit != mit:
        files["licenses/historical-v0.3.3-Taleprism-MIT.txt"] = old_mit
    files.update(material)
    files["RIGHTS.txt"] += ("\n" + SOURCE_NOTE[example] + "\n" + RIGHTS).encode()
    if example == "last-light":
        files["RIGHTS.txt"] += (
            b"Last Light manuscript, artwork and generation records: storygal-source/samples/last-light/PROVENANCE.md.\n"
        )
    if "SHOWCASE.txt" in previous:
        history = previous["SHOWCASE.txt"].decode()
        require("不含系统语音及任何音频配置" in history, "Unknown historical showcase")
        files["SHOWCASE.txt"] = (
            history.replace(
                "不含系统语音及任何音频配置",
                "本版仅在第十二段保留一次程序合成的风声；无系统配音",
            )
            .replace("Taleprism v0.3.3 ", f"Taleprism v{VERSION} ", 1)
            .encode()
        )
    files["README.txt"] = (
        "Taleprism v" + VERSION + " · " + SOURCE_NOTE[example] + "\n\n"
    ).encode() + files["README.txt"]
    # The database can enumerate image/character IDs in a different order for
    # each imported project. Do not reorder arrays (their order is narrative).
    # Canonical object order keeps both the inert HTML payload and reader.json
    # byte-identical across clean, independent rebuilds of these public editions.
    d = json.loads(json.dumps(d, ensure_ascii=False, sort_keys=True))
    files["reader.json"] = encoded(d)
    sync_reader_data(files, fresh, d)
    # Stable public edition export ID, not a new work/bookmark identity or a local job ID.
    del files["storygal-delivery.json"]
    inv["files"] = {
        k: {"bytes": len(v), "sha256": digest(v)} for k, v in sorted(files.items())
    }
    inv["export_id"] = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "taleprism:v" + VERSION + ":" + digest(encoded(inv["files"])),
        )
    )
    require(inv["export_id"] != inv_old["export_id"], "Old export ID reused")
    files["storygal-delivery.json"] = encoded(
        json.loads(json.dumps(inv, sort_keys=True))
    )
    verify_inventory(files)
    return pack(files), d


def build(inputs, out):
    require(VERSION == "0.9.1", "This frozen migration is for v0.9.1 only.")
    targets = [
        out / f"{PREFIX}-{e}-{k}.zip" for e in PINS for k in ("reader", "project")
    ]
    index = out / "public-example-pairs.json"
    require(
        not any(p.exists() for p in [*targets, index]),
        "Will not overwrite frozen example outputs",
    )
    out.mkdir(parents=True, exist_ok=True)
    mit = (ROOT / "LICENSE").read_bytes()
    require(
        all(
            s in mit
            for s in (
                b"2026 Storygal contributors",
                b"2026 Taleprism contributors",
                b"Permission is hereby granted",
                b"THE SOFTWARE IS PROVIDED",
            )
        ),
        "Incomplete source MIT notice",
    )
    checks, records = {}, []
    with tempfile.TemporaryDirectory(prefix="taleprism-public-pairs-", dir=out) as tmp:
        tmp = Path(tmp)
        with (
            patch.dict(os.environ, {"STORYGAL_DATA_DIR": str(tmp / "initial")}),
            patch("storygal.settings.load_env"),
            patch(
                "socket.socket.connect",
                side_effect=AssertionError("Public pack build is offline"),
            ),
        ):
            for ex, pins in PINS.items():

                def prior(kind, ex=ex, pins=pins):
                    return read_zip(
                        checked_file(
                            inputs / f"taleprism-v0.3.3-{ex}-{kind}.zip", pins[kind]
                        )
                    )

                material = credits(ex)
                project = project_archive(ex, prior("project"), mit, material)
                built, story = seal_reader(
                    ex,
                    cold_export(project, tmp / ex),
                    prior("reader"),
                    mit,
                    material,
                )
                for kind, raw in (("project", project), ("reader", built)):
                    name = f"{PREFIX}-{ex}-{kind}.zip"
                    (tmp / name).write_bytes(raw)
                    records.append(
                        {
                            "file": name,
                            "bytes": len(raw),
                            "sha256": digest(raw),
                            "example": ex,
                            "kind": kind,
                        }
                    )
                checks[ex] = {
                    "prior_public_release": "v0.3.3",
                    "prior_project_sha256": pins["project"],
                    "prior_reader_sha256": pins["reader"],
                    "public_work_id": pins["work"],
                    "original_sha256": pins["source"],
                    "paragraphs": len(story["blocks"]),
                    "illustrations": pins["plates"],
                    "media": pins["media"] + 1,
                    "unchanged_images": pins["media"],
                    "accepted_sound": {
                        "id": SOUNDS[ex].id,
                        "byte_start": SOUNDS[ex].start,
                        "sha256": SOUNDS[ex].sha256,
                    },
                    "editable_schema": 6,
                    "reader_schema": 5,
                    "clean_project_import_and_reexport": True,
                    "prior_media_and_source_preserved": True,
                    "system_audio_included": False,
                    "creator_final_review": "pending",
                }
                del project, built, story
        (tmp / index.name).write_bytes(
            encoded({"artifacts": records, "checks": checks})
        )
        for dest in [*targets, index]:
            (tmp / dest.name).rename(dest)
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    opts = parser.parse_args()
    print(json.dumps(build(opts.inputs.resolve(), opts.output.resolve()), indent=2))
