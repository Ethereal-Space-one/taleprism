"""Build only the reviewed public release assets. No publishing, API keys or author stores."""

import argparse
import hashlib
import json
import tempfile
import urllib.request
from pathlib import Path

from release_files import ROOT, source_files
from release_version import PREFIX, VERSION


def digest(b):
    return hashlib.sha256(b).hexdigest()


def starter_entries():
    # Separate positive list: adding a new directory to examples/ never puts it in the starter.
    roots = {
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "docs/快速上手.md",
        f"docs/RELEASE-v{VERSION}.md",
    }
    prefixes = (
        "prompts/",
        "schemas/",
        "examples/last-light/",
        "examples/chibi/",
        "samples/last-light/",
        "examples/reading-lab/",
    )
    files = {
        "taleprism/" + n: p.read_bytes()
        for n, p in source_files()
        if n in roots or n.startswith(prefixes)
    }
    files["taleprism/README.md"] = (
        f"""# Taleprism {VERSION} · Prompt starter
从 [八套提示模板](prompts/README.md)、[三镜头教程](examples/last-light/README.md) 或 [创意实验](examples/reading-lab/README.md) 开始。无需安装软件即可阅读这些文本。
模板中的文字只是制作示例。作者决定是否采用；独立阅读器不收录工作备份。软件与素材许可分别见 LICENSE、THIRD_PARTY_NOTICES.md 与各示例的来源说明。
This starter contains templates, schemas and public tutorial material. Download the source to run the workbench, or a reader ZIP to read offline. No accounts or model service are required for reading.
"""
    ).encode()
    return files


def build_starter(out):
    from build_encounter_readers import pack

    p = out / (PREFIX + "-prompt-starter.zip")
    p.write_bytes(pack(starter_entries()))
    return p


def fetch_public_inputs(dst):
    from build_public_example_pairs import PINS

    base = "https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.3.3/"
    for example, pins in PINS.items():
        for kind in ["project", "reader"]:
            n = f"taleprism-v0.3.3-{example}-{kind}.zip"
            with urllib.request.urlopen(base + n, timeout=90) as r:
                raw = r.read(160000001)
            if len(raw) > 160000000 or digest(raw) != pins[kind]:
                raise ValueError(
                    "Public release input does not match its published digest: " + n
                )
            (dst / n).write_bytes(raw)


def main():
    from build_encounter_readers import build as encounters
    from build_public_example_pairs import build as pairs
    from export_prompt_kit import outputs
    from package_source import package_source

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / ".release" / ("v" + VERSION))
    p.add_argument(
        "--public-inputs",
        type=Path,
        help="Directory with four pinned public v0.3.3 example ZIPs; build offline.",
    )
    p.add_argument(
        "--chibi-source",
        type=Path,
        help="Legacy CI switch: verify v0.1 public Chibi, then download four pinned v0.3.3 release assets if --public-inputs is absent.",
    )
    p.add_argument(
        "--reuse-verified-pairs",
        action="store_true",
        help="Re-use the four already built, hash-checked files in --output; never use this on untrusted inputs.",
    )
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for n, expected in outputs().items():
        if (ROOT / n).read_text() != expected:
            raise ValueError("Out-of-date prompt/schema: " + n)
    if (
        args.chibi_source
        and digest(args.chibi_source.read_bytes())
        != "b8597e51982dfc23acd10cdb99caf0e75cb616a599e4049ce9fb217a87adf84a"
    ):
        raise ValueError("Unrecognized legacy Chibi source")
    if not args.reuse_verified_pairs:
        with tempfile.TemporaryDirectory(prefix="public-release-inputs-") as t:
            src = args.public_inputs
            if not src:
                if not args.chibi_source:
                    p.error(
                        "--public-inputs (or explicit --chibi-source download mode) is required"
                    )
                src = Path(t)
                fetch_public_inputs(src)
            pairs(src, out)
    data = json.loads((out / "public-example-pairs.json").read_bytes())
    # A sidecar must not authorize other paths or its own substituted inputs.
    catalog = json.loads((ROOT / "samples/content-packs/catalog.json").read_bytes())
    expected = {
        f"{PREFIX}-{e['id']}-{kind}.zip": (
            e["id"],
            kind,
            (e if kind == "project" else e["reader"])["sha256"],
        )
        for e in catalog
        if e["id"] in {"chibi", "last-light"}
        for kind in ("project", "reader")
    }
    records = data["artifacts"]
    if (
        len(expected) != 4
        or len(records) != 4
        or {a["file"] for a in records} != set(expected)
    ):
        raise ValueError("Expected both classic public reader/editable pairs.")
    for a in records:
        raw = (out / a["file"]).read_bytes()
        if (
            (a["example"], a["kind"], a["sha256"]) != expected[a["file"]]
            or len(raw) != a["bytes"]
            or digest(raw) != a["sha256"]
        ):
            raise ValueError(
                "Frozen project/reader or its catalog pin changed: " + a["file"]
            )
    docs = encounters(out)
    starter = build_starter(out)
    pack = {
        "file": starter.name,
        "bytes": starter.stat().st_size,
        "sha256": digest(starter.read_bytes()),
        "kind": "starter",
        "example": None,
    }
    manifest = {
        "product": "Taleprism",
        "version": VERSION,
        "channel": "prerelease",
        "commit": None,
        "artifacts": [pack, *data["artifacts"], *docs],
        "checks": {
            "examples": data["checks"],
            "pages_deployment": "unchanged",
            "reader_only_editions": ["the-door-left-open", "the-margin"],
            "live_provider": "not_exercised",
            "physical_ios_safari": "not_exercised",
        },
    }
    (out / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    package_source(out / (PREFIX + "-source.zip"))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
