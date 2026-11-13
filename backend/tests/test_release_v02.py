"""Public packages use reviewed inputs and keep the two examples distinct."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inventory(root, names):
    (root / "tools").mkdir(parents=True, exist_ok=True)
    (root / "tools/public-source.json").write_text(json.dumps(sorted(names)))


def test_public_source_ignores_unlisted_files_without_git(tmp_path):
    module = tool("release_files")
    inventory(tmp_path, ["README.md"])
    (tmp_path / "README.md").write_text("public")
    (tmp_path / "tools/session.json").write_text("private working session")
    (tmp_path / "tools/.env").write_text("synthetic test only")
    assert [name for name, _ in module.source_files(tmp_path)] == ["README.md"]


@pytest.mark.parametrize(
    "name",
    [
        "../README.md",
        "/README.md",
        "tools/.env",
        "tools/.env.private",
        "data/private.json",
        "tools/node_modules/a.js",
        "tools/archive.zip",
        "tools/../README.md",
    ],
)
def test_public_source_rejects_disallowed_inventory_paths(tmp_path, name):
    inventory(tmp_path, [name])
    with pytest.raises(ValueError, match="Disallowed"):
        tool("release_files").source_files(tmp_path)


@pytest.mark.parametrize("mode", ["missing", "file_link", "parent_link", "duplicate"])
def test_public_source_rejects_missing_linked_or_duplicate_entries(tmp_path, mode):
    module = tool("release_files")
    if mode == "parent_link":
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        (outside / "a.py").write_text("private")
        (tmp_path / "backend").symlink_to(outside, target_is_directory=True)
        inventory(tmp_path, ["backend/a.py"])
    else:
        inventory(tmp_path, ["README.md"] * (2 if mode == "duplicate" else 1))
        if mode == "file_link":
            (tmp_path / "secret").write_text("private")
            (tmp_path / "README.md").symlink_to(tmp_path / "secret")
    with pytest.raises(ValueError):
        module.source_files(tmp_path)


def test_inventory_refresh_only_uses_git_index(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "README.md").write_text("public")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/private.json").write_text("untracked")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    assert tool("release_files").tracked_inventory(tmp_path) == [
        "README.md",
        "tools/public-source.json",
    ]


def artifacts(example):
    return [
        {
            "file": f"taleprism-v0.2.0-{example}-{kind}.zip",
            "sha256": char * 64,
            "example": example,
            "kind": kind,
        }
        for kind, char in [("project", "a"), ("reader", "b")]
    ]


@pytest.fixture
def catalog(tmp_path):
    folder = tmp_path / "samples/content-packs"
    folder.mkdir(parents=True)
    existing = [
        {"id": "chibi", "reader": {"file": "old-chibi.zip"}},
        {"id": "last-light", "reader": {"file": "old-tutorial.zip"}},
    ]
    file = folder / "catalog.json"
    file.write_text(json.dumps(existing))
    return tmp_path, file, existing


def test_catalog_pins_each_example_by_explicit_id_not_zip_order(catalog):
    root, path, _ = catalog
    incoming = list(reversed(artifacts("chibi") + artifacts("last-light")))
    tool("update_release_catalog").pin_release({"version": "0.2.0", "artifacts": incoming}, root)
    for entry in json.loads(path.read_text()):
        assert entry["file"] == f"taleprism-v0.2.0-{entry['id']}-project.zip"
        assert entry["reader"]["file"] == f"taleprism-v0.2.0-{entry['id']}-reader.zip"
        assert "/v0.2.0/" in entry["reader"]["url"]


def test_partial_catalog_update_preserves_other_example(catalog):
    root, path, existing = catalog
    tool("update_release_catalog").pin_release(
        {"version": "0.2.0", "artifacts": artifacts("last-light")}, root
    )
    assert json.loads(path.read_text())[0] == existing[0]


@pytest.mark.parametrize("bad", ["missing", "duplicate", "mixed_name", "bad_hash"])
def test_bad_catalog_manifest_does_not_partially_write(catalog, bad):
    root, path, _ = catalog
    incoming = artifacts("chibi")
    if bad == "missing":
        incoming.pop()
    elif bad == "duplicate":
        incoming.append(incoming[0])
    elif bad == "mixed_name":
        incoming[0]["file"] = "taleprism-v0.2.0-last-light-project.zip"
    else:
        incoming[0]["sha256"] = "invalid"
    before = path.read_bytes()
    with pytest.raises(ValueError):
        tool("update_release_catalog").pin_release(
            {"version": "0.2.0", "artifacts": artifacts("last-light") + incoming}, root
        )
    assert path.read_bytes() == before
