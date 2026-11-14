import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from .llm import api_key
from .review import Review
from .speech import Speech
from .storage import Store
from .text import sha256
from .visual import Visual

REPO = Path(__file__).resolve().parents[3]
ENGINE = REPO / "engine" / "webgal-4.6.5"
BUNDLE = "assets/index-CC7KTie-.js"
BUNDLE_HASH = "356f7184c80af8da4dd782e25c5b3fb89f55f1e8b9e9e18be6f50035763dc6b6"
SIGNATURE = "function Na(e,t,r,n=!0){"


def encode_literal(text: str) -> str:
    return "SGTEXT_" + "".join(f"{ord(c):06x}" for c in text)


def copy_verified(source: Path, target: Path, expected: str):
    shutil.copy2(source, target)
    if sha256(target.read_bytes()) != expected:
        raise ValueError("素材在打包期间发生变化，请检查后重新导出。")


def assert_versions(db, pid, expected):
    for table, key in [
        ("review_states", "review_revision"),
        ("speech_states", "speech_revision"),
        ("visual_states", "visual_revision"),
        ("reader_states", "reader_revision"),
        ("production_states", "production_revision"),
    ]:
        if key not in expected:
            continue
        row = db.execute(f"SELECT revision FROM {table} WHERE project_id=?", (pid,)).fetchone()
        if (row[0] if row else 0) != expected[key]:
            raise ValueError("制作状态在导出期间发生变化，本次未发布。请重新导出。")


