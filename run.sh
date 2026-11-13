#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x backend/.venv/bin/python || ! -f frontend/dist/index.html ]]; then
  echo '尚未完成首次准备，请先运行 ./start.sh。'
  exit 1
fi
command -v node >/dev/null || { echo '需要 Node.js 20.19+ 或 22.12+。'; exit 1; }
exec backend/.venv/bin/python tools/open_workbench.py --foreground --no-open
