#!/bin/bash
# Finder entry point for an extracted standalone reader, not the workbench.
set -u
fail() {
  printf '\nTaleprism 阅读器 / Reader: %s\n' "$1" >&2
  if [ -t 0 ]; then
    printf '按回车关闭窗口 / Press Return to close. '
    read -r _
  fi
  exit 1
}
ROOT="$(CDPATH= cd -P "$(dirname "$0")" 2>/dev/null && pwd)" ||
  fail '无法找到阅读包目录。请完整解压 ZIP 后再双击。 / Extract the entire ZIP first.'
cd "$ROOT" || fail '阅读包路径不可访问。 / The extracted reader folder is not accessible.'
[ -f "$ROOT/reader_launcher.py" ] ||
  fail '缺少 reader_launcher.py。请重新完整解压阅读器 ZIP，不要只移动 .command 文件。 / Re-extract the entire reader ZIP; keep the launcher beside reader_launcher.py.'
PYTHON=''
# Finder has a small PATH. Try common existing Python locations, without installing anything.
for candidate in "$(command -v python3 2>/dev/null || true)" \
  /opt/homebrew/bin/python3 /usr/local/bin/python3 \
  /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/bin/python3; do
  [ -n "$candidate" ] && [ -x "$candidate" ] || continue
  # macOS's unconfigured developer-tools stub can open an installation dialog.
  if [ "$candidate" = /usr/bin/python3 ] && [ "$(uname -s)" = Darwin ]; then
    /usr/bin/xcode-select -p >/dev/null 2>&1 || continue
  fi
  if "$candidate" -I -B -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
[ -n "$PYTHON" ] ||
  fail '需要现有的 Python 3.9+。本启动器不会安装软件。请先准备 Python 3.9+（python.org），或请提供者托管阅读器网页，再重新双击。 / Python 3.9+ is required. Nothing was installed; use an existing Python or request a hosted reader.'
case "${0##*/}" in
  停止阅读器.command) "$PYTHON" -I -B "$ROOT/reader_launcher.py" --stop ;;
  *) "$PYTHON" -I -B "$ROOT/reader_launcher.py" ;;
esac
STATUS=$?
[ "$STATUS" -eq 0 ] || fail '启动操作未完成。请按上方原因处理后重试。 / See the error above, correct it, then try again.'
