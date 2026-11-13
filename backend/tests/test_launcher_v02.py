"""Launcher identity regressions, including isolated real uvicorn and legacy pid records."""

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "workbench_launcher_v02", ROOT / "tools/open_workbench.py"
)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def port_number():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def context(monkeypatch, tmp_path):
    root = tmp_path / "workspace with spaces"
    root.mkdir()
    data = tmp_path / "selected data"
    port = 18432
    monkeypatch.setattr(launcher, "ROOT", root)
    monkeypatch.setattr(launcher, "load_env", lambda *_: None)
    monkeypatch.setenv("STORYGAL_DATA_DIR", str(data))
    monkeypatch.setenv("STORYGAL_PORT", str(port))
    body = {
        **launcher.identity(root, data),
        "service": "taleprism",
        "status": "ok",
        "version": "0.2.0",
        "pid": 54321,
        "instance_id": "instance-a",
    }
    monkeypatch.setattr(launcher, "health", lambda _: body.copy())
    return root, data, port, body


@pytest.mark.parametrize(
    "change",
    [
        {"workspace_id": "other"},
        {"data_id": "other"},
        {"service": "other"},
        {"status": "ok", "engine_available": True, "version": "0.1.0"},
    ],
)
def test_foreign_health_never_reused_or_spawned(context, monkeypatch, change):
    _, _, _, body = context
    foreign = change if "engine_available" in change else {**body, **change}
    monkeypatch.setattr(launcher, "health", lambda _: foreign)
    monkeypatch.setattr(
        launcher.subprocess, "Popen", lambda *_a, **_k: pytest.fail("Must not spawn")
    )
    monkeypatch.setattr(
        launcher.webbrowser, "open", lambda *_: pytest.fail("Must not open foreign service")
    )
    with pytest.raises(ValueError, match="其他"):
        launcher.main(["--no-open"])


def test_matching_direct_uvicorn_instance_reused_without_pidfile(context, monkeypatch):
    monkeypatch.setattr(
        launcher.subprocess, "Popen", lambda *_a, **_k: pytest.fail("Must not spawn")
    )
    launcher.main(["--no-open"])
    assert not context[1].exists()


@pytest.mark.parametrize(
    "change",
    [
        {"pid": 54322},
        {"instance_id": "old"},
        {"data_id": "other"},
        {"workspace_id": "other"},
        {"port": 9000},
    ],
)
def test_stop_refuses_stale_or_foreign_record(context, monkeypatch, change):
    _, data, port, body = context
    data.mkdir()
    record = {**body, "port": port, **change}
    path = data / f"workbench-{port}.pid"
    path.write_text(json.dumps(record))
    monkeypatch.setattr(launcher.os, "kill", lambda *_: pytest.fail("Must not kill"))
    with pytest.raises(ValueError, match="没有停止"):
        launcher.main(["--stop"])
    assert json.loads(path.read_text()) == record


def test_stop_rechecks_instance_before_signal(context, monkeypatch):
    _, data, port, body = context
    data.mkdir()
    (data / f"workbench-{port}.pid").write_text(json.dumps({**body, "port": port}))
    bodies = iter([body, {**body, "instance_id": "replacement"}])
    monkeypatch.setattr(launcher, "health", lambda _: next(bodies))
    monkeypatch.setattr(launcher.os, "kill", lambda *_: pytest.fail("Must not kill replacement"))
    with pytest.raises(ValueError, match="运行实例已改变"):
        launcher.main(["--stop"])


def test_legacy_workspace_pidfile_is_rechecked_before_signal(context, monkeypatch):
    root, data, port, body = context
    path = root / "data" / f"workbench-{port}.pid"
    path.parent.mkdir()
    path.write_text(str(body["pid"]))
    legacy_health = {"status": "ok", "version": "0.1.0", "engine_available": False}
    monkeypatch.setattr(launcher, "health", lambda _: legacy_health)
    checks = iter([True, False])

    def verify(pid, workspace, selected_data, expected_port):
        assert (pid, workspace, selected_data, expected_port) == (body["pid"], root, data, port)
        return next(checks)

    monkeypatch.setattr(launcher, "legacy_process", verify)
    monkeypatch.setattr(launcher.os, "kill", lambda *_: pytest.fail("Must not kill replacement"))
    with pytest.raises(ValueError, match="运行实例已改变"):
        launcher.main(["--stop"])
    assert path.read_text() == str(body["pid"])


