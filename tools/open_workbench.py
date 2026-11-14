"""Start/stop only the workbench belonging to this workspace and data directory."""

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from storygal.settings import load_env

ROOT = Path(__file__).resolve().parents[1]


def identity(root, data):
    return {
        "workspace_id": hashlib.sha256(str(root.resolve()).encode()).hexdigest(),
        "data_id": hashlib.sha256(str(data.resolve()).encode()).hexdigest(),
    }


def health(base):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(base + "/api/health", timeout=1) as response:
            result = json.loads(response.read(16385))
            return result if isinstance(result, dict) else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


def matches(body, expected):
    return bool(
        body
        and body.get("status") == "ok"
        and body.get("service") == "taleprism"
        and all(body.get(k) == v for k, v in expected.items())
        and isinstance(body.get("pid"), int)
        and body["pid"] > 1
        and isinstance(body.get("instance_id"), str)
        and body["instance_id"]
    )


def read_record(path):
    try:
        record = json.loads(path.read_text())
        if type(record) is int and record > 1:
            return {"pid": record, "legacy": True}
        if (
            isinstance(record, dict)
            and "legacy" not in record
            and type(record.get("pid")) is int
            and record["pid"] > 1
        ):
            return record
    except (OSError, ValueError):
        pass
    return None


def legacy_python_matches(executable, python):
    if executable == python:
        return True
    if sys.platform != "darwin":
        return False
    resolved = python.resolve(strict=True)
    if executable == resolved:
        return True
    # The macOS framework launcher execs Python.app, so ps may show that binary.
    version = resolved.parent.parent
    framework_python = version / "Resources/Python.app/Contents/MacOS/Python"
    return (
        resolved.parent.name == "bin"
        and version.parent.name == "Versions"
        and version.parent.parent.name == "Python.framework"
        and executable == framework_python
        and framework_python.is_file()
    )


