"""Small, non-executable stand-in for package/integrity tests (not browser tests)."""

import hashlib
import json
from pathlib import Path


def fake_reader_build(repo: Path):
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "LICENSE").write_bytes((Path(__file__).resolve().parents[2] / "LICENSE").read_bytes())
    portable = repo / "frontend/dist/reader"
    portable.mkdir(parents=True)
    (portable / "reader.js").write_text("/* isolated fixture: no executable runtime */")
    (portable / "reader.css").write_text("/* isolated fixture */")
    checks = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in portable.iterdir()}
    (portable / "runtime-checksums.json").write_text(json.dumps(checks))
    for name in [
        "react/LICENSE",
        "react-dom/LICENSE",
        "scheduler/LICENSE",
        "opencc-js/LICENSE",
        "opencc-js/THIRD_PARTY_LICENSES.md",
        "opencc-js/LICENSES/Apache-2.0.txt",
    ]:
        file = repo / "frontend/node_modules" / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("Test fixture license marker; not distributed.")
