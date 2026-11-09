#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v uv >/dev/null || { echo '需要 uv：https://docs.astral.sh/uv/getting-started/installation/'; exit 1; }
command -v node >/dev/null || { echo '需要 Node.js 20.19+ 或 22.12+。'; exit 1; }
uv sync --project backend --frozen
npm --prefix frontend ci --no-audit --no-fund
if [[ "${1:-}" == "--with-webgal" ]]; then
  npm --prefix tools/webgal-verify ci --no-audit --no-fund
  bash tools/fetch_engine.sh
fi
npm --prefix frontend run build
exec bash ./run.sh