@pytest.mark.parametrize("record", ["not a pid", "-1", "true", '{"pid": 1}', '{"pid":"54321"}'])
def test_invalid_pidfiles_do_not_signal(context, monkeypatch, record):
    _, data, port, _ = context
    data.mkdir()
    (data / f"workbench-{port}.pid").write_text(record)
    monkeypatch.setattr(launcher.os, "kill", lambda *_: pytest.fail("Must not signal"))
    launcher.main(["--stop"])


def test_non_http_listener_is_not_replaced(context, monkeypatch):
    monkeypatch.setattr(launcher, "health", lambda _: None)
    monkeypatch.setattr(launcher, "occupied", lambda _: True)
    monkeypatch.setattr(
        launcher.subprocess, "Popen", lambda *_a, **_k: pytest.fail("Must not spawn")
    )
    with pytest.raises(ValueError, match="端口已被"):
        launcher.main(["--no-open"])


def test_foreground_uses_same_identity_check(context, monkeypatch):
    body = {**context[3], "data_id": "foreign"}
    monkeypatch.setattr(launcher, "health", lambda _: body)
    monkeypatch.setattr(launcher.os, "execve", lambda *_: pytest.fail("Must not launch"))
    with pytest.raises(ValueError, match="其他工作区"):
        launcher.main(["--foreground"])


def test_relative_data_path_and_env_file_use_workspace(context, monkeypatch):
    root, _, _, _ = context
    monkeypatch.setenv("STORYGAL_DATA_DIR", "custom/data")
    monkeypatch.setattr(launcher, "health", lambda _: None)
    monkeypatch.setattr(launcher, "occupied", lambda _: False)
    (root / "backend/.venv/bin").mkdir(parents=True)
    (root / "backend/.venv/bin/python").touch()
    (root / "frontend/dist").mkdir(parents=True)
    (root / "frontend/dist/index.html").touch()

    class Captured(Exception):
        pass

    seen = {}

    def execute(executable, command, env):
        seen.update(executable=executable, command=command, env=env)
        raise Captured()

    monkeypatch.setattr(launcher.os, "execve", execute)
    monkeypatch.setattr(launcher.os, "chdir", lambda path: seen.update(cwd=path))
    with pytest.raises(Captured):
        launcher.main(["--foreground"])
    assert seen["env"]["STORYGAL_DATA_DIR"] == str(root / "custom/data")
    assert seen["cwd"] == root
    assert str(root / "backend/.venv/bin/python") == seen["command"][0]


@pytest.mark.parametrize("port", ["0", "65536", "-2", "abc"])
def test_invalid_port_has_actionable_error(context, monkeypatch, port):
    monkeypatch.setenv("STORYGAL_PORT", port)
    with pytest.raises(ValueError, match="1–65535"):
        launcher.main(["--no-open"])


