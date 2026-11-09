#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x backend/.venv/bin/python || ! -f frontend/dist/index.html ]]; then
  echo '尚未完成首次准备，请先运行 ./start.sh。'
  exit 1
fi
command -v node >/dev/null || { echo '需要 Node.js 20.19+ 或 22.12+。'; exit 1; }
echo "Taleprism：打开 http://127.0.0.1:${STORYGAL_PORT:-8000}"
echo '关闭此终端会停止工作台；项目和已导出工程仍保留在本机。'
exec backend/.venv/bin/python -m uvicorn storygal.app:app --host 127.0.0.1 --port "${STORYGAL_PORT:-8000}"
