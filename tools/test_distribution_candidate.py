"""Four-download contract: synthetic fixtures exercise the wrapper, not the books."""

import hashlib
import io
import json
import posixpath
import re
import stat
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urldefrag

import build_distribution_candidate as candidate


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def zipped(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        for name, raw in entries:
            z.writestr(name, raw)
    return output.getvalue()


def synthetic_reader():
    files = {
        "index.html": b"<html/>",
        "reader.json": b"{}",
        "RIGHTS.txt": b"fixture",
        "licenses/Taleprism-MIT.txt": b"test",
        "media/sample.png": b"sample",
        "打开阅读器.command": b"test only",
    }
    inventory = {n: {"bytes": len(b), "sha256": sha(b)} for n, b in files.items()}
    files["storygal-delivery.json"] = json.dumps(
        {"schema_version": 1, "files": inventory}
    ).encode()
    return files


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / "inputs"
        self.src.mkdir()

    def test_first_work_walkthrough_links_exist_in_the_portable_starter(self):
        # A repo-relative link can work online but strand a first-time author
        # who extracted only the starter. Check the actual included entries.
        files = candidate.starter_entries()
        for page in (
            "taleprism/prompts/START-HERE.md",
            "taleprism/examples/last-light/README.md",
            "taleprism/examples/last-light/README.en.md",
        ):
            for link in re.findall(r"\]\(([^)]+)\)", files[page].decode()):
                path, _ = urldefrag(link)
                if not path or path.startswith(("https://", "http://")):
                    continue
                target = posixpath.normpath(
                    posixpath.join(posixpath.dirname(page), path)
                )
                with self.subTest(page=page, target=target):
                    self.assertIn(target, files.keys())

    def test_reader_exact_and_project_unchanged(self):
        files = synthetic_reader()
        reader = zipped(files.items())
        project = zipped([("project.json", b'{"fixture":1}')])
        new = candidate.work_files("chibi", reader, project)
        self.assertEqual(
            {n[7:]: b for n, b in new.items() if n.startswith("Reader/")}, files
        )
        self.assertEqual(
            set(new) - {"Reader/" + n for n in files}, {"Project.zip", "README.md"}
        )
        self.assertEqual(new["Project.zip"], project)
        for text in [
            "赤壁",
            "Chibi",
            "Reader/index.html",
            "导入可编辑工程",
            "Project.zip",
        ]:
            self.assertIn(text, new["README.md"].decode())
        a, b = self.root / "a.zip", self.root / "b.zip"
        candidate.write_zip(a, new)
        candidate.write_zip(b, dict(reversed(new.items())))
        self.assertEqual(a.read_bytes(), b.read_bytes())
        with zipfile.ZipFile(a) as z:
            self.assertEqual(z.namelist(), sorted(new))
            self.assertEqual(
                z.getinfo("Reader/打开阅读器.command").external_attr >> 16 & 0o777,
                0o755,
            )
            self.assertEqual(
                z.getinfo("Reader/index.html").external_attr >> 16 & 0o777, 0o644
            )
            self.assertEqual(z.getinfo("Project.zip").date_time, (1980, 1, 1, 0, 0, 0))
            for n, data in new.items():
                self.assertEqual(z.read(n), data)

    def test_reopened_work_zip_is_checked_against_reference_not_its_own_inventory(self):
        files = synthetic_reader()
        reader = zipped(files.items())
        project = zipped([("project.json", b"editable")])
        expected = candidate.work_files("chibi", reader, project)
        for fault in (
            "valid",
            "different_project",
            "extra",
            "missing",
            "changed_image",
            "wrong_guide",
        ):
            with self.subTest(fault=fault):
                wrapped = expected.copy()
                if fault == "different_project":
                    wrapped["Project.zip"] = zipped([("project.json", b"another book")])
                elif fault == "extra":
                    wrapped["private-notes.txt"] = b"must not travel"
                elif fault == "missing":
                    del wrapped["Reader/RIGHTS.txt"]
                elif fault == "changed_image":
                    wrapped["Reader/media/sample.png"] = b"change"
                elif fault == "wrong_guide":
                    wrapped["README.md"] = candidate.work_readme("last-light")
                path = self.root / f"{fault}.zip"
                candidate.write_zip(path, wrapped)
                if fault == "valid":
                    candidate.verify_work_zip(path, "chibi", reader, sha(project))
                else:
                    with self.assertRaises(ValueError):
                        candidate.verify_work_zip(path, "chibi", reader, sha(project))

    def test_reject_unsafe_and_colliding_reader_members(self):
        examples = [
            ["../outside"],
            ["/root"],
            ["a//b"],
            ["a/./b"],
            [r"a\b"],
            ["C:/drive"],
            ["bad."],
            ["bad "],
            ["file:stream"],
            ["ok", "ok"],
            ["media/A", "media/a"],
            ["É", "E\u0301"],
            ["f", "f/child"],
        ]
        for names in examples:
            with self.subTest(names=names), warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with self.assertRaises(ValueError):
                    candidate.safe_files(zipped((n, b"x") for n in names))
        for typ in [stat.S_IFLNK, stat.S_IFIFO]:
            info = zipfile.ZipInfo("file")
            info.create_system = 3
            info.external_attr = (typ | 0o644) << 16
            with self.assertRaises(ValueError):
                candidate.safe_files(zipped([(info, b"outside")]))

    def test_windows_reserved_members_rejected_on_any_platform(self):
        for name in [
            "NUL.txt",
            "cloud/cOn/image.png",
            "media/com¹.jpg",
            "LPT9",
            "PRN .txt",
        ]:
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(ValueError, "Unsafe member"),
            ):
                candidate.safe_files(zipped([(name, b"x")]))
        names = ["media/concept.png", "COM10.txt", "data/辅助.md"]
        files = dict.fromkeys(names, b"safe")
        self.assertEqual(candidate.safe_files(zipped(files.items())), files)

    def test_windows_reserved_uses_ntpath_when_pathlib_method_is_absent(self):
        with (
            patch.object(
                candidate,
                "ntpath",
                SimpleNamespace(isreserved=lambda p: p == "NUL.txt"),
            ),
            patch.object(candidate, "PureWindowsPath", return_value=object()) as legacy,
        ):
            with self.assertRaisesRegex(ValueError, "Unsafe member"):
                candidate.safe_files(zipped([("NUL.txt", b"x")]))
            self.assertEqual(
                candidate.safe_files(zipped([("index.html", b"x")])),
                {"index.html": b"x"},
            )
            legacy.assert_not_called()

    def test_windows_reserved_falls_back_without_ntpath_api(self):
        accepted = SimpleNamespace(is_reserved=lambda: False)
        rejected = SimpleNamespace(is_reserved=lambda: True)
        with (
            patch.object(candidate, "ntpath", SimpleNamespace()),
            patch.object(
                candidate, "PureWindowsPath", side_effect=[rejected, accepted]
            ) as legacy,
        ):
            with self.assertRaisesRegex(ValueError, "Unsafe member"):
                candidate.safe_files(zipped([("NUL.txt", b"x")]))
            self.assertEqual(
                candidate.safe_files(zipped([("index.html", b"x")])),
                {"index.html": b"x"},
            )
            self.assertEqual(legacy.call_count, 2)

    def test_broken_reader_inventory(self):
        files = synthetic_reader()
        files["media/sample.png"] += b"X"
        with self.assertRaises(ValueError):
            candidate.work_files("last-light", zipped(files.items()), b"project")

    def test_starter_cannot_drop_template_and_source_cannot_self_attest_missing_file(
        self,
    ):
        starter = self.root / "starter.zip"
        candidate.write_zip(starter, {"README.md": b"start"})
        with (
            zipfile.ZipFile(starter) as archive,
            self.assertRaisesRegex(ValueError, "missing files"),
        ):
            candidate.verify_members(
                archive,
                {"README.md": sha(b"start"), "prompts/01-source.md": sha(b"template")},
                (".command",),
            )

        source = self.root / "source.zip"
        sample = self.root / "start.sh"
        sample.write_bytes(b"onboarding")
        manifest = {"format": "storygal-source", "version": 1, "files": {}}
        candidate.write_zip(
            source, {"taleprism/SOURCE-MANIFEST.json": json.dumps(manifest).encode()}
        )
        with self.assertRaisesRegex(ValueError, "reviewed source inventory"):
            candidate.verify_source_zip(source, [("start.sh", sample)])

    def test_pins_ignore_inputs_own_sidecars_and_other_tags(self):
        n = "taleprism-v0.9.2-chibi-project.zip"
        raw = b"replacement"
        (self.src / n).write_bytes(raw)
        (self.src / "SHA256SUMS").write_text(sha(raw) + "  " + n + "\n")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            candidate.checked_input(self.src, "chibi", "project")
        (self.src / n).rename(self.src / n.replace("0.9.2", "0.9.1"))
        with self.assertRaisesRegex(ValueError, "Missing"):
            candidate.checked_input(self.src, "chibi", "project")

    def test_existing_output_never_overwritten(self):
        (self.src / "keep").write_bytes(b"existing release")
        with self.assertRaisesRegex(ValueError, "new output"):
            candidate.build(self.src, self.src)
        self.assertEqual((self.src / "keep").read_bytes(), b"existing release")

    def test_four_downloads_checksums_and_atomic_failure(self):
        reader = zipped(synthetic_reader().items())
        pins = {}
        for slug in candidate.PINS:
            project = zipped([("project.json", slug.encode())])
            pins[slug] = {}
            for kind, raw in [("project", project), ("reader", reader)]:
                pins[slug][kind] = sha(raw)
                (self.src / f"taleprism-v0.9.2-{slug}-{kind}.zip").write_bytes(raw)
        commit = "a" * 40

        sample = self.root / "README.md"
        sample.write_bytes(b"source")
        selected = [("README.md", sample)]

        def source_stub(path):
            doc = {
                "format": "storygal-source",
                "version": 1,
                "files": {"README.md": sha(b"source")},
            }
            candidate.write_zip(
                path,
                {
                    "taleprism/README.md": b"source",
                    "taleprism/SOURCE-MANIFEST.json": json.dumps(doc).encode(),
                },
            )
            path.with_suffix(".json").write_text("{}")

        with (
            patch.object(candidate, "PINS", pins),
            patch.object(candidate, "source_commit", return_value=commit),
            patch.object(
                candidate,
                "starter_entries",
                return_value={"taleprism/prompts/START-HERE.md": b"start"},
            ),
            patch.object(candidate, "package_source", source_stub),
            patch.object(candidate, "source_files", return_value=selected),
        ):
            out = candidate.build(self.src, self.root / "one")
            two = candidate.build(self.src, self.root / "two")
            wanted = {
                candidate.STARTER,
                candidate.SOURCE,
                *(candidate.work_name(s) for s in pins),
            }
            listing = {p.name for p in out.iterdir()}
            self.assertEqual(listing, wanted | {candidate.MANIFEST, candidate.SUMS})
            self.assertTrue(
                all((out / n).read_bytes() == (two / n).read_bytes() for n in listing)
            )
            sums = dict(
                line.split("  ")[::-1]
                for line in (out / candidate.SUMS).read_text().splitlines()
            )
            self.assertEqual(
                sums,
                {n: candidate.hash_file(out / n) for n in listing - {candidate.SUMS}},
            )
            doc = json.loads((out / candidate.MANIFEST).read_bytes())
            self.assertEqual(doc["commit"], commit)
            self.assertEqual({a["file"] for a in doc["artifacts"]}, wanted)
            for a in doc["artifacts"]:
                self.assertEqual(
                    (a["bytes"], a["sha256"]),
                    ((out / a["file"]).stat().st_size, sums[a["file"]]),
                )
            for slug, kinds in pins.items():
                self.assertEqual(
                    {
                        k: v["sha256"]
                        for k, v in doc["work_inputs"]["works"][slug].items()
                    },
                    kinds,
                )
            self.assertEqual(
                {h["id"] for h in doc["historical_reader_only"]},
                {"the-door-left-open", "the-margin"},
            )
            with zipfile.ZipFile(out / candidate.STARTER) as z:
                self.assertIn(
                    "prompts/START-HERE.md", z.read("taleprism/README.md").decode()
                )
                self.assertIn("taleprism/docs/DOWNLOADS.md", z.namelist())
                self.assertEqual(
                    z.read("taleprism/README.md"), z.read("taleprism/README.en.md")
                )
            (self.src / "taleprism-v0.9.2-last-light-project.zip").write_bytes(
                b"invalid"
            )
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                candidate.build(self.src, self.root / "bad")
            self.assertFalse((self.root / "bad").exists())
            self.assertEqual(list(self.root.glob(".taleprism-candidate-*")), [])


if __name__ == "__main__":
    unittest.main()
