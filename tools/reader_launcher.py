"""Dependency-free, package-scoped localhost launcher for exported readers.

The server is separate from the workbench. Runtime records/logs stay in a private
user cache, not in the hash-inventoried delivery. Stop uses an authenticated HTTP
request, never a PID file, process-name match, fixed port, or OS-wide kill.
"""

import argparse
import contextlib
import functools
import hashlib
import hmac
import http.server
import json
import os
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVICE = "taleprism-reader"
CONTROL = "/__taleprism_reader__/"
HEADER = "X-Taleprism-Reader-Instance"
START_TIMEOUT = 15
# Diagnostic vocabulary is deliberately closed: no records, paths, URLs, tokens,
# exception messages, response bodies, or arbitrary child output can be emitted.
PHASE_PREFIX = "TALEPRISM_READER_PHASE "
CHILD_PHASES = {
    ("entry", "ok"),
    ("package", "ok"),
    ("cache", "ok"),
    ("server_lock", "pending"),
    ("server_lock", "held"),
    ("server_constructor", "pending"),
    ("server_constructor", "ok"),
    ("record", "written"),
    ("serve_loop", "pending"),
}
PARENT_PHASES = {
    ("child", "started"),
    ("record", "missing"),
    ("record", "instance_mismatch"),
    ("server_lock", "not_held"),
    ("status", "unconfirmed"),
    ("ready", "ok"),
    *{
        (phase, outcome)
        for phase in ("index_head", "reader_head")
        for outcome in ("http_403", "http_404", "http_other", "request_failed")
    },
}


def child_phase(phase, outcome):
    if (phase, outcome) not in CHILD_PHASES:
        raise ValueError("Unsupported startup diagnostic code")
    print(PHASE_PREFIX + phase + ":" + outcome, file=sys.stderr, flush=True)


def startup_summary(directory, parent_phase):
    if parent_phase not in PARENT_PHASES:
        parent_phase = ("diagnostic", "unavailable")
    child = "unobserved"
    try:
        with (directory / "launcher.log").open("rb") as log:
            # Only recognize complete, exact, allowlisted lines. Never copy raw logs.
            for line in log.read(8192).decode("utf-8", errors="replace").splitlines():
                if line.startswith(PHASE_PREFIX):
                    pair = tuple(line[len(PHASE_PREFIX) :].split(":"))
                    if pair in CHILD_PHASES:
                        child = ":".join(pair)
    except OSError:
        pass
    return " [startup parent=" + ":".join(parent_phase) + "; child=" + child + "]"


def package_id(root):
    return hashlib.sha256(os.fsencode(root.resolve())).hexdigest()


def state_directory(root):
    cache = Path.home() / (
        "Library/Caches/Taleprism/readers"
        if sys.platform == "darwin"
        else ".cache/taleprism/readers"
    )
    path = cache / package_id(root)
    for directory in (cache, path):
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        metadata = directory.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077
        ):
            raise ValueError(
                "启动缓存不可安全使用；请检查当前账户的 Taleprism 缓存目录。 / "
                "The reader cache must be a private directory owned by this account."
            )
    return path


@contextlib.contextmanager
def lock(path, wait=True):
    import fcntl

    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        deadline = time.monotonic() + START_TIMEOUT
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not wait or time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        yield
    finally:
        os.close(descriptor)


def running(directory):
    try:
        with lock(directory / "server.lock", wait=False):
            return False
    except BlockingIOError:
        return True


def read_record(directory, root):
    try:
        value = json.loads((directory / "server.json").read_text(encoding="utf-8"))
        if (
            isinstance(value, dict)
            and value.get("service") == SERVICE
            and value.get("package_id") == package_id(root)
            and type(value.get("port")) is int
            and 1 <= value["port"] <= 65535
            and isinstance(value.get("instance_id"), str)
            and len(value["instance_id"]) == 64
            and all(c in "0123456789abcdef" for c in value["instance_id"])
        ):
            return value
    except (OSError, ValueError, TypeError):
        pass
    return None


