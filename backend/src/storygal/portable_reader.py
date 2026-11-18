"""The extracted and hosted reader use the same published data, not a second rendering."""

import json

DATA_TAG = '<script id="taleprism-story" type="application/json">'
TEMPLATE = (
    """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="theme-color" content="#202329">
  <meta name="storygal-reader-export" content="./reader.json">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self' file:; style-src 'self' file: 'unsafe-inline'; img-src 'self' file: data:; media-src 'self' file:; connect-src 'none'; base-uri 'none'; form-action 'none'">
  <title>Taleprism · 独立阅读器</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="./assets/reader.css">
</head>
<body>
  <div id="root"><p>正在打开阅读器…</p>
    <p>若未打开，请完整解压 ZIP，保留 assets 与 media 文件夹，并用桌面浏览器打开 index.html。不要在压缩包或邮件预览中打开。</p>
    <p>If the reader does not open, extract the entire ZIP, keep the assets and media folders together, and open index.html in a desktop browser rather than a ZIP or email preview.</p>
    <noscript>阅读器需要浏览器启用 JavaScript。 / This reader requires JavaScript.</noscript>
  </div>
  """
    + DATA_TAG
    + """</script>
  <script src="./assets/reader.js"></script>
</body>
</html>
"""
)


def embed_story(html, content, previous=None):
    """Replace the single inert payload. Never interpolate story text into executable JS."""
    if html.count(DATA_TAG) != 1:
        raise ValueError("离线阅读页的数据区无效。")
    start = html.index(DATA_TAG) + len(DATA_TAG)
    end = html.index("</script>", start)
    if previous is not None and json.loads(html[start:end]) != previous:
        raise ValueError("离线阅读页与 reader.json 内容不一致。")
    # HTML raw-text parsing ends at a case-insensitive </script (even inside a
    # JSON string). Escaping every '<' preserves original story text and bytes.
    payload = json.dumps(content, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return html[:start] + payload + html[end:]
