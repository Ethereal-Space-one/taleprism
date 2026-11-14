"""Maker-only Chibi lineage. No generation, owner approval, or reader-state changes.

The original requests are evidence; the later recipe and reusable templates are not
proof of how an existing image was generated. Unknown history stays explicitly null.
"""

import argparse
import json
from pathlib import Path

from chibi_source import digest, preflight

ROOT = Path(__file__).resolve().parents[1]
TRACE = "examples/chibi/maker-trace-v1.json"
GATE = "examples/chibi/paired-shot-continuity-v1.json"
GUIDE = "examples/chibi/MAKER-PROVENANCE.md"
WORKSHEET = "prompts/paired-shot-continuity-worksheet.json"
PROMPTS = "samples/reader/narrative-v1/prompts.json"
GENERATIONS = "samples/reader/narrative-v1/generation-files.json"
REVISIONS = "samples/reader/narrative-v1/psychology-revisions.json"
RECIPE = "examples/chibi/rebuild-v0.2.0.json"
REVIEW = "examples/chibi/visual-review-v0.2.0.json"
GROUP = ["huanggai-departure", "caocao-watch", "fire-panorama"]


def pointer(path, selector, value):
    return {"path": path, "pointer": selector, "value_sha256": digest(value.encode())}


def anchor(source, quote):
    raw = quote.encode()
    start = source.find(raw)
    if start < 0:
        raise ValueError("制作来源引文不在固定原文中：" + quote)
    return {"quote": quote, "byte_start": start, "byte_end": start + len(raw)}


def reference(recorded, role, media):
    # Preserve historical spelling, including paths relative to a past workspace.
    # Resolved pointers are a separate modern index, never a silent path correction.
    name = Path(recorded).name
    key = {
        "fleet-v1.png": "fleet",
        "kongming-v1.png": "kongming",
        "zhouyu-v1.png": "zhouyu",
        "zhaoyun-base-v1.png": "zhaoyun",
        "zhangfei-base-v1.png": "zhangfei",
        "guanyu-base-v1.png": "guanyu",
        "caocao-base-v1.png": "caocao",
        "huanggai-base-v1.png": "huanggai",
    }.get(name)
    asset = media.get(key)
    path = ("samples/reader/" if key == "fleet" else "samples/characters/") + name
    if "/expansion-" in recorded:
        path = "samples/characters/" + recorded.split("/characters/", 1)[1]
    if role == "edit_target":
        path = "samples/reader/narrative-v1/" + name
    return {
        "recorded_path": recorded,
        "resolved_source_path": path,
        "role": role,
        "asset_id": asset["id"] if asset else None,
        "sha256": asset["sha256"] if asset else None,
        "hash_status": "verified_public_asset" if asset else "not_in_public_input",
        "scope": {
            "style_only": "水墨、水彩、纸色与光色；不是舰队几何母版或跨镜头空间约束。",
            "identity_only": "人物身份、面貌与服装；不是原场景布置或固定姿势。",
            "edit_target": "已有画面编辑对象；旧版 PNG 不在固定公开输入内，不能补造字节哈希。",
        }[role],
    }


