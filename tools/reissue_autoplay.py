"""Update the runtime of an explicitly hash-pinned portable reader without altering its book.

The original is never edited. The output receives a fresh package identity; source,
media, credits, launcher, embedded story and reading identity must remain byte-exact.
This helper supports the legacy guide text below and refuses unknown package layouts.
"""

import argparse
import hashlib
import io
import json
import stat
import uuid
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from chibi_source import read_zip

RUNTIME = ("reader.css", "reader.js")
INVENTORY = "storygal-delivery.json"
CHANGED = {"README.txt", INVENTORY, *("assets/" + n for n in RUNTIME)}
OLD_GUIDE = (
    "段落朗读为作者提供的录音，须主动点播；已制作的对白配音与段落朗读分别控制。"
    "插图默认静止；仅已配置的展开插图可主动开启动效，减少动态效果时保持静止。"
    "缺失图片或声音时仍可读正文；请重新完整解压原 ZIP 修复素材。"
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(truth, message):
    if not truth:
        raise ValueError(message)


def jsonbytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode()


def summary(files):
    return {
        n: {"bytes": len(b), "sha256": sha(b)}
        for n, b in sorted(files.items())
        if n != INVENTORY
    }


def loadzip(raw):
    # Share bounded entry-count/decoded-size, path, CRC and link validation
    # with the public release builder. No ZIP entries are executed or extracted.
    files = read_zip(raw)
    inv = json.loads(files[INVENTORY])
    require(summary(files) == inv["files"], "File inventory mismatch")
    return files, inv


class Embedded(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active = False
        self.story = []

    def handle_starttag(self, tag, attrs):
        self.active = (
            tag == "script"
            and dict(attrs).get("id") == "taleprism-story"
            and dict(attrs).get("type") == "application/json"
        )

    def handle_data(self, value):
        if self.active:
            self.story.append(value)

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False


def inspect_story(files):
    c = json.loads(files["reader.json"])
    parser = Embedded()
    parser.feed(files["index.html"].decode())
    require(
        len(parser.story) == 1 and json.loads(parser.story[0]) == c,
        "Embedded reader differs",
    )
    source = files["storygal-source/original.txt"]
    require(
        c["config"]["title"]
        and c["project"]["id"]
        and c["project"]["sha256"] == sha(source)
        and c["project"]["canonical_sha256"]
        == sha(files["storygal-source/source.utf8.txt"]),
        "Book identity mismatch",
    )
    for asset in c["media"].values():
        n = asset["url"].removeprefix("./")
        require(
            n.startswith("media/") and sha(files[n]) == asset["sha256"],
            "Media digest mismatch",
        )
    return c


def verified_runtime(runtime_dir):
    sums = json.loads((runtime_dir / "runtime-checksums.json").read_bytes())
    require(set(sums) == set(RUNTIME), "Unexpected build checksum inventory")
    files = {n: (runtime_dir / n).read_bytes() for n in RUNTIME}
    require(
        all(b and sha(b) == sums[n] for n, b in files.items()),
        "Built reader digest mismatch",
    )
    return files


def packed(files):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as z:
        for n, b in sorted(files.items()):
            i = zipfile.ZipInfo(n, (1980, 1, 1, 0, 0, 0))
            i.create_system = 3
            i.external_attr = (
                stat.S_IFREG | (0o755 if n.endswith(".command") else 0o644)
            ) << 16
            z.writestr(i, b, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return result.getvalue()


def reissue(baseline, runtime_dir, expected_sha):
    prev = sha(baseline)
    require(prev == expected_sha, "Expected baseline digest mismatch")
    old, inv = loadzip(baseline)
    content = inspect_story(old)
    runtime = verified_runtime(runtime_dir)
    require(
        runtime["reader.js"] != old["assets/reader.js"],
        "Runtime is still the previous build",
    )
    new = dict(old)
    for f, b in runtime.items():
        new["assets/" + f] = b
    readme = old["README.txt"].decode()
    require(readme.count(OLD_GUIDE) == 1, "Unknown older guide")
    guide = (
        "本书使用 Taleprism v0.9.0 阅读器。封面安静；开始阅读后，顺着原文读到相应位置，"
        "已编排的声景、动效或回声折页会在那里出现。可暂停自动效果、静音；系统选择减少动态效果时，"
        "插图保持静止。若浏览器拦住声音，按页面提示开启即可，无需更改浏览器权限。"
        "缺失素材时正文仍可读。\n\n"
        "The cover stays quiet. Read forward to encounter the edition’s effects in place. "
        "You can pause automatic effects or mute sound. Reduced motion keeps the illustration still. "
        "If the browser blocks sound, use the reader’s one-time sound action."
    )
    new["README.txt"] = readme.replace(OLD_GUIDE, guide).encode()
    sums = {n: sha(b) for n, b in sorted(runtime.items())}
    origin = {
        "release": "0.9.0",
        "prior_reader_sha256": prev,
        "prior_export_id": inv["export_id"],
        "runtime_sha256": sums,
    }
    # Export-package identity changes, not the work identity used by records/bookmarks.
    build_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL, "urn:taleprism:reader-reissue:" + sha(jsonbytes(origin))
        )
    )
    new[INVENTORY] = jsonbytes(
        {**inv, "export_id": build_id, "runtime_reissue": origin, "files": summary(new)}
    )
    out = packed(new)
    back, verified = loadzip(out)
    require(
        set(old) == set(back)
        and all(old[f] == back[f] for f in old if f not in CHANGED),
        "Content or file set changed",
    )
    require(
        inspect_story(back) == content and verified["versions"] == inv["versions"],
        "Story changed",
    )
    return out, {
        "title": content["config"]["title"],
        "work_id": content["project"]["id"],
        "reader_sha256": sha(out),
        **origin,
        "export_id": build_id,
        "source_bytes": len(back["storygal-source/original.txt"]),
        "source_sha256": content["project"]["sha256"],
        "reader_json_sha256": sha(back["reader.json"]),
        "index_sha256": sha(back["index.html"]),
        "entries": len(back),
        "changed": sorted(n for n in back if old[n] != back[n]),
        "media_sha256": {n: sha(b) for n, b in back.items() if n.startswith("media/")},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument(
        "--runtime",
        type=Path,
        required=True,
        help="frontend/dist/reader from verified v0.9.0 source",
    )
    p.add_argument(
        "--output", type=Path, required=True, help="new .zip (refuses to overwrite)"
    )
    p.add_argument("--baseline-sha256", required=True)
    args = p.parse_args()
    raw, report = reissue(
        args.baseline.read_bytes(), args.runtime, args.baseline_sha256
    )
    with args.output.open("xb") as f:
        f.write(raw)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