@pytest.fixture
def actual(monkeypatch, tmp_path):
    root = tmp_path / "isolated workbench"
    (root / "backend/src").mkdir(parents=True)
    shutil.copytree(
        ROOT / "backend/src/storygal",
        root / "backend/src/storygal",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # Reuse installed dependencies, but load ONLY the copied application source.
    (root / "backend/.venv").symlink_to(Path(sys.prefix), target_is_directory=True)
    (root / "frontend/dist").mkdir(parents=True)
    (root / "frontend/dist/index.html").write_text("<html></html>")
    data = tmp_path / "isolated data"
    port = port_number()
    monkeypatch.setattr(launcher, "ROOT", root)
    monkeypatch.setenv("STORYGAL_DATA_DIR", str(data))
    monkeypatch.setenv("STORYGAL_PORT", str(port))
    monkeypatch.setenv("PYTHONPATH", str(root / "backend/src"))
    for name in list(os.environ):
        if name.startswith("STORYGAL_LLM_") or name in {
            "OPENAI_API_KEY",
            "DEEPSEEK_API_KEY",
            "DeepSeek_ApiKeyN",
            "deepseek-apin",
        }:
            monkeypatch.delenv(name)
    processes = []
    original = subprocess.Popen

    def spawn(*args, **kwargs):
        process = original(*args, **kwargs)
        if "uvicorn" in args[0]:
            processes.append(process)
        return process

    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    yield root, data, port, processes
    for process in processes:
        launcher.terminate_child(process)


def test_real_launch_reuse_stop_and_wrong_data_protection(actual, monkeypatch):
    root, data, port, processes = actual
    launcher.main(["--no-open"])
    base = f"http://127.0.0.1:{port}"
    body = launcher.health(base)
    assert launcher.matches(body, launcher.identity(root, data))
    assert body["version"] == "0.2.0"
    record_path = data / f"workbench-{port}.pid"
    record = json.loads(record_path.read_text())
    assert record["instance_id"] == body["instance_id"]
    launcher.main(["--no-open"])
    assert len(processes) == 1
    foreign_data = data.parent / "different data"
    foreign_data.mkdir()
    (foreign_data / record_path.name).write_text(json.dumps(record))
    monkeypatch.setenv("STORYGAL_DATA_DIR", str(foreign_data))
    for mode in ["--no-open", "--stop", "--foreground"]:
        with pytest.raises(ValueError):
            launcher.main([mode])
    assert launcher.health(base)["instance_id"] == body["instance_id"]
    assert processes[0].poll() is None
    monkeypatch.setenv("STORYGAL_DATA_DIR", str(data))
    launcher.main(["--stop"])
    processes[0].wait(timeout=5)
    assert not record_path.exists()
    assert launcher.health(base) is None
    assert (data / "storygal.sqlite3").exists() or list(data.glob("*.sqlite*"))


@pytest.mark.parametrize("location", ["selected_data", "workspace_data"])
def test_running_v01_pidfile_can_be_reused_and_stopped_after_process_verification(
    actual, monkeypatch, location
):
    root, data, port, processes = actual
    launcher.main(["--no-open"])
    process = processes[0]
    assert launcher.legacy_process(process.pid, root, data, port)
    assert not launcher.legacy_process(process.pid, root, data.parent / "wrong", port)
    assert not launcher.legacy_process(process.pid, root.parent, data, port)
    assert not launcher.legacy_process(process.pid, root, data, port + 1)
    selected_record = data / f"workbench-{port}.pid"
    selected_contents = selected_record.read_bytes()
    record_path = selected_record
    if location == "workspace_data":
        record_path = root / "data" / selected_record.name
        record_path.parent.mkdir()
        selected_record.unlink()
    record_path.write_text(str(process.pid))
    actual_health = launcher.health

    def legacy_health(base):
        if actual_health(base):
            return {"status": "ok", "version": "0.1.0", "engine_available": False}
        return None

    monkeypatch.setattr(launcher, "health", legacy_health)
    if location == "workspace_data":
        monkeypatch.setenv("STORYGAL_DATA_DIR", str(data.parent / "wrong"))
        with pytest.raises(ValueError, match="端口已被"):
            launcher.main(["--no-open"])
        launcher.main(["--stop"])
        assert process.poll() is None
        assert record_path.read_text() == str(process.pid)
        monkeypatch.setenv("STORYGAL_DATA_DIR", str(data))
    launcher.main(["--no-open"])
    assert len(processes) == 1
    assert record_path.read_text() == str(process.pid)
    if location == "workspace_data":
        # A stale current-format record must not hide the verified legacy record.
        selected_record.write_bytes(selected_contents)
    launcher.main(["--stop"])
    process.wait(timeout=5)
    assert not record_path.exists()
    if location == "workspace_data":
        assert selected_record.read_bytes() == selected_contents


def test_real_occupied_port_and_data_lock_do_not_leave_new_processes(actual, monkeypatch):
    _, data, port, processes = actual
    launcher.main(["--no-open"])
    first = processes[0]
    monkeypatch.setenv("STORYGAL_PORT", str(port_number()))
    with pytest.raises(ValueError, match="启动失败"):
        launcher.main(["--no-open"])
    assert processes[-1].poll() is not None
    assert first.poll() is None
    assert len(list(data.glob("workbench-*.pid"))) == 1
    monkeypatch.setenv("STORYGAL_PORT", str(port))
    launcher.main(["--stop"])


def test_env_file_resolves_the_same_data_and_port(context, monkeypatch):
    from storygal.settings import load_env

    root, _, _, body = context
    monkeypatch.delenv("STORYGAL_DATA_DIR")
    monkeypatch.delenv("STORYGAL_PORT")
    (root / ".env").write_text('STORYGAL_DATA_DIR="nested data"\nSTORYGAL_PORT=18081\n')
    monkeypatch.setattr(launcher, "load_env", load_env)
    expected = launcher.identity(root, root / "nested data")
    seen = []

    def probe(base):
        seen.append(base)
        return {**body, **expected}

    monkeypatch.setattr(launcher, "health", probe)
    launcher.main(["--no-open"])
    assert seen == ["http://127.0.0.1:18081"]
    assert not (root / "data").exists()
