"""Create the two original public reader-only examples solely from reviewed source inputs."""

import argparse
import hashlib
import io
import json
import stat
import uuid
import zipfile
from pathlib import Path

from release_version import PREFIX, ROOT, VERSION
from storygal.portable_reader import TEMPLATE, embed_story
from storygal.reader_export import read_runtime
from storygal.soundscape_audio import render_soundscape

DEMO = {
    "the-door-left-open": ("留门", True, 6, False),
    "the-margin": ("留白处", False, None, True),
}
RIGHTS = "本文和插图为 Taleprism 原创示例。声音是本地合成，不是外部录音。文本、插图和合成声景可按随附 MIT 许可使用。阅读器依赖各自的许可证位于 licenses/。\nOriginal public example text, art and procedural audio: MIT, see licenses/Taleprism-MIT.txt. Runtime dependency notices apply separately.\n"


def rawjson(o):
    return (json.dumps(o, ensure_ascii=False, indent=2) + "\n").encode()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def pack(files):
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w") as z:
        for name, raw in sorted(files.items()):
            e = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            e.create_system = 3
            e.external_attr = (
                stat.S_IFREG | (0o755 if name.endswith(".command") else 0o644)
            ) << 16
            z.writestr(e, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return memory.getvalue()


def build(out):
    out.mkdir(parents=True, exist_ok=True)
    rt = read_runtime(ROOT / "frontend/dist/reader")
    modules = ROOT / "frontend/node_modules"
    notices = {"Taleprism-MIT.txt": ROOT / "LICENSE"}
    for d in ["react", "react-dom", "scheduler"]:
        notices[d + ".txt"] = modules / d / "LICENSE"
    for s, t in [
        ("LICENSE", "opencc-js.txt"),
        ("THIRD_PARTY_LICENSES.md", "opencc-js-THIRD_PARTY_LICENSES.md"),
        ("LICENSES/Apache-2.0.txt", "opencc-js-Apache-2.0.txt"),
    ]:
        notices[t] = modules / "opencc-js" / s
    records = []
    for slug, (title, rain, car, pencil) in DEMO.items():
        p = ROOT / "examples/encounters" / slug
        source = (p / "source.txt").read_bytes()
        story = json.loads((p / "reading.json").read_bytes())
        if (
            story["project"]["canonical_sha256"] != sha(source)
            or story["project"]["sha256"] != sha(source)
            or story["project"]["rights_status"] != "owned"
            or story["config"]["title"] != title
            or story["issues"]
            or story["preview"]
        ):
            raise ValueError("Public showcase/source mismatch")
        if set(story) != {
            "schema_version",
            "project",
            "versions",
            "config",
            "blocks",
            "characters",
            "media",
            "map",
            "preview",
            "issues",
            "presentations",
            "map_entries",
        }:
            raise ValueError("Unexpected story member")
        files = {
            "index.html": embed_story(TEMPLATE, story).encode(),
            "reader.json": rawjson(story),
            "RIGHTS.txt": RIGHTS.encode(),
            "storygal-source/original.txt": source,
            "storygal-source/source.utf8.txt": source,
            **{"assets/" + n: b for n, b in rt.items()},
            **{"licenses/" + n: path.read_bytes() for n, path in notices.items()},
        }
        description = (
            "雨落在铁篷，声音与湿路上的细雨在相应段落相遇。"
            if rain
            else "静态的桌角、第五段的回声和第六段的铅笔响，留在各自的原文位置。"
        )
        files["README.txt"] = (
            title
            + f" · Taleprism v{VERSION} public preview\n"
            + description
            + "\n完整解压并打开 index.html。已采用的演绎随阅读自动出现，封面可选「安静阅读」。若浏览器拦下声音，点击「开启声音」。\nExtract fully and open index.html in your browser. Offline, no API key or application required. Quiet reading, pause, mute and reduced motion are respected.\n"
        ).encode()
        if sorted(v["type"] for v in story["media"].values()) != ["audio", "image"]:
            raise ValueError("Unexpected artwork or sound")
        for mid, a in story["media"].items():
            ext = "png" if a["type"] == "image" else "wav"
            name = "media/" + str(uuid.UUID(mid)) + "." + ext
            if a["id"] != mid or a["url"] != "./" + name:
                raise ValueError("Unexpected media reference")
            b = (
                (p / "plate.png").read_bytes()
                if ext == "png"
                else render_soundscape(rain, car, pencil=pencil)
            )
            if sha(b) != a["sha256"]:
                raise ValueError("Adopted source media mismatch")
            files[name] = b
        for b in story["blocks"]:
            if source[b["byte_start"] : b["byte_end"]].decode() != b["text"]:
                raise ValueError("Text anchor mismatch")
        for n in ["reader_launcher.py", "verify_package.py"]:
            files[n] = (ROOT / "tools" / n).read_bytes()
        for n in ["打开阅读器.command", "停止阅读器.command"]:
            files[n] = (ROOT / "tools/reader_launcher.command").read_bytes()
        memo = {
            n: {"bytes": len(b), "sha256": sha(b)} for n, b in sorted(files.items())
        }
        files["storygal-delivery.json"] = rawjson(
            {
                "schema_version": 1,
                "export_id": str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        "taleprism-preview:" + slug + ":" + sha(rawjson(memo)),
                    )
                ),
                "versions": story["versions"],
                "files": memo,
            }
        )
        raw = pack(files)
        name = f"{PREFIX}-{slug}-reader.zip"
        (out / name).write_bytes(raw)
        records.append(
            {
                "file": name,
                "bytes": len(raw),
                "sha256": sha(raw),
                "example": slug,
                "kind": "reader-only",
            }
        )
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(build(parser.parse_args().output), ensure_ascii=False, indent=2))
