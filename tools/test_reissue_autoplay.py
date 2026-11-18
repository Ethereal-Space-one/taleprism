"""Runtime-only reissue integrity, exercised with disposable synthetic archives."""

import json
import tempfile
import unittest
from pathlib import Path

from reissue_autoplay import (
    CHANGED,
    OLD_GUIDE,
    RUNTIME,
    loadzip,
    packed,
    reissue,
    sha,
    summary,
)


class ReissueChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.rt = Path(self.tmp.name)
        for n in RUNTIME:
            (self.rt / n).write_text(
                "synthetic runtime fixture for package tests, not a shipping runtime: "
                + n
            )
        (self.rt / "runtime-checksums.json").write_text(
            json.dumps({n: sha((self.rt / n).read_bytes()) for n in RUNTIME})
        )
        self.baselines = []
        for title in ("Control A", "Control B"):
            source = title.encode()
            image = ("QA image " + title).encode()
            story = {
                "project": {
                    "id": title,
                    "sha256": sha(source),
                    "canonical_sha256": sha(source),
                },
                "config": {"title": title},
                "media": {"sample": {"url": "./media/image", "sha256": sha(image)}},
            }
            raw = json.dumps(story).encode()
            files = {
                "reader.json": raw,
                "index.html": b'<script type="application/json" id="taleprism-story">'
                + raw
                + b"</script>",
                "media/image": image,
                "storygal-source/original.txt": source,
                "storygal-source/source.utf8.txt": source,
                "README.txt": OLD_GUIDE.encode(),
                "open.command": b"#!/bin/sh\n",
                **{"assets/" + n: b"old player" for n in RUNTIME},
            }
            files["storygal-delivery.json"] = json.dumps(
                {"files": summary(files), "export_id": title, "versions": {}}
            ).encode()
            self.baselines.append(packed(files))

    def test_byte_identity_modes_inventory_repeatability(self):
        for baseline in self.baselines:
            prior, inv = loadzip(baseline)
            out, report = reissue(baseline, self.rt, sha(baseline))
            self.assertEqual((out, report), reissue(baseline, self.rt, sha(baseline)))
            new, final = loadzip(out)
            self.assertEqual(set(prior), set(new))
            self.assertEqual({n for n in new if new[n] != prior[n]}, CHANGED)
            self.assertEqual(report["reader_sha256"], sha(out))
            self.assertNotEqual(final["export_id"], inv["export_id"])
            self.assertEqual(
                final["runtime_reissue"]["prior_export_id"], inv["export_id"]
            )
            self.assertEqual(final["versions"], inv["versions"])
            self.assertEqual(new["index.html"], prior["index.html"])
            self.assertEqual(new["reader.json"], prior["reader.json"])
            import io
            import zipfile

            with zipfile.ZipFile(io.BytesIO(out)) as z:
                self.assertTrue(
                    all(
                        i.external_attr >> 16 & 0o111
                        for i in z.infolist()
                        if i.filename.endswith(".command")
                    )
                )

    def test_wrong_runtime_is_rejected(self):
        (self.rt / RUNTIME[0]).write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "digest"):
            reissue(self.baselines[0], self.rt, sha(self.baselines[0]))

    def test_corrupt_source_or_unsupported_baseline_is_rejected(self):
        files, _ = loadzip(self.baselines[0])
        files["storygal-source/original.txt"] += b" "
        tampered = packed(files)
        with self.assertRaisesRegex(ValueError, "inventory"):
            loadzip(tampered)
        with self.assertRaisesRegex(ValueError, "baseline"):
            reissue(tampered, self.rt, sha(self.baselines[0]))

    def test_missing_and_extra_runtime_assets_rejected(self):
        path = self.rt / "runtime-checksums.json"
        for hashes in [{}, {i: "x" for i in (*RUNTIME, "other")}]:
            path.write_text(json.dumps(hashes))
            with self.assertRaisesRegex(ValueError, "checksum inventory"):
                reissue(self.baselines[0], self.rt, sha(self.baselines[0]))

    def test_old_runtime_rejected(self):
        files, _ = loadzip(self.baselines[0])
        for n in RUNTIME:
            (self.rt / n).write_bytes(files["assets/" + n])
        (self.rt / "runtime-checksums.json").write_text(
            json.dumps({n: sha((self.rt / n).read_bytes()) for n in RUNTIME})
        )
        with self.assertRaisesRegex(ValueError, "previous build"):
            reissue(self.baselines[0], self.rt, sha(self.baselines[0]))


if __name__ == "__main__":
    unittest.main()
