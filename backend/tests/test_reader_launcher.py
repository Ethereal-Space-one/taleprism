"""Portable launcher regressions. Finder/Gatekeeper behavior still needs a real Mac.

Uses unittest as well as pytest collection, so the stdlib-only launcher checks
can run without installing a test runner: python3 backend/tests/test_reader_launcher.py
"""

import concurrent.futures
import hashlib
import http.server
import importlib.util
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "export_reader_launcher", ROOT / "tools/reader_launcher.py"
)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class ForeignHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"unrelated service")

    def log_message(self, *_args):
        pass


class ReaderLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="reader-launcher-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "home"
        self.home.mkdir()
        self.environment = {**os.environ, "HOME": str(self.home)}
        self.environment.pop("PYTHONPATH", None)
        self.env_patch = patch.dict(os.environ, {"HOME": str(self.home)})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.root = self.directory / "阅读器 space ' $(touch SHOULD_NOT_EXIST)"
        self.root.mkdir()
        self.other = self.directory / "unrelated cwd"
        self.other.mkdir()
        for name in ("reader_launcher.py", "verify_package.py"):
            shutil.copyfile(ROOT / "tools" / name, self.root / name)
        for name in ("打开阅读器.command", "停止阅读器.command"):
            shutil.copyfile(ROOT / "tools/reader_launcher.command", self.root / name)
            (self.root / name).chmod(0o755)
        (self.root / "index.html").write_text("<html>the correct exported reader</html>")
        (self.root / "reader.json").write_text('{"schema_version": 1}')
        (self.root / "assets").mkdir()
        (self.root / "assets/app.js").write_text("// isolated reader")
        self.root_patch = patch.object(launcher, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.state = launcher.state_directory(self.root)
        self.addCleanup(self.ensure_stopped)

    def run_launcher(self, *args):
        return subprocess.run(
            check=False,
            args=[sys.executable, "-I", "-B", str(self.root / "reader_launcher.py"), *args],
            env=self.environment,
            cwd=self.other,
            capture_output=True,
            text=True,
            timeout=25,
        )

    def start(self):
        result = self.run_launcher("--no-open")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = launcher.read_record(self.state, self.root)
        self.assertIsNotNone(record)
        self.assertTrue(launcher.ready(record))
        return record

    def ensure_stopped(self):
        self.run_launcher("--stop")

    def request(self, record, path="/", headers=None, method="GET"):
        request = urllib.request.Request(
            launcher.base_url(record) + path, headers=headers or {}, method=method
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=2)

    def foreign_server(self, port=0):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), ForeignHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_actual_start_reuses_owned_instance_and_keeps_package_clean(self):
        initial = {p.relative_to(self.root) for p in self.root.rglob("*")}
        first = self.start()
        second = self.start()
        self.assertEqual(first, second)
        with self.request(first) as response:
            self.assertIn(b"the correct exported reader", response.read())
        with self.request(first, "/reader.json") as response:
            self.assertEqual(json.loads(response.read())["schema_version"], 1)
        self.assertEqual(initial, {p.relative_to(self.root) for p in self.root.rglob("*")})
        self.assertFalse((self.other / "SHOULD_NOT_EXIST").exists())
        self.assertFalse((self.root / "__pycache__").exists())
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.state / "server.json").stat().st_mode & 0o777, 0o600)
        # Confirm the live listener owns its chosen loopback port.
        with socket.socket() as probe, self.assertRaises(OSError):
            probe.bind(("127.0.0.1", first["port"]))
        result = self.run_launcher("--stop")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(launcher.running(self.state))
        self.assertEqual(self.run_launcher("--stop").returncode, 0)

    def test_concurrent_double_clicks_start_only_one_instance(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.run_launcher("--no-open"), range(2)))
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        urls = [result.stdout.splitlines()[0] for result in results]
        self.assertEqual(urls[0], urls[1])
        self.assertTrue(launcher.ready(launcher.read_record(self.state, self.root)))

    def test_browser_is_opened_only_after_http_and_package_readiness(self):
        opened = []

        def open_browser(url):
            record = launcher.read_record(self.state, self.root)
            self.assertTrue(launcher.ready(record))
            self.assertEqual(url, launcher.base_url(record) + "/")
            opened.append(url)
            return True

        with patch.object(launcher.webbrowser, "open", side_effect=open_browser):
            launcher.main([])
        self.assertEqual(len(opened), 1)

    def test_failed_readiness_does_not_open_browser_and_cleans_owned_child(self):
        child = Mock()
        child.stdin = io.BytesIO()
        child.poll.return_value = None
        with (
            patch.object(launcher.subprocess, "Popen", return_value=child),
            patch.object(launcher, "START_TIMEOUT", 0),
            patch.object(launcher.webbrowser, "open") as open_browser,
            self.assertRaisesRegex(ValueError, "ready"),
        ):
            launcher.start(self.state, self.root)
        child.terminate.assert_called_once()
        child.wait.assert_called_once_with(timeout=3)
        open_browser.assert_not_called()

    def test_port_is_automatic_sticky_and_busy_port_uses_another(self):
        first = self.start()
        self.assertEqual(self.run_launcher("--stop").returncode, 0)
        second = self.start()
        self.assertEqual(first["port"], second["port"])
        self.assertNotEqual(first["instance_id"], second["instance_id"])
        self.assertEqual(self.run_launcher("--stop").returncode, 0)
        foreign = self.foreign_server(second["port"])
        third = self.start()
        self.assertNotEqual(third["port"], foreign.server_port)
        self.assertEqual(self.run_launcher("--stop").returncode, 0)
        foreign_record = {"port": foreign.server_port}
        with self.request(foreign_record) as response:
            self.assertEqual(response.read(), b"unrelated service")

    def test_stale_or_foreign_record_cannot_stop_any_process(self):
        owned = self.start()
        foreign = self.foreign_server()
        launcher.write_record(self.state, {**owned, "port": foreign.server_port})
        result = self.run_launcher("--stop")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No other program was stopped", result.stderr)
        self.assertTrue(launcher.control(owned))
        with self.request({"port": foreign.server_port}) as response:
            self.assertEqual(response.read(), b"unrelated service")
        launcher.write_record(self.state, owned)
        self.assertEqual(self.run_launcher("--stop").returncode, 0)

    def test_invalid_records_never_signal_or_reuse_a_service(self):
        for value in (None, True, 123, {}, {"port": 8000}, {"instance_id": "bad"}):
            with self.subTest(value=value):
                (self.state / "server.json").write_text(json.dumps(value))
                result = self.run_launcher("--stop")
                self.assertEqual(result.returncode, 0, result.stderr)
        self.start()

    def test_control_requires_private_instance_and_expected_host_and_origin(self):
        record = self.start()
        for headers in (
            {},
            {launcher.HEADER: "wrong"},
            {launcher.HEADER: record["instance_id"], "Origin": "https://foreign.invalid"},
            {launcher.HEADER: record["instance_id"], "Host": "foreign.invalid"},
        ):
            with self.subTest(headers=headers):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.request(record, launcher.CONTROL + "stop", headers, "POST")
                self.assertEqual(caught.exception.code, 404)
                self.assertTrue(launcher.control(record))
        with self.assertRaises(urllib.error.HTTPError):
            self.request(record, headers={"Host": "foreign.invalid"})

    def test_static_server_rejects_traversal_directory_listing_and_symlink_escape(self):
        secret = self.directory / "outside.txt"
        secret.write_text("not in this reader")
        (self.root / "escape.txt").symlink_to(secret)
        (self.root / "escape").symlink_to(self.directory, target_is_directory=True)
        record = self.start()
        for path in (
            "/../outside.txt",
            "/%2e%2e/outside.txt",
            "/assets/",
            "/escape.txt",
            "/escape/outside.txt",
            "/a%00b",
            "/%FF",
        ):
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    self.request(record, path)
                self.assertEqual(caught.exception.code, 404)
        with self.request(record, "/assets/app.js") as response:
            self.assertEqual(response.status, 200)

    def test_missing_or_invalid_reader_gives_actionable_error_without_browser(self):
        (self.root / "reader.json").unlink()
        result = self.run_launcher("--no-open")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Re-extract", result.stderr)
        self.assertFalse(launcher.running(self.state))
        (self.root / "reader.json").write_text("{broken")
        result = self.run_launcher("--no-open")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reader.json", result.stderr)

    def test_shell_start_and_stop_from_unrelated_cwd_quote_package_path(self):
        result = subprocess.run(
            ["/bin/bash", str(self.root / "打开阅读器.command")],
            check=False,
            cwd=self.other,
            env={**self.environment, "BROWSER": "/bin/true"},
            capture_output=True,
            text=True,
            timeout=25,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(launcher.ready(launcher.read_record(self.state, self.root)))
        result = subprocess.run(
            ["/bin/bash", str(self.root / "停止阅读器.command")],
            check=False,
            cwd=self.other,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(launcher.running(self.state))
        self.assertFalse((self.other / "SHOULD_NOT_EXIST").exists())

    def test_server_bind_is_only_loopback_with_os_selected_port(self):
        server = Mock()
        server.server_port = 34123
        server.__enter__ = Mock(return_value=server)
        server.__exit__ = Mock(return_value=False)
        with (
            patch.object(launcher.http.server, "ThreadingHTTPServer", return_value=server) as make,
            patch.object(launcher.signal, "signal"),
        ):
            launcher.serve("a" * 64)
        self.assertEqual(make.call_args.args[0], ("127.0.0.1", 0))

    def test_shell_path_error_and_missing_python_are_actionable(self):
        (self.root / "reader_launcher.py").unlink()
        result = subprocess.run(
            check=False,
            args=["/bin/bash", str(self.root / "打开阅读器.command")],
            cwd=self.other,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Re-extract", result.stderr)
        # Exercise the missing-interpreter branch without changing this host's Python.
        shutil.copyfile(ROOT / "tools/reader_launcher.py", self.root / "reader_launcher.py")
        raw = (ROOT / "tools/reader_launcher.command").read_text()
        for candidate in (
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
            "/usr/bin/python3",
        ):
            raw = raw.replace(candidate, str(self.directory / "absent-python"))
        (self.root / "打开阅读器.command").write_text(raw)
        path = self.directory / "minimal-path"
        path.mkdir()
        (path / "dirname").symlink_to(shutil.which("dirname"))
        result = subprocess.run(
            check=False,
            args=["/bin/bash", str(self.root / "打开阅读器.command")],
            cwd=self.other,
            env={**self.environment, "PATH": str(path)},
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Python 3.9+ is required", result.stderr)
        self.assertIn("Nothing was installed", result.stderr)

    def test_reader_manifest_verifies_before_and_after_using_launcher(self):
        inventory = {
            "export_id": "launcher-fixture",
            "files": {
                p.relative_to(self.root).as_posix(): {
                    "bytes": p.stat().st_size,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
                for p in self.root.rglob("*")
                if p.is_file()
            },
        }
        (self.root / "storygal-delivery.json").write_text(json.dumps(inventory))
        self.start()
        self.assertEqual(self.run_launcher("--stop").returncode, 0)
        result = subprocess.run(
            check=False,
            args=[sys.executable, "-I", "-B", str(self.root / "verify_package.py")],
            cwd=self.other,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["passed"])


class ReaderLauncherPackagingTests(unittest.TestCase):
    def test_normal_export_inventories_launcher_and_preserves_executable_zip_metadata(self):
        from fastapi.testclient import TestClient

        from storygal import reader_export
        from storygal.app import create_app

        with tempfile.TemporaryDirectory(prefix="reader-export-test-") as temporary:
            root = Path(temporary)
            repo = root / "source"
            (repo / "frontend/dist/assets").mkdir(parents=True)
            (repo / "frontend/dist/index.html").write_text(
                '<head></head><script src="/assets/app.js"></script>'
            )
            (repo / "frontend/dist/assets/app.js").write_text("// test")
            (repo / "tools").mkdir()
            for name in ("verify_package.py", "reader_launcher.py", "reader_launcher.command"):
                shutil.copyfile(ROOT / "tools" / name, repo / "tools" / name)
            with patch.object(reader_export, "REPO", repo):
                client = TestClient(create_app(root / "data"))
                raw = "第一章\n林遥说：「等一会儿。」\n雨停了。".encode()
                pid = client.post(
                    "/api/projects",
                    files={"file": ("ordinary.txt", raw)},
                    data={"rights_status": "owned"},
                ).json()["id"]
                response = client.post(f"/api/projects/{pid}/reader/exports")
                self.assertEqual(response.status_code, 202, response.text)
                job = client.get(f"/api/projects/{pid}/jobs").json()[0]
                self.assertEqual(job["state"], "completed", job)
                packed = client.get(job["result"]["download_url"]).content
            with zipfile.ZipFile(io.BytesIO(packed)) as archive:
                inventory = json.loads(archive.read("storygal-delivery.json"))
                self.assertEqual(
                    set(archive.namelist()), set(inventory["files"]) | {"storygal-delivery.json"}
                )
                self.assertEqual(archive.read("storygal-source/original.txt"), raw)
                for name in ("reader_launcher.py", "打开阅读器.command", "停止阅读器.command"):
                    self.assertIn(name, inventory["files"])
                    self.assertEqual(
                        hashlib.sha256(archive.read(name)).hexdigest(),
                        inventory["files"][name]["sha256"],
                    )
                for name in ("打开阅读器.command", "停止阅读器.command"):
                    info = archive.getinfo(name)
                    self.assertEqual(info.create_system, 3)
                    self.assertEqual((info.external_attr >> 16) & 0o777, 0o755)
                self.assertIn("完整解压", archive.read("README.txt").decode())
                unpacked = root / "unpacked"
                archive.extractall(unpacked)
            checked = subprocess.run(
                check=False,
                args=[sys.executable, "-I", "-B", str(unpacked / "verify_package.py")],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_chibi_repack_also_preserves_command_executable_bit(self):
        with patch.object(sys, "path", [str(ROOT / "tools"), *sys.path]):
            import build_chibi_demo
        with zipfile.ZipFile(
            io.BytesIO(
                build_chibi_demo.pack(
                    {"打开阅读器.command": b"#!/bin/bash\n", "reader.json": b"{}"}
                )
            )
        ) as archive:
            self.assertEqual(archive.getinfo("打开阅读器.command").create_system, 3)
            self.assertEqual(
                (archive.getinfo("打开阅读器.command").external_attr >> 16) & 0o777, 0o755
            )
            self.assertEqual((archive.getinfo("reader.json").external_attr >> 16) & 0o777, 0o644)


if __name__ == "__main__":
    # Existing application dependencies are needed only by the two packaging tests.
    sys.path.insert(0, str(ROOT / "backend/src"))
    unittest.main(verbosity=2)