def make_trace(files, public, root=ROOT):
    root = Path(root)
    historical = files["storygal-source/narrative-v1/prompts.json"]
    if historical != (root / PROMPTS).read_bytes():
        raise ValueError("历史逐图请求与固定公开输入不同；不能改写历史提示词。")
    requests = json.loads(historical)
    generations = json.loads((root / GENERATIONS).read_bytes())
    recipe = json.loads((root / RECIPE).read_bytes())
    review = json.loads((root / REVIEW).read_bytes())
    shots = {s["id"]: s for s in recipe["plan"]["shots"]}
    media = {a["sample_key"]: a for a in public["media"].values()}
    source = files["storygal-source/original.txt"]
    records = []
    for index, image in enumerate(requests["images"]):
        key = image["key"]
        asset = media["narrative:" + key]
        if digest(files[asset["url"][2:]]) != asset["sha256"]:
            raise ValueError("实际结果图片哈希不匹配：" + key)
        edits = image.get("edits", [])
        original_file = edits[0]["reference"] if edits else image["file"]
        original_id = generations[key + "-initial"] if edits else generations[key]
        current_pointer = f"/images/{index}/edits/{len(edits) - 1}/prompt" if edits else (
            f"/images/{index}/prompt"
        )
        current_prompt = edits[-1]["prompt"] if edits else image["prompt"]
        records.append(
            {
                "key": key,
                "title": image["title"],
                "current_file": "samples/reader/narrative-v1/" + image["file"],
                "source_moment": {
                    "recorded_marker": anchor(source, image["marker"]),
                    "recorded_edit_moment": edits[-1].get("source_moment") if edits else None,
                    "retrospective_description": shots[key]["moment"],
                    "retrospective_source_evidence": anchor(source, shots[key]["evidence"]),
                    "description_basis": RECIPE + "#/plan/shots; recorded after generation",
                    "interpretation": shots[key]["interpretation"],
                },
                "original_generation": {
                    "date": requests["date"],
                    "file": original_file,
                    "generation_artifact": original_id,
                    "result_sha256": asset["sha256"] if not edits else None,
                    "hash_status": "verified_public_asset" if not edits else "not_in_public_input",
                    "prompt": pointer(PROMPTS, f"/images/{index}/prompt", image["prompt"]),
                    "references": [
                        reference(ref, "style_only" if n == 0 else "identity_only", media)
                        for n, ref in enumerate(image["refs"])
                    ],
                },
                "edits": [
                    {
                        "sequence": n + 1,
                        "date": edit.get("date"),
                        "date_status": "recorded" if edit.get("date") else "not_recorded_per_edit",
                        "edit_target": reference(edit["reference"], "edit_target", media),
                        "output_file": edit.get("file", image["file"]),
                        "output_file_basis": "explicit_edit_field" if edit.get("file") else (
                            "parent_current_file_and_generation_map"
                        ),
                        "prompt": pointer(PROMPTS, f"/images/{index}/edits/{n}/prompt", edit["prompt"]),
                        "references": [
                            reference(ref, "edit_target" if m == 0 else "identity_only", media)
                            for m, ref in enumerate(edit.get("refs", [edit["reference"]]))
                        ],
                        "reference_list_status": "recorded" if "refs" in edit else (
                            "only_edit_target_recorded; no_additional_references_claimed"
                        ),
                        "generation_artifact": generations[key],
                        "result_sha256": asset["sha256"],
                    }
                    for n, edit in enumerate(edits)
                ],
                "current_result": {
                    "asset_id": asset["id"],
                    "sample_key": asset["sample_key"],
                    "public_path": asset["url"][2:],
                    "sha256": asset["sha256"],
                    "generation_artifact": generations[key],
                    "effective_actual_prompt": pointer(PROMPTS, current_pointer, current_prompt),
                    "model_version": None,
                    "seed": None,
                    "missing_metadata": "model version and seed were not recorded; no exact rerun claim",
                },
                "review": {
                    "assistant": {
                        "status": "recorded_inspection_with_limitations",
                        "record": REVIEW + "#/shots/" + key,
                        "notes": review["shots"][key],
                    },
                    "creator_final_art_review": "pending",
                    "supplemental_pair_gate": GATE if key in GROUP else None,
                },
            }
        )
    return {
        "format": "taleprism-maker-trace",
        "version": 1,
        "scope": "current_12_chibi_narrative_artworks; maker-side only",
        "assembled_on": "2026-11-14",
        "source_archive_sha256": recipe["source_archive"]["sha256"],
        "source_sha256": digest(source),
        "tool_recorded": requests["tool"],
        "historical_requests_changed": False,
        "image_bytes_changed": False,
        "creator_final_art_review": "pending",
        "layers": {
            "actual_requests": {"path": PROMPTS, "role": "recorded per-image generation and edit requests"},
            "retrospective_recipe": {"path": RECIPE, "role": "v0.2 maker reconstruction; not the original image-generation prompt"},
            "generic_templates": {"path": "prompts/manifest.json", "role": "reusable workflow; not evidence any current image used these templates"},
        },
        "dependencies": {
            path: digest((root / path).read_bytes())
            for path in [PROMPTS, GENERATIONS, REVISIONS, RECIPE, REVIEW]
        },
        "records": records,
    }


def provenance_assets(files, public, root=ROOT):
    """Validate the maker record against immutable input before carrying it into export."""
    root = Path(root)
    trace = json.loads((root / TRACE).read_bytes())
    if trace != make_trace(files, public, root):
        raise ValueError("制作追溯与历史请求／固定结果不符；请实际复核，勿只改哈希。")
    gate = json.loads((root / GATE).read_bytes())
    if (
        gate.get("format") != "taleprism-paired-shot-continuity"
        or gate.get("version") != 1
        or gate.get("decision") != "needs_revision"
        or gate.get("reviewer") != "assistant"
        or gate.get("creator_final_art_review") != "pending"
        or gate.get("image_bytes_changed") is not False
        or gate.get("canonical_state_status") != "proposed_for_future_correction_not_applied"
        or gate.get("shot_order") != GROUP
        or gate.get("source_sha256") != trace["source_sha256"]
        or gate.get("trace_sha256") != digest((root / TRACE).read_bytes())
    ):
        raise ValueError("成对连续性记录失效；当前旗色差异不能标成已修复／已通过。")
    by_key = {r["key"]: r for r in trace["records"]}
    if gate.get("image_sha256") != {k: by_key[k]["current_result"]["sha256"] for k in GROUP}:
        raise ValueError("成对连续性记录不是当前三张图片。")
    if (
        [s.get("key") for s in gate.get("shots", [])] != GROUP
        or not all(s.get("image_inspected") is True for s in gate["shots"])
        or not any(p.get("decision") == "needs_revision" for p in gate.get("pair_checks", []))
    ):
        raise ValueError("成对检查必须保留实际看图与未解决问题，不能只改总状态。")
    for evidence in gate["source_evidence"]:
        if evidence != anchor(files["storygal-source/original.txt"], evidence["quote"]):
            raise ValueError("成对连续性原文引文或字节位置失效。")
    # Mirror source-relative paths so pointers remain usable in a standalone reader ZIP.
    # The legacy storygal-source/narrative-v1 request is also preserved unchanged.
    paths = [TRACE, GATE, GUIDE, WORKSHEET, PROMPTS, GENERATIONS, REVISIONS, RECIPE, REVIEW]
    paths += [
        "prompts/" + name
        for name in [
            "manifest.json", "README.md", "RULES.md", "01-source.md", "02-character.md",
            "03-shot-plan.md", "04-scene.md", "05-first-image.md", "06-continuation.md",
            "07-review.md", "08-repair.md",
        ]
    ]
    return {"storygal-source/" + path: (root / path).read_bytes() for path in paths}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    _, _, files, public, _, _ = preflight(args.source, ROOT / RECIPE, ROOT / REVIEW)
    provenance_assets(files, public)
    print("12 current assets traced; paired-shot gate needs_revision; creator review pending.")
