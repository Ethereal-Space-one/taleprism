"""Start the local workbench independently of a terminal window; reuse a healthy instance."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    port = int(os.environ.get("STORYGAL_PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("端口应在 1–65535 之间。")
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    pidfile = data / f"workbench-{port}.pid"
    if args.stop:
        if not pidfile.exists():
            print("没有找到后台启动记录。前台启动的服务请在对应终端按 Control+C。")
            return
        pid = int(pidfile.read_text())
        command = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        if (
            str(ROOT / "backend/.venv/bin/python") in command
            and "uvicorn" in command
            and "storygal.app:app" in command
        ):
            os.kill(pid, signal.SIGTERM)
            print("Taleprism 已停止，项目与作品保留。")
        else:
            print("启动记录已失效，没有停止其他程序。")
        pidfile.unlink(missing_ok=True)
        return
    base = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def healthy():
        try:
            with opener.open(base + "/api/health", timeout=1) as response:
                body = json.load(response)
                return body.get("status") == "ok" and "engine_available" in body
        except (OSError, ValueError, urllib.error.URLError):
            return False

    if not healthy():
        python = ROOT / "backend/.venv/bin/python"
        if not python.is_file() or not (ROOT / "frontend/dist/index.html").is_file():
            raise ValueError("尚未完成首次准备，请先运行 start.sh。")
        with (data / "workbench.log").open("ab") as log:
            process = subprocess.Popen(
                [
                    str(python),
                    "-m",
                    "uvicorn",
                    "storygal.app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        for _ in range(60):
            if process.poll() is not None:
                raise ValueError(
                    "启动失败，请查看 data/workbench.log；端口或项目可能已经被其他服务占用。"
                )
            if healthy():
                pidfile.write_text(str(process.pid))
                break
            time.sleep(0.2)
        else:
            process.terminate()
            raise ValueError("启动超时，请查看 data/workbench.log。")
    print("Taleprism 已就绪：" + base)
    print("服务在后台运行，关闭此终端不会停止；需要退出时双击「停止Taleprism.command」。")
    if not args.no_open:
        webbrowser.open(base)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
