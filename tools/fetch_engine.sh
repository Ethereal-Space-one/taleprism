#!/usr/bin/env bash
# 下载固定版本的 WebGAL 网页版引擎（MPL-2.0），校验 SHA-256 后解压到 engine/webgal-<版本>/。
# 版本要和 tools/webgal-verify 里的 webgal-parser 保持一致。
set -euo pipefail

VERSION="4.6.5"
SHA256="30a6a446121482cb431950c4d0457ee48f4af9652ca81250fc3f5e244537ce1b"
URL="https://github.com/OpenWebGAL/WebGAL/releases/download/${VERSION}/WebGAL-${VERSION}-web.zip"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/engine/webgal-$VERSION"
if [ -f "$DEST/index.html" ]; then
  echo "已存在：$DEST"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fL --retry 3 -o "$TMP/engine.zip" "$URL"
echo "$SHA256  $TMP/engine.zip" | shasum -a 256 -c -
mkdir -p "$TMP/x"
unzip -q "$TMP/engine.zip" -d "$TMP/x"

# 发布包可能带一层顶级目录
SRC="$TMP/x"
if [ ! -f "$SRC/index.html" ]; then
  SRC="$(dirname "$(find "$TMP/x" -maxdepth 3 -name index.html | head -1)")"
fi
mkdir -p "$ROOT/engine"
mv "$SRC" "$DEST"
echo "已安装：$DEST"
