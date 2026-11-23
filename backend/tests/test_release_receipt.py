"""An archive inventory or a receipt from other bytes must never close the release gate."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from finalize_release import require_editions


def test_only_full_current_release_receipt_is_acceptable(tmp_path):
    files = {f"a{i}.zip": f"{i:064x}" for i in range(8)}
    commit = "a" * 40
    report = {
        "schema": 1,
        "static_only": False,
        "mode": "release",
        "source_commit": commit,
        "zip_sha256": files,
        "cold_exports": ["chibi", "last-light"],
        "browser_version": "Chromium",
        "results": [{"passed": True}],
    }
    with pytest.raises(ValueError, match="full edition gate"):
        require_editions(tmp_path, commit, files)
    for key, value in [
        ("mode", "pages-live"),
        ("mode", "frozen-books"),
        ("static_only", True),
        ("source_commit", "0" * 40),
        ("zip_sha256", files | {"a1.zip": "a" * 64}),
        ("cold_exports", ["chibi"]),
        ("browser_version", ""),
        ("results", []),
    ]:
        (tmp_path / "edition-acceptance.json").write_text(json.dumps(report | {key: value}))
        with pytest.raises(ValueError, match="does not match"):
            require_editions(tmp_path, commit, files)
    (tmp_path / "edition-acceptance.json").write_text(json.dumps(report))
    require_editions(tmp_path, commit, files)
