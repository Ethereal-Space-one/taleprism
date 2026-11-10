"""Build a local sample solely through public APIs, from a content-only recipe."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import httpx


def build(
    recipe_path, base, destination, with_audio=False, client_factory=httpx.Client
):
    recipe_path = Path(recipe_path)
    root = recipe_path.parent
    recipe_raw = recipe_path.read_bytes()
    recipe = json.loads(recipe_raw)
    continuity_review = None
    dependencies = None
    if recipe.get("scenes"):
        review_file = recipe.get("continuity_review")
        if not review_file:
            raise ValueError(
                "此配方包含连续场景，需先在制作台检查图像并保存带哈希的制作检查记录。"
            )
        try:
            continuity_review = json.loads((root / review_file).read_bytes())
        except (OSError, ValueError) as exc:
            raise ValueError(
                "连续性制作检查失效：检查记录缺失或无法读取，请重新核对。"
            ) from exc
        if not isinstance(continuity_review, dict):
            raise ValueError("连续性制作检查失效：检查记录格式无效，请重新核对。")
        if (
            continuity_review.get("recipe_sha256")
            != hashlib.sha256(recipe_raw).hexdigest()
        ):
            raise ValueError("配方已改变或缺少哈希，连续性制作检查失效，请重新核对。")
        expected_shots = {
            s["id"] for s in recipe["shots"] if s.get("continuity", {}).get("scene_id")
        }
        if (
            continuity_review.get("reviewer") not in {"creator", "assistant"}
            or not isinstance(continuity_review.get("notes"), dict)
            or set(continuity_review.get("notes", {})) != expected_shots
            or any(
                not isinstance(v, str) or len(v.strip()) < 8
                for v in continuity_review["notes"].values()
            )
        ):
            raise ValueError("制作检查的署名或逐镜头说明不完整。")
        expected = {image["file"] for image in recipe["images"]}
        if (
            not isinstance(continuity_review.get("images"), dict)
            or set(continuity_review["images"]) != expected
        ):
            raise ValueError("连续性制作检查失效：场景图哈希清单不完整，请重新核对。")
        dependencies = continuity_review.get("dependencies")
        if not isinstance(dependencies, dict):
            raise ValueError(
                "连续性制作检查失效：缺少完整依赖清单，请重新核对并升级检查记录，"
                "覆盖原文、全部人物参考与全部场景图。"
            )

    # Paths are recipe-relative, with one digest per file even when reused by multiple roles.
    expected_inputs = (
        {recipe["source"]}
        | {c["portrait"] for c in recipe["characters"] if c.get("portrait")}
        | {image["file"] for image in recipe["images"]}
    )
    if dependencies is not None and set(dependencies) != expected_inputs:
        raise ValueError(
            "连续性制作检查失效：依赖清单与配方不一致，请重新核对并升级检查记录，"
            "覆盖原文、全部人物参考与全部场景图。"
        )
    inputs = {}
    for name in sorted(expected_inputs):
        try:
            inputs[name] = (root / name).read_bytes()
        except OSError as exc:
            raise ValueError(
                f"配方依赖无法读取，制作检查失效，请重新核对：{name}"
            ) from exc
        if dependencies is not None:
            digest = hashlib.sha256(inputs[name]).hexdigest()
            if dependencies[name] != digest or (
                name in continuity_review["images"]
                and continuity_review["images"][name] != digest
            ):
                raise ValueError(
                    f"依赖已改变或哈希无效，制作检查失效，请重新核对：{name}"
                )

    # Upload exactly the bytes checked above; never reread mutable inputs after preflight.
    with client_factory(base_url=base, trust_env=False, timeout=180) as client:

        def call(path, method="GET", body=None, **kwargs):
            r = client.request(method, path, json=body, **kwargs)
            r.raise_for_status()
            return r.json()

        project = call(
            "/api/projects",
            "POST",
            files={
                "file": (
                    recipe["title"] + ".txt",
                    inputs[recipe["source"]],
                )
            },
            data={"rights_status": recipe["rights_status"]},
        )
        prefix = "/api/projects/" + project["id"]

        def state(area):
            return call(prefix + "/" + area)

        def wait(job):
            for _ in range(180):
                result = next(
                    j for j in call(prefix + "/jobs") if j["id"] == job["job_id"]
                )
                if result["state"] != "running":
                    if result["state"] != "completed":
                        raise RuntimeError(result["error"])
                    return result
                time.sleep(0.4)
            raise RuntimeError("任务未完成，请在制作台查看。")

        chars = {}
        for c in recipe["characters"]:
            current = state("review")
            existing = next(
                (r for r in current["characters"] if r["display_name"] == c["name"]),
                None,
            )
            body = {
                "revision": current["revision"],
                "display_name": c["name"],
                "aliases": [],
                "description": c["description"],
                "status": "confirmed",
            }
            char = call(
                prefix + "/characters" + ("/" + existing["id"] if existing else ""),
                "PATCH" if existing else "POST",
                body,
            )
            chars[c["name"]] = char["id"]
            if c.get("portrait"):
                asset = call(
                    prefix + "/characters/" + char["id"] + "/assets",
                    "POST",
                    files={"file": ("figure.png", inputs[c["portrait"]])},
                    data={
                        "revision": state("review")["revision"],
                        "kind": "reference_and_figure",
                        "license_text": recipe["license"],
                    },
                )
                call(
                    prefix + "/assets/" + asset["id"],
                    "PATCH",
                    {
                        "revision": state("review")["revision"],
                        "status": "accepted",
                        "active": True,
                    },
                )
        for item in recipe["dialogues"]:
            current = state("review")
            found = [d for d in current["dialogues"] if d["text"] == item["text"]]
            if len(found) != 1:
                raise ValueError("对白无法唯一匹配：" + item["text"])
            call(
                prefix + "/dialogues",
                "PATCH",
                {
                    "revision": current["revision"],
                    "dialogue_ids": [found[0]["id"]],
                    "speaker_id": chars[item["character"]],
                },
            )
            if with_audio and item.get("voice_prefix"):
                speech = state("speech")
                voice = next(
                    v
                    for v in speech["capabilities"]["voices"]
                    if v.startswith(item["voice_prefix"])
                )
                call(
                    prefix + "/speech/profiles/" + chars[item["character"]],
                    "PATCH",
                    {"revision": speech["revision"], "voice": voice, "speed": 170},
                )
                did = found[0]["id"]
                call(
                    prefix + "/speech/lines/" + did,
                    "PATCH",
                    {"revision": state("speech")["revision"], "selected": True},
                )
                wait(call(prefix + "/speech/generate", "POST", {"dialogue_id": did}))
                speech = state("speech")
                line = next(d for d in speech["lines"] if d["id"] == did)
                call(
                    prefix + "/speech/lines/" + did + "/accept",
                    "POST",
                    {
                        "revision": speech["revision"],
                        "take_ids": {
                            s["key"]: s["candidate"]["id"] for s in line["segments"]
                        },
                    },
                )
        images = {}
        for image in recipe["images"]:
            asset = call(
                prefix + "/reader/assets",
                "POST",
                files={"file": (image["file"], inputs[image["file"]])},
                data={
                    "revision": state("reader")["revision"],
                    "kind": image["kind"],
                    "license_text": image["title"] + "；" + recipe["license"],
                },
            )
            images[image["key"]] = asset["id"]
            call(
                prefix + "/reader/assets/" + asset["id"],
                "PATCH",
                {"revision": state("reader")["revision"], "status": "accepted"},
            )
        reader = state("reader")
        config = reader["config"]
        config.update(
            title=recipe["title"],
            subtitle=recipe["subtitle"],
            cover_asset_id=images[recipe["cover"]],
            reading_layout="illustrated",
        )
        config["scenes"] = [
            {
                "id": "opening",
                "title": recipe["subtitle"],
                "start_byte": reader["paragraphs"][0]["byte_start"],
                "asset_id": images[recipe["background"]],
                "character_ids": [],
            }
        ]
        call(prefix + "/reader", "PATCH", {"revision": reader["revision"], **config})
        shots = []
        for spec in recipe["shots"]:
            spec = dict(spec)
            matches = [p for p in reader["paragraphs"] if spec["marker"] in p["text"]]
            if len(matches) != 1:
                raise ValueError("镜头原文无法唯一匹配：" + spec["marker"])
            spec.pop("marker")
            spec["after_byte"] = matches[0]["byte_end"]
            spec["image_asset_id"] = images[spec.pop("image")]
            spec["actors"] = [
                {
                    "character_id": chars[a["character"]],
                    **{k: v for k, v in a.items() if k != "character"},
                }
                for a in spec["actors"]
            ]
            shots.append(spec)
        scenes = [
            {**scene, "reference_asset_id": images[scene["reference"]]}
            for scene in recipe.get("scenes", [])
        ]
        for scene in scenes:
            scene.pop("reference")
        plan = {
            "style": recipe["style"],
            "budget": recipe["budget"],
            "shots": shots,
            "scenes": scenes,
        }
        pstate = state("production")
        call(
            prefix + "/production",
            "PUT",
            {
                "revision": pstate["revision"],
                "source_sha256": pstate["source_sha256"],
                "plan": plan,
            },
        )
        for shot in shots:
            call(
                prefix + "/production/" + shot["id"] + "/approve",
                "POST",
                {"revision": state("production")["revision"]},
            )
        if continuity_review:
            for shot in sorted(shots, key=lambda s: s["after_byte"]):
                if shot.get("continuity", {}).get("scene_id"):
                    call(
                        prefix + "/production/" + shot["id"] + "/continuity-check",
                        "POST",
                        {
                            "revision": state("production")["revision"],
                            "decision": "passed",
                            "reviewer": continuity_review["reviewer"],
                            "notes": continuity_review["notes"][shot["id"]],
                        },
                    )
        call(
            prefix + "/production/apply",
            "POST",
            {
                "revision": state("production")["revision"],
                "reader_revision": state("reader")["revision"],
            },
        )
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        archive = client.get(prefix + "/bundle")
        archive.raise_for_status()
        target.write_bytes(archive.content)
        exported = wait(call(prefix + "/reader/exports", "POST"))
        report = {
            "project_id": project["id"],
            "reader_url": base + "/read/" + project["id"],
            "bundle": str(target),
            "export": exported,
            "source_bytes": project["byte_length"],
            "art_review": "pending_user_review",
        }
        target.with_suffix(".build.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("recipe")
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--output", required=True)
    p.add_argument("--with-local-audio", action="store_true")
    args = p.parse_args()
    print(
        json.dumps(
            build(args.recipe, args.base, args.output, args.with_local_audio),
            ensure_ascii=False,
        )
    )