def export_project(
    store: Store,
    project_id: str,
    job_id: str,
    *,
    reader_revision: int | None = None,
    compatibility: dict | None = None,
) -> dict:
    checks = store.verify(project_id)
    metadata = store.get(project_id)
    review = Review(store)
    units, review_state = review.presentation(project_id)
    speech = Speech(store, review)
    speech_state, audio = speech.for_export(project_id, units)
    visual = Visual(store, review)
    visual_state, visual_events = visual.for_export(project_id, units)
    visual_events.sort(key=lambda e: e["after_unit_id"])
    if speech_state["review_revision"] != review_state["revision"]:
        raise ValueError("审校在导出期间发生变化，请重新导出。")
    selected_assets = {a["id"]: a for a in review_state["assets"] if a["status"] == "accepted"}
    used_assets = sorted({u.get("figure_asset_id") for u in units if u.get("figure_asset_id")})
    if not (ENGINE / "index.html").exists():
        raise ValueError("缺少 WebGAL 引擎，请先运行 tools/fetch_engine.sh。")
    source_js = (ENGINE / BUNDLE).read_bytes()
    if sha256(source_js) != BUNDLE_HASH:
        raise ValueError("引擎文件与固定版本不一致，请重新下载引擎。")
    parent = store.project_dir(project_id) / "exports"
    parent.mkdir(exist_ok=True)
    staging = parent / (job_id + ".partial")
    target = parent / job_id
    archive = parent / (job_id + ".zip")
    archive_staging = parent / (job_id + ".zip.partial")
    versions = {
        "review_revision": review_state["revision"],
        "speech_revision": speech_state["revision"],
        "visual_revision": visual_state["revision"],
    }
    if reader_revision is not None:
        versions["reader_revision"] = reader_revision
    try:
        with store.db() as db:
            assert_versions(db, project_id, versions)
        staging.mkdir()
        for entry in ["assets", "icons"]:
            shutil.copytree(ENGINE / entry, staging / entry)
        for entry in [
            "index.html",
            "manifest.json",
            "webgal-engine.json",
            "webgal-serviceworker.js",
        ]:
            shutil.copy2(ENGINE / entry, staging / entry)
        # Keep the stock title resources and animation files, omit demo story, voice and characters.
        for entry in ["template", "background", "bgm", "animation"]:
            shutil.copytree(ENGINE / "game" / entry, staging / "game" / entry)
        for entry in ["scene", "figure", "vocal"]:
            (staging / "game" / entry).mkdir(parents=True, exist_ok=True)
        config = (ENGINE / "game/config.txt").read_text()
        config = config.replace("欢迎使用WebGAL！", "Taleprism · 本地试读")
        config = config.replace("0f87dstRg", project_id.replace("-", ""))
        config = config.replace("Enable_flowchart:true", "Enable_flowchart:false")
        config = config.replace("Enable_Appreciation:true", "Enable_Appreciation:false")
        (staging / "game/config.txt").write_text(config, encoding="utf-8")
        (staging / "game/userStyleSheet.css").write_text(
            "/* Original source whitespace is retained in plain text nodes. */\n"
            "#textBoxMain>div:not(#miniAvatar){white-space:pre-wrap!important;tab-size:4;}\n",
            encoding="utf-8",
        )
        for asset_id in used_assets:
            copy_verified(
                review.asset_path(project_id, asset_id),
                staging / "game/figure" / (asset_id + ".png"),
                selected_assets[asset_id]["sha256"],
            )
        script_lines = []
        for event in visual_events:
            item = next(i for i in visual_state["items"] if i["id"] == event["item_id"])
            copy_verified(
                visual.path(project_id, event["asset_id"]),
                staging / "game/background" / (event["asset_id"] + ".png"),
                item["asset"]["sha256"],
            )
            if event["kind"] == "diagram":
                (staging / "storygal-diagrams").mkdir(exist_ok=True)
                copy_verified(
                    visual.path(project_id, event["asset_id"], True),
                    staging / "storygal-diagrams" / (event["asset_id"] + ".svg"),
                    item["asset"]["svg_sha256"],
                )
        for take in {a["id"]: a for a in audio.values()}.values():
            copy_verified(
                speech.path(project_id, take),
                staging / "game/vocal" / (take["id"] + ".wav"),
                take["sha256"],
            )
        current_figure = None
        current_background = None
        for unit in units:
            figure = unit.get("figure_asset_id")
            if figure != current_figure:
                script_lines.append(f"changeFigure:{figure + '.png' if figure else 'none'} -next;")
                current_figure = figure
            args = (
                "-speaker=" + encode_literal(unit["speaker_name"])
                if unit.get("speaker_name")
                else "-clear"
            )
            vocal = f" -vocal={unit['vocal_id']}.wav" if unit.get("vocal_id") else ""
            script_lines.append(f"say:{encode_literal(unit['text'])} {args}{vocal};")
            for event in [e for e in visual_events if e["after_unit_id"] == unit["id"]]:
                path = event["asset_id"] + ".png"
                if event["kind"] in {"illustration", "diagram"}:
                    script_lines.extend(
                        [
                            "setTextbox:hide -next;",
                            "changeFigure:none -next;",
                            f"changeBg:{path} -duration=0 -exitDuration=0;",
                            f"changeBg:{current_background or 'none'} -duration=0 -exitDuration=0 -next;",
                            "setTextbox:on -next;",
                            f"changeFigure:{current_figure + '.png' if current_figure else 'none'} -next;",
                        ]
                    )
        text = "\n".join(script_lines) + "\nend;\n"
        (staging / "game/scene/start.txt").write_text(text, encoding="utf-8")
        patch = (REPO / "tools/webgal-verify/literal-patch.js").read_text()
        js = source_js.decode("utf-8")
        if js.count(SIGNATURE) != 1:
            raise ValueError("正文扩展与引擎不匹配。")
        (staging / BUNDLE).write_text(js.replace(SIGNATURE, SIGNATURE + patch, 1), encoding="utf-8")
        source_dir = staging / "storygal-source"
        source_dir.mkdir()
        shutil.copy2(REPO / "tools/webgal-verify/literal-patch.js", source_dir)
        shutil.copy2(REPO / "tools/webgal-verify/verify.cjs", source_dir)
        license_path = REPO / "engine/LICENSE-MPL-2.0.txt"
        if not license_path.exists():
            raise ValueError("缺少引擎许可证 engine/LICENSE-MPL-2.0.txt。")
        shutil.copy2(license_path, staging / "LICENSE-WebGAL-MPL-2.0.txt")
        (staging / "NOTICE.txt").write_text(
            "WebGAL 4.6.5, OpenWebGAL contributors, MPL-2.0.\n"
            "Upstream source: https://github.com/OpenWebGAL/WebGAL/tree/4.6.5\n"
            "Modified file: " + BUNDLE + "\n"
            "Modification: literal text extension; source fragment: storygal-source/literal-patch.js\n"
            "The fragment is inserted directly after function Na(e,t,r,n=!0){ in the upstream bundle.\n"
            "Exported scenes require this included engine; stock engines do not decode SGTEXT_.\n",
            encoding="utf-8",
        )
        shutil.copy2(store.project_dir(project_id) / "original.txt", source_dir / "original.txt")
        shutil.copy2(
            store.project_dir(project_id) / "source.utf8.txt", source_dir / "source.utf8.txt"
        )
        manifest = {
            "schema_version": 1,
            "engine": "4.6.5",
            "literal_extension": 1,
            "project": metadata,
            "checks": checks,
            "units": units,
            "spans": store.parts(project_id, "spans"),
            "review": review_state,
            "figure_assets": [selected_assets[a] for a in used_assets],
            "speech": speech_state,
            "visual": visual_state,
            "visual_events": visual_events,
        }
        if compatibility is not None:
            manifest["webgal_compatibility"] = compatibility
        manifest_path = staging / "storygal-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        try:
            proc = subprocess.run(
                ["node", str(REPO / "tools/webgal-verify/verify.cjs"), str(staging)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError("官方解析器无法运行，请检查 Node 和校验工具依赖。") from error
        if proc.returncode:
            raise ValueError("官方解析器回读失败：" + proc.stderr[:500])
        checks["parser"] = json.loads(proc.stdout)
        checks["render"] = "not_run"  # Browser verification is a separate, explicit check.
        manifest["checks"] = checks
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (staging / "README.txt").write_text(
            "Taleprism 本地试读工程\n\n请通过本地 HTTP 服务打开 index.html（浏览器不支持直接双击播放）。\n"
            "可在本目录运行：python3 -m http.server 8080 --bind 127.0.0.1\n"
            "然后打开 http://127.0.0.1:8080\n\n"
            "正文只隐藏换行、初始 BOM 和行首尾空白。原文件、偏移、来源及校验记录见清单。\n"
            "本工程附带 SGTEXT_ 正文扩展，需使用随包提供的 WebGAL 引擎。\n"
            "自动导出包含字节和解析校验；逐框播放复核需单独执行。\n"
            "解压后先运行 python3 verify_package.py 检查逐文件哈希，再开启本地服务。\n"
            "图页出现后点击继续；声音可在引擎选项中调整。\n"
            "复核原文、角色归属、声音和图页，读到末尾后在制作台记录本版本复核。\n"
            "仅本地测试的作品请先核实分享范围；原文权利与素材来源见 RIGHTS.txt。\n"
            "移动完整目录即可播放；重新制作需要原制作台的完整 data 目录。\n",
            encoding="utf-8",
        )
        secret = api_key().encode()
        if secret and any(
            secret in path.read_bytes() for path in staging.rglob("*") if path.is_file()
        ):
            raise ValueError("导出内容包含本机模型密钥，已停止打包。请检查原文与素材。")
        checks["no_service_keys"] = True
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (staging / "RIGHTS.txt").write_text(
            "项目权利状态：" + metadata["rights_status"] + "\n"
            "原文文件：" + metadata["filename"] + "\n"
            "原文 SHA-256：" + metadata["sha256"] + "\n\n"
            "原文和素材的使用范围须由制作人核实；工程导出不授予额外权利。\n"
            "每项图像及图解的来源／许可、语音后端与参数见 storygal-manifest.json。\n"
            "WebGAL 引擎许可证和修改说明见 LICENSE-WebGAL-MPL-2.0.txt 与 NOTICE.txt。\n"
            "哈希清单用于检查文件完整性，不是来源真实性或权利状态的认证。\n",
            encoding="utf-8",
        )
        shutil.copy2(REPO / "tools/verify_package.py", staging / "verify_package.py")
        inventory = {
            "schema_version": 1,
            "export_id": job_id,
            "versions": versions,
            "files": {
                p.relative_to(staging).as_posix(): {
                    "bytes": p.stat().st_size,
                    "sha256": sha256(p.read_bytes()),
                }
                for p in sorted(staging.rglob("*"))
                if p.is_file()
            },
        }
        (staging / "storygal-delivery.json").write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with zipfile.ZipFile(archive_staging, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(staging))
        with zipfile.ZipFile(archive_staging) as bundle:
            if bundle.testzip() is not None or set(bundle.namelist()) != set(inventory["files"]) | {
                "storygal-delivery.json"
            }:
                raise ValueError("工程压缩包校验失败，请检查磁盘空间并重试。")
        archive_hash = sha256(archive_staging.read_bytes())
        store.verify(project_id)
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            assert_versions(db, project_id, versions)
            archive_staging.rename(archive)
            staging.rename(target)
        return {
            "export_id": job_id,
            **versions,
            "archive_sha256": archive_hash,
            "file_count": len(inventory["files"]),
            "checks": checks,
            "play_url": f"/play/{project_id}/{job_id}/index.html",
            "download_url": f"/api/projects/{project_id}/exports/{job_id}/download",
            **({"webgal_compatibility": compatibility} if compatibility is not None else {}),
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(target, ignore_errors=True)
        archive_staging.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
        raise