def legacy_process(pid, root, data, port):
    """v0.1 pid files have no identity: require exact command, cwd AND held data lock."""
    try:
        result = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        suffix = f" -m uvicorn storygal.app:app --host 127.0.0.1 --port {port}"
        command = result.stdout.strip()
        if result.returncode or not command.endswith(suffix):
            return False
        executable = Path(command.removesuffix(suffix))
        if not legacy_python_matches(executable, root / "backend/.venv/bin/python"):
            return False
        proc = Path(f"/proc/{pid}")
        lock = (data / ".instance.lock").resolve()
        if proc.is_dir():
            return (proc / "cwd").resolve() == root and any(
                fd.resolve() == lock for fd in (proc / "fd").iterdir()
            )
        files = subprocess.run(
            ["lsof", "-nP", "-p", str(pid), "-Ffn"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if files.returncode:
            return False
        descriptor = ""
        paths = {}
        for line in files.stdout.splitlines():
            if line.startswith("f"):
                descriptor = line[1:]
            elif line.startswith("n/"):
                paths[descriptor] = Path(line[1:]).resolve()
        return paths.get("cwd") == root and any(
            fd.isdecimal() and path == lock for fd, path in paths.items()
        )
    except (OSError, subprocess.SubprocessError):
        return False


def legacy_matches(body, record, root, data, port):
    return bool(
        record
        and record.get("legacy")
        and body
        and body.get("status") == "ok"
        and body.get("version") == "0.1.0"
        and "engine_available" in body
        and "instance_id" not in body
        and legacy_process(record["pid"], root, data, port)
    )


def find_legacy_record(pidfile, record, body, root, data, port):
    if legacy_matches(body, record, root, data, port):
        return pidfile, record
    # v0.1 wrote here even when the server used a custom data directory.
    former = root / "data" / pidfile.name
    if former != pidfile:
        former_record = read_record(former)
        if legacy_matches(body, former_record, root, data, port):
            return former, former_record
    return None


def process_running(pid):
    """A closed HTTP socket is not process exit (uvicorn may be draining workers)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        proc = Path(f"/proc/{pid}/stat")
        if proc.exists():
            return proc.read_text().rsplit(")", 1)[1].split()[0] != "Z"
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        return not result.stdout.lstrip().startswith("Z")
    except (OSError, subprocess.SubprocessError, IndexError):
        return True  # If exit cannot be proved, do not announce a safe backup point.


def data_lock_available(data):
    import fcntl

    try:
        with (data / ".instance.lock").open("r+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def stopped(record, data):
    return not process_running(record["pid"]) and data_lock_available(data)


def stop(pidfile, body, expected, root, data, port, base):
    record = read_record(pidfile)
    if (
        record
        and not record.get("legacy")
        and body is None
        and all(record.get(k) == v for k, v in expected.items())
        and record.get("port") == port
    ):
        if stopped(record, data):
            if read_record(pidfile) == record:
                pidfile.unlink(missing_ok=True)
            print("Taleprism 已停止，项目与作品保留。")
            return
        raise ValueError(
            "服务尚未确认退出或数据目录仍被占用；保留启动记录，请稍后重试。"
        )
    owned = (
        record
        and matches(body, expected)
        and all(
            record.get(k) == body.get(k)
            for k in ["pid", "instance_id", "workspace_id", "data_id"]
        )
        and record.get("port") == port
    )
    if not owned:
        legacy = find_legacy_record(pidfile, record, body, root, data, port)
        if legacy:
            pidfile, record = legacy
        elif record:
            raise ValueError(
                "启动记录与当前工作区、数据或运行实例不一致；没有停止任何程序。"
            )
        else:
            print(
                "没有有效后台启动记录。前台服务请在对应终端按 Control+C；没有停止其他程序。"
            )
            return
    # Recheck immediately before signalling: an old pid file must not target a replacement.
    current = health(base)
    still_owned = (
        current == body if owned else legacy_matches(current, record, root, data, port)
    )
    if not still_owned or read_record(pidfile) != record:
        raise ValueError("运行实例已改变；没有停止任何程序，请重新检查。")
    os.kill(record["pid"], signal.SIGTERM)
    for _ in range(50):
        if stopped(record, data):
            if read_record(pidfile) == record:
                pidfile.unlink(missing_ok=True)
            print("Taleprism 已停止，项目与作品保留。")
            return
        time.sleep(0.1)
    raise ValueError(
        "已请求停止，进程仍在退出或数据锁尚未释放；保留启动记录，请稍后重试。"
    )


def occupied(port):
    with socket.socket() as connection:
        connection.settimeout(0.5)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def terminate_child(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-open", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--stop", action="store_true")
    mode.add_argument("--foreground", action="store_true")
    args = parser.parse_args(argv)
    root = ROOT.resolve()
    load_env(root / ".env")
    try:
        port = int(os.environ.get("STORYGAL_PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError()
    except ValueError:
        raise ValueError("端口应为 1–65535 之间的整数。") from None
    configured_data = Path(
        os.environ.get("STORYGAL_DATA_DIR") or root / "data"
    ).expanduser()
    data = (root / configured_data).resolve()
    expected = identity(root, data)
    base = f"http://127.0.0.1:{port}"
    pidfile = data / f"workbench-{port}.pid"
    body = health(base)
    if args.stop:
        stop(pidfile, body, expected, root, data, port, base)
        return
    reuse = matches(body, expected) or find_legacy_record(
        pidfile, read_record(pidfile), body, root, data, port
    )
    if not reuse:
        if body is not None or occupied(port):
            raise ValueError(
                "此端口已被其他服务或其他工作区／数据实例占用。请切换 STORYGAL_PORT，"
                "或在原工作区停止对应实例；不会复用或停止它。"
            )
        python = root / "backend/.venv/bin/python"
        if not python.is_file() or not (root / "frontend/dist/index.html").is_file():
            raise ValueError("尚未完成首次准备，请先运行 start.sh。")
        command = [
            str(python),
            "-m",
            "uvicorn",
            "storygal.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        env = {**os.environ, "STORYGAL_DATA_DIR": str(data)}
        if args.foreground:
            print("Taleprism：打开 " + base, flush=True)
            print("关闭此终端会停止工作台；项目和已导出工程仍保留在本机。", flush=True)
            os.chdir(root)
            os.execve(python, command, env)
        data.mkdir(parents=True, exist_ok=True)
        with (data / "workbench.log").open("ab") as log:
            process = subprocess.Popen(
                command,
                cwd=root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        try:
            for _ in range(60):
                if process.poll() is not None:
                    raise ValueError(
                        "启动失败，请查看所选数据目录下的 workbench.log；端口或数据目录可能已被占用。"
                    )
                body = health(base)
                if matches(body, expected) and body["pid"] == process.pid:
                    record = {
                        **expected,
                        "pid": process.pid,
                        "instance_id": body["instance_id"],
                        "port": port,
                    }
                    temporary = pidfile.with_suffix(f".{process.pid}.tmp")
                    try:
                        temporary.write_text(json.dumps(record))
                        temporary.replace(pidfile)
                    finally:
                        temporary.unlink(missing_ok=True)
                    break
                if body is not None:
                    raise ValueError("端口上出现了其他运行实例，已取消本次启动。")
                time.sleep(0.2)
            else:
                raise ValueError("启动超时，请查看所选数据目录下的 workbench.log。")
        except BaseException:
            terminate_child(process)
            raise
    print("Taleprism 已就绪：" + base)
    if reuse:
        print("已复用此工作区及数据目录的现有实例。")
    else:
        print(
            "服务在后台运行；需要退出时使用同一数据配置双击「停止Taleprism.command」。"
        )
    if not args.no_open and not args.foreground:
        webbrowser.open(base)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