def write_record(directory, value):
    descriptor, name = tempfile.mkstemp(prefix="record-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output)
        os.replace(name, directory / "server.json")
    finally:
        Path(name).unlink(missing_ok=True)


def base_url(record):
    return "http://127.0.0.1:" + str(record["port"])


def control(record, action="status"):
    request = urllib.request.Request(
        base_url(record) + CONTROL + action,
        headers={HEADER: record["instance_id"]},
        method="POST" if action == "stop" else "GET",
    )

    # Loopback control must not pass through environment-configured HTTP proxies.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=0.5) as response:
            result = json.loads(response.read(8193))
            return result == record and response.status == 200
    except (OSError, ValueError, urllib.error.URLError):
        return False


def readiness_phase(record):
    if not control(record):
        return ("status", "unconfirmed")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for name, phase in (("index.html", "index_head"), ("reader.json", "reader_head")):
        try:
            request = urllib.request.Request(base_url(record) + "/" + name, method="HEAD")
            with opener.open(request, timeout=0.5) as response:
                if response.status != 200:
                    return (phase, "http_other")
        except urllib.error.HTTPError as exc:
            return (phase, {403: "http_403", 404: "http_404"}.get(exc.code, "http_other"))
        except (OSError, urllib.error.URLError):
            return (phase, "request_failed")
    return ("ready", "ok")


def ready(record):
    return readiness_phase(record) == ("ready", "ok")


def validate_package(root):
    if not all((root / name).is_file() for name in ("index.html", "reader.json")):
        raise ValueError(
            "阅读器文件缺失。请完整解压 ZIP，并让启动器与 index.html、reader.json 保持同目录。 / "
            "Re-extract the complete reader ZIP; keep the launcher beside index.html and reader.json."
        )
    try:
        data = json.loads((root / "reader.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError("reader.json must contain an object")
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(
            "reader.json 无法读取。请重新完整解压阅读器 ZIP。 / Re-extract the reader ZIP."
        ) from exc


class ReaderHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # No personal reading paths or control credentials in the runtime log.

    def valid_host(self):
        return self.headers.get("Host") == "127.0.0.1:" + str(self.server.server_port)

    def authorized(self):
        return (
            self.valid_host()
            and self.headers.get("Origin") is None
            and hmac.compare_digest(
                self.headers.get(HEADER, "").encode(), self.server.record["instance_id"].encode()
            )
        )

    def send_record(self):
        raw = json.dumps(self.server.record).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == CONTROL + "status":
            if not self.authorized():
                self.send_error(404)
                return
            self.send_record()
            return
        if not self.valid_host():
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):
        if not self.valid_host():
            self.send_error(404)
            return
        super().do_HEAD()

    def do_POST(self):
        if self.path != CONTROL + "stop" or not self.authorized():
            self.send_error(404)
            return
        self.send_record()
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def send_head(self):
        # No directory listings, traversal, or symlink escape outside the delivery.
        try:
            name = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path, errors="strict")
            parts = name.lstrip("/").split("/")
            if ".." in parts or "\\" in name or "\x00" in name:
                raise ValueError()
            path = ROOT.joinpath(*parts)
            if path == ROOT:
                path /= "index.html"
            if not path.resolve().is_relative_to(ROOT) or not path.is_file():
                raise ValueError()
            relative = path.relative_to(ROOT)
            if any(
                (ROOT / parent).is_symlink()
                for parent in (relative, *relative.parents)
                if parent != Path(".")
            ):
                # Resolved containment above is the essential boundary; explicit
                # symlinks are also excluded to keep delivery contents predictable.
                raise ValueError()
        except (OSError, ValueError):
            self.send_error(404)
            return None
        return super().send_head()


def serve(instance_id):
    child_phase("entry", "ok")
    validate_package(ROOT)
    child_phase("package", "ok")
    directory = state_directory(ROOT)
    child_phase("cache", "ok")
    child_phase("server_lock", "pending")
    with lock(directory / "server.lock", wait=False):
        child_phase("server_lock", "held")
        previous = read_record(directory, ROOT)
        handler = functools.partial(ReaderHandler, directory=str(ROOT))
        # Reuse the previous OS-selected port where possible to retain the browser
        # origin. If it is occupied, ask the OS for another free loopback port.
        port = previous["port"] if previous else 0
        child_phase("server_constructor", "pending")
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        except OSError:
            if not port:
                raise
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        child_phase("server_constructor", "ok")
        server.record = {
            "service": SERVICE,
            "package_id": package_id(ROOT),
            "instance_id": instance_id,
            "port": server.server_port,
        }
        with server:
            write_record(directory, server.record)
            child_phase("record", "written")

            # A launcher-time failure terminates only this newly created child.
            # Raising lets the context manager release its socket and lifetime lock.
            def exit_signal(_signal, _frame):
                raise SystemExit(0)

            signal.signal(signal.SIGTERM, exit_signal)
            signal.signal(signal.SIGINT, exit_signal)
            child_phase("serve_loop", "pending")
            server.serve_forever(poll_interval=0.05)
    # Keep only the last port record for browser-origin continuity. No PID is used.


def stop(directory, root):
    record = read_record(directory, root)
    if not running(directory):
        print("阅读器已停止；没有停止其他程序。 / Reader is stopped; no other program was stopped.")
        return
    if not record or not control(record) or not control(record, "stop"):
        raise ValueError(
            "无法确认此阅读包的运行实例；没有停止其他程序。请稍后重试。 / "
            "Cannot verify this reader instance. No other program was stopped; try again shortly."
        )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not running(directory):
            print(
                "阅读器已停止；文件与浏览器记录保留。 / Reader stopped; files and browser data kept."
            )
            return
        time.sleep(0.05)
    raise ValueError(
        "阅读器仍在退出，请稍后再试。 / The reader is still stopping; try again shortly."
    )


def start(directory, root, open_browser=True):
    validate_package(root)
    record = read_record(directory, root)
    if running(directory):
        if not record or not ready(record):
            raise ValueError(
                "此阅读包的服务未通过就绪检查，没有打开浏览器。请稍后重试。 / "
                "This reader failed its readiness check; the browser was not opened. Try again shortly."
            )
    else:
        instance_id = secrets.token_hex(32)
        # -I prevents local modules/PYTHONPATH from shadowing the standard library;
        # -B avoids __pycache__ files altering the archived delivery inventory.
        with (directory / "launcher.log").open("wb") as log:
            process = subprocess.Popen(
                [sys.executable, "-I", "-B", str(root / "reader_launcher.py"), "--serve"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        try:
            process.stdin.write(instance_id.encode("ascii"))
            process.stdin.close()
            deadline = time.monotonic() + START_TIMEOUT
            phase = ("child", "started")
            while time.monotonic() < deadline:
                record = read_record(directory, root)
                if not record:
                    phase = ("record", "missing")
                elif record["instance_id"] != instance_id:
                    phase = ("record", "instance_mismatch")
                elif not running(directory):
                    phase = ("server_lock", "not_held")
                else:
                    phase = readiness_phase(record)
                    if phase == ("ready", "ok"):
                        break
                if process.poll() is not None:
                    raise ValueError(
                        "阅读器服务提前退出。 / The reader server exited during startup."
                        + startup_summary(directory, phase)
                    )
                time.sleep(0.05)
            else:
                raise ValueError(
                    "阅读器启动超时。 / The reader server did not become ready in time."
                    + startup_summary(directory, phase)
                )
        except BaseException:
            # This handle belongs only to the child we just created, never a saved PID.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
            raise
        # Reap our own child when this module is embedded in a longer-lived process.
        threading.Thread(target=process.wait, daemon=True).start()
    url = base_url(record) + "/"
    print("阅读器已就绪 / Reader ready: " + url)
    print("阅读完成后双击「停止阅读器.command」。 / Double-click Stop Reader when finished.")
    if open_browser:
        try:
            opened = webbrowser.open(url)
        except (OSError, webbrowser.Error):
            opened = False
        if not opened:
            print(
                "无法自动打开浏览器；请点击或复制上方网址。 / Open the URL above in your browser."
            )
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.serve:
        instance_id = sys.stdin.read(65)
        if len(instance_id) != 64 or any(c not in "0123456789abcdef" for c in instance_id):
            raise ValueError("Invalid reader instance")
        serve(instance_id)
        return
    directory = state_directory(ROOT)
    with lock(directory / "launcher.lock"):
        if args.stop:
            stop(directory, ROOT)
        else:
            start(directory, ROOT, not args.no_open)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print("Taleprism 阅读器 / Reader: " + str(exc), file=sys.stderr)
        print(
            "未安装软件或更改安全设置。请确认阅读包完整、路径可读及用户缓存可写后重试。 / "
            "Nothing was installed and no security settings were changed. "
            "Check the complete extracted folder is readable and your user cache is writable.",
            file=sys.stderr,
        )
        sys.exit(1)
