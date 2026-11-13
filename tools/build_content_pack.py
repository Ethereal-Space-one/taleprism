"""Build a local sample solely through public APIs, from a content-only recipe."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import httpx
from storygal.review import top_dialogues
from storygal.text import decode_source


def resolve_dialogues(recipe, source_raw):
    """Resolve tasks against the same canonical bytes/parser used by project ingestion.

    Recipe anchors are half-open UTF-8 ranges of an entire top-level quote's content,
    without its outer quotation marks. Never persist the parser's temporary UUIDs.
    """
    _, source = decode_source(source_raw)
    characters = recipe.get("characters")
    tasks = recipe.get("dialogues")
    if not isinstance(characters, list) or not isinstance(tasks, list):
        raise ValueError("配方 characters 和 dialogues 必须为列表。")  # noqa: TRY004 -- invalid recipe
    names, normalized_names = set(), set()
    for index, character in enumerate(characters, 1):
        name = character.get("name") if isinstance(character, dict) else None
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 40
            or any(ord(c) < 32 for c in name)
        ):
            raise ValueError(
                f"characters 第 {index} 项的 name 必须为 1–40 个字符的非空姓名，不能包含控制字符。"
            )
        description = character.get("description")
        if not isinstance(description, str) or len(description) > 2000:
            raise ValueError(
                f"characters 第 {index} 项必须提供 description，且为最多 2,000 个字符的字符串。"
            )
        if name.strip() in normalized_names:
            raise ValueError(f"配方人物姓名重复：{name!r}；请使用不同姓名区分说话人。")
        names.add(name)
        normalized_names.add(name.strip())

    by_text, by_range = {}, {}
    for dialogue in top_dialogues(source):
        by_text.setdefault(dialogue["text"], []).append(dialogue)
        by_range[(dialogue["byte_start"], dialogue["byte_end"])] = dialogue
    # In valid UTF-8, each non-continuation byte starts a character; EOF is also a boundary.
    boundaries = {i for i, b in enumerate(source) if b & 0xC0 != 0x80} | {len(source)}
    allowed = {"text", "character", "voice_prefix", "byte_start", "byte_end"}
    resolved, occupied = [], {}
    for index, task in enumerate(tasks, 1):
        label = f"dialogues 第 {index} 项"
        if not isinstance(task, dict):
            raise ValueError(f"{label} 必须为对象。")  # noqa: TRY004 -- invalid recipe
        if unknown := set(task) - allowed:
            raise ValueError(f"{label} 含未知字段：{', '.join(sorted(unknown))}。")
        for field in ("text", "character"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise ValueError(f"{label} 的 {field} 必须为非空字符串。")
        if "voice_prefix" in task and (
            not isinstance(task["voice_prefix"], str)
            or not task["voice_prefix"].strip()
            or task["voice_prefix"] != task["voice_prefix"].strip()
            or any(ord(c) < 32 for c in task["voice_prefix"])
        ):
            raise ValueError(
                f"{label} 的 voice_prefix 必须为非空字符串，不能包含首尾空白或控制字符；不配音请省略此字段。"
            )
        if task["character"] not in names:
            raise ValueError(
                f"{label} 的 character 在配方人物列表中不存在：{task['character']!r}。"
            )
        if ("byte_start" in task) != ("byte_end" in task):
            raise ValueError(f"{label} 必须同时提供 byte_start 和 byte_end。")
        if "byte_start" in task:
            start, end = task["byte_start"], task["byte_end"]
            if type(start) is not int or type(end) is not int:
                raise ValueError(
                    f"{label} 的 byte_start、byte_end 必须为整数，不能为布尔值。"
                )
            if not 0 <= start < end <= len(source):
                raise ValueError(
                    f"{label} 锚点范围无效，需满足 0 <= byte_start < byte_end <= 原文字节数。"
                )
            if start not in boundaries or end not in boundaries:
                raise ValueError(f"{label} 锚点必须落在 UTF-8 字符边界。")
            if source[start:end] != task["text"].encode("utf-8"):
                raise ValueError(
                    f"{label} 的 text 与原文不一致：锚点范围 [{start}, {end})。"
                )
            if (start, end) not in by_range:
                raise ValueError(
                    f"{label} 锚点必须覆盖引号内一条完整对白，不能包含外层引号、截取片段、跨对白或指向旁白。"
                )
        else:
            matches = by_text.get(task["text"], [])
            if not matches:
                raise ValueError(
                    f"{label} 未找到完整匹配的原文对白：{task['text']!r}。"
                )
            if len(matches) != 1:
                raise ValueError(
                    f"{label} 原文对白重复（{len(matches)} 处），请同时提供 byte_start 和 byte_end；不会猜选。"
                )
            start, end = matches[0]["byte_start"], matches[0]["byte_end"]
        # Complete top-level dialogue ranges never partially overlap. A repeated range
        # (including mixed anchored/text-only tasks) is the only remaining overlap case.
        if (start, end) in occupied:
            raise ValueError(
                f"{label} 与第 {occupied[(start, end)]} 项范围重叠，是重复任务；一条对白只能分配一次。"
            )
        occupied[(start, end)] = index
        resolved.append({**task, "byte_start": start, "byte_end": end})
    return resolved


def resolve_voices(dialogue_tasks, capabilities):
    """Resolve all requested voices from the server snapshot before the first write."""
    if (
        not isinstance(capabilities, dict)
        or capabilities.get("provider") != "macos-say"
        or type(capabilities.get("available")) is not bool
        or not isinstance(capabilities.get("voices"), list)
        or any(
            not isinstance(voice, str) or not voice.strip()
            for voice in capabilities.get("voices", [])
        )
    ):
        raise ValueError("服务器本机语音能力响应格式无效；未创建项目，未合成语音。")
    requested = [task for task in dialogue_tasks if "voice_prefix" in task]
    if requested and not capabilities["available"]:
        raise ValueError(
            "服务器本机语音合成不可用，请检查服务器音色和 ffmpeg；未创建项目，未合成语音。"
        )
    voices, character_voices = {}, {}
    for task in requested:
        prefix = task["voice_prefix"]
        matches = {
            voice for voice in capabilities["voices"] if voice.startswith(prefix)
        }
        if not matches:
            raise ValueError(
                f"voice_prefix {prefix!r} 在服务器上没有匹配音色；未创建项目，未合成语音。"
            )
        if len(matches) != 1:
            raise ValueError(
                f"voice_prefix {prefix!r} 匹配多个服务器音色，请提供能唯一匹配的更完整名称；未创建项目，未合成语音。"
            )
        voice = next(iter(matches))
        character = task["character"]
        if character in character_voices and character_voices[character] != voice:
            raise ValueError(
                f"人物 {character!r} 的对白请求了不同音色，请统一人物音色；未创建项目，未合成语音。"
            )
        voices[prefix] = character_voices[character] = voice
    return voices


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

    dialogue_tasks = resolve_dialogues(recipe, inputs[recipe["source"]])

    # Upload exactly the bytes checked above; never reread mutable inputs after preflight.
    with client_factory(base_url=base, trust_env=False, timeout=180) as client:

        def call(path, method="GET", body=None, **kwargs):
            r = client.request(method, path, json=body, **kwargs)
            r.raise_for_status()
            return r.json()

        voices = {}
        if with_audio:
            try:
                capabilities = call("/api/speech/capabilities")
            except (httpx.HTTPError, ValueError):
                # Do not echo response bodies, URLs with credentials, or transport details.
                raise ValueError(
                    "无法读取服务器本机语音能力，请检查连接及服务版本；未创建项目，未合成语音。"
                ) from None
            voices = resolve_voices(dialogue_tasks, capabilities)

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
        for item in dialogue_tasks:
            current = state("review")
            found = [
                d
                for d in current["dialogues"]
                if all(
                    d[key] == item[key] for key in ("byte_start", "byte_end", "text")
                )
            ]
            if len(found) != 1:
                raise ValueError(
                    "服务器对白切分与本地预检不一致，请确认构建工具与服务版本一致："
                    f"[{item['byte_start']}, {item['byte_end']})"
                )
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
                voice = voices[item["voice_prefix"]]
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
