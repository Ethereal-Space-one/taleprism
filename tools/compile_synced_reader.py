"""Compile a synchronized reader from a verified editable copy, in a fresh local store.

The original editable and earlier reader ZIPs are read, never mutated. Reuses the
current workbench's actual export path; no old runtime/JS is copied forward.
"""

import argparse
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

from reissue_reader import digest, reissue


def compile_copy(editable, baseline, prior_sha):
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory(prefix="taleprism-edition-sync-") as d:
        os.environ["STORYGAL_DATA_DIR"] = str(Path(d) / "initial")
        from storygal.app import create_app

        with TestClient(create_app(Path(d) / "edition")) as c:
            restore = c.post(
                "/api/project-bundles",
                files={"file": ("editable.zip", editable, "application/zip")},
            )
            if restore.status_code != 201:
                raise ValueError(
                    "The candidate editable package failed restore: "
                    + restore.text[:400]
                )
            pid = restore.json()["id"]
            base = f"/api/projects/{pid}"
            working = c.get(base + "/reader/soundscapes").json()
            chosen = [x for x in working["takes"] if x["status"] == "accepted"]
            if not chosen:
                raise ValueError("No accepted soundscape in this handoff")
            req = c.post(base + "/reader/exports")
            if req.status_code != 202:
                raise ValueError("Could not export the restored project")
            job = c.get(base + "/jobs").json()[0]
            if job["state"] != "completed":
                raise ValueError(job.get("error", "Failed to compile"))
            raw = c.get(job["result"]["download_url"]).content
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                story = json.loads(z.read("reader.json"))
                if [
                    b["byte_start"] for b in story["blocks"] if b.get("soundscape")
                ] != sorted(x["byte_start"] for x in chosen):
                    raise ValueError(
                        "Audible paragraph set differs from accepted choices"
                    )
            result, report = reissue(baseline, raw, prior_sha)
            report.update(
                editable_sha256=digest(editable),
                new_reader=digest(result),
                restore_issues=restore.json().get("restore_issues", []),
            )
            return result, report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--editable", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--baseline-sha256", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    raw, r = compile_copy(
        a.editable.read_bytes(), a.baseline.read_bytes(), a.baseline_sha256
    )
    with a.output.open("xb") as f:
        f.write(raw)
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
