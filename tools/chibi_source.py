"""Offline, bounded verification of Chibi's immutable public bootstrap input."""

import hashlib
import io
import json
import stat
import zipfile
from pathlib import PurePosixPath

LIMIT = 160_000_000


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def read_zip(raw):
    """Read bytes, never extract paths or execute anything from the input package."""
    if len(raw) > LIMIT:
        raise ValueError("公开包超过160MB。")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if (
                len(infos) > 3000
                or len(set(names)) != len(names)
                or sum(i.file_size for i in infos) > LIMIT
            ):
                raise ValueError("公开包文件重复或解压大小超限。")
            for info in infos:
                path = PurePosixPath(info.filename)
                if (
                    info.is_dir()
                    or path.is_absolute()
                    or ".." in path.parts
                    or "\\" in info.filename
                    or path.as_posix() != info.filename
                    or stat.S_ISLNK(info.external_attr >> 16)
                    or info.flag_bits & 1
                ):
                    raise ValueError("公开包包含非法路径、链接或加密条目。")
            return {i.filename: archive.read(i) for i in infos}
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError("公开包无法读取。") from exc


def verify_inventory(files):
    try:
        manifest = json.loads(files["storygal-delivery.json"])
        entries = manifest["files"]
        if manifest["schema_version"] != 1 or set(entries) != set(files) - {
            "storygal-delivery.json"
        }:
            raise ValueError("公开包内部清单与文件集合不匹配。")
        for name, entry in entries.items():
            if (
                len(files[name]) != entry["bytes"]
                or digest(files[name]) != entry["sha256"]
            ):
                raise ValueError("公开包内部文件校验失败：" + name)
        return manifest
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("公开包内部清单无效。") from exc


def verify_content(files, recipe):
    """Source anchors, media identity and inherited choreography are checked independently."""
    try:
        content = json.loads(files["reader.json"])
        original = files["storygal-source/original.txt"]
        canonical = files["storygal-source/source.utf8.txt"]
        if (
            digest(original) != recipe["source_sha256"]
            or canonical != original
            or content["project"]["sha256"] != digest(original)
            or content["project"]["canonical_sha256"] != digest(canonical)
            or content["project"]["id"] != recipe["public_work_id"]
        ):
            raise ValueError("公开包原文、工作副本或作品身份不匹配。")
        media = content["media"]
        counts = {
            "illustrations": len(content["config"]["illustrations"]),
            "characters": len(content["characters"]),
            "portraits": sum(a["type"] == "figure" for a in media.values()),
            "presentations": len(content["presentations"]),
            "map_phases": len(content["map"]["phases"]),
            "media": len(media),
        }
        if any(recipe["expected"][k] != v for k, v in counts.items()):
            raise ValueError("公开包内容数量不符合赤壁配方。")
        if content["config"]["presentations"] != content["presentations"]:
            raise ValueError("公开包呈现记录不一致。")
        previous_end = 0
        for block in content["blocks"]:
            start, end = block["byte_start"], block["byte_end"]
            if (
                start < previous_end
                or canonical[start:end].decode() != block["text"]
                or canonical[previous_end:start].decode().strip()
                or block["audio"]
            ):
                raise ValueError("公开包段落与原文不一致或包含音频。")
            previous_end = end
            for run in block["runs"]:
                if (
                    not start <= run["byte_start"] < run["byte_end"] <= end
                    or canonical[run["byte_start"] : run["byte_end"]].decode()
                    != run["text"]
                    or run["take_id"]
                    or (
                        run["speaker_id"]
                        and run["speaker_id"] not in content["characters"]
                    )
                ):
                    raise ValueError("公开包正文片段不一致。")
        if canonical[previous_end:].decode().strip():
            raise ValueError("公开包遗漏原文段落。")
        for aid, asset in media.items():
            if (
                aid != asset["id"]
                or asset["type"] not in {"image", "figure"}
                or asset["url"] != f"./media/{aid}.png"
                or digest(files[asset["url"][2:]]) != asset["sha256"]
            ):
                raise ValueError("公开包图片路径、类型或哈希不匹配。")
        if any(
            n.lower().endswith((".wav", ".mp3", ".aiff", ".m4a", ".ogg")) for n in files
        ):
            raise ValueError("公开源包不得包含音频。")
        return content
    except (KeyError, TypeError, AttributeError, UnicodeError) as exc:
        raise ValueError("公开包阅读数据不完整。") from exc


def preflight(source, recipe_path, review_path):
    """All review inputs are read once and verified before a project is created."""
    recipe_raw, review_raw = recipe_path.read_bytes(), review_path.read_bytes()
    recipe, review = json.loads(recipe_raw), json.loads(review_raw)
    raw = source.read_bytes()
    expected_hash = recipe["source_archive"]["sha256"]
    if digest(raw) != expected_hash:
        raise ValueError("源包不是配方固定的 v0.1.0 公开阅读包；未创建工程。")
    files = read_zip(raw)
    verify_inventory(files)
    content = verify_content(files, recipe)
    expected = {
        "reader.json",
        "storygal-source/original.txt",
        "storygal-source/source.utf8.txt",
    } | {a["url"][2:] for a in content["media"].values()}
    dependencies = review.get("dependencies")
    if (
        review.get("format") != "taleprism-chibi-visual-review"
        or review.get("version") != 1
        or review.get("reviewer") != "assistant"
        or review.get("creator_final_art_review") != "pending"
        or review.get("source_archive_sha256") != expected_hash
        or review.get("recipe_sha256") != digest(recipe_raw)
        or not isinstance(dependencies, dict)
        or set(dependencies) != expected
        or any(dependencies[n] != digest(files[n]) for n in expected)
    ):
        raise ValueError(
            "逐图制作检查失效：请重新核对配方、原文与全部图片，不可直接改哈希。"
        )
    image_reviews = review.get("images", [])
    if len(image_reviews) != len(content["media"]) or {
        r.get("asset_id") for r in image_reviews
    } != set(content["media"]):
        raise ValueError("逐图检查记录不完整。")
    for item in image_reviews:
        asset = content["media"][item["asset_id"]]
        if (
            item.get("sha256") != asset["sha256"]
            or item.get("sample_key") != asset["sample_key"]
            or not isinstance(item.get("inspection"), str)
            or len(item["inspection"].strip()) < 8
        ):
            raise ValueError("逐图检查与图片不匹配。")
    notes = review.get("shots")
    if (
        not isinstance(notes, dict)
        or set(notes) != {s["id"] for s in recipe["plan"]["shots"]}
        or any(not isinstance(n, str) or len(n.strip()) < 8 for n in notes.values())
    ):
        raise ValueError("逐镜头检查记录不完整。")
    return recipe, review, files, content, recipe_raw, review_raw
