"""Application release metadata stays separate from reviewed content and storage."""

import json
import sys
import tomllib
from pathlib import Path

import pytest

from storygal.app import create_app

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))


def test_application_version_matches_frontend_locks_and_health(tmp_path):
    version = tomllib.loads((ROOT / "backend/pyproject.toml").read_text())["project"]["version"]
    assert version == "0.3.1"
    lock = tomllib.loads((ROOT / "backend/uv.lock").read_text())
    assert next(p for p in lock["package"] if p["name"] == "storygal")["version"] == version
    for folder in ("frontend", "tools/webgal-verify"):
        package = json.loads((ROOT / folder / "package.json").read_text())
        locked = json.loads((ROOT / folder / "package-lock.json").read_text())
        assert package["version"] == locked["version"] == locked["packages"][""]["version"] == version
    app = create_app(tmp_path)
    assert app.version == version
    from fastapi.testclient import TestClient

    assert TestClient(app).get("/api/health").json()["version"] == version
    prompt = json.loads((ROOT / "backend/src/storygal/prompt_library.json").read_text())
    assert prompt["version"] == "0.2.0"


@pytest.mark.parametrize("recipe_version,accepted", [("0.2.0", True), ("0.3.0", False)])
def test_reviewed_chibi_recipe_version_is_independent_of_application(
    monkeypatch, tmp_path, recipe_version, accepted
):
    import build_chibi_demo as builder

    monkeypatch.setattr(builder, "VERSION", "0.3.1")
    monkeypatch.setattr(
        builder, "preflight", lambda *_: ({"release_version": recipe_version}, {}, {}, {}, b"", b"")
    )

    # This unit stubs the frozen source package; maker validation has its own tests.
    monkeypatch.setattr(builder, "provenance_assets", lambda *_: {})

    def reached(*_args):
        raise RuntimeError("reviewed reconstruction reached")

    monkeypatch.setattr(builder, "rebuild", reached)
    if accepted:
        with pytest.raises(RuntimeError, match="reviewed reconstruction reached"):
            builder.build(tmp_path / "source.zip", tmp_path / "new-output")
    else:
        with pytest.raises(ValueError, match="已检查内容版本"):
            builder.build(tmp_path / "source.zip", tmp_path / "new-output")


@pytest.mark.parametrize("legacy", ["v0.1.0", "v0.2.0", "v0.2.0-chibi", "chibi-demo"])
def test_chibi_builder_never_overwrites_legacy_release(monkeypatch, tmp_path, legacy):
    import build_chibi_demo as builder

    monkeypatch.setattr(builder, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="不能覆盖历史发布产物"):
        builder.build(tmp_path / "missing.zip", tmp_path / ".release" / legacy / "nested")
