"""把维基文库 action=parse 返回的 JSON 转成样例 TXT。

用法：python3 -I wikisource_to_txt.py OUT.txt CH1.json [CH2.json ...]

规则（写进 PROVENANCE.md，改动时同步更新）：
- 回目取自页眉，写成「第X回　上联　下联」一行，回目内部的空格换成全角空格；
- 正文 <p> 原样保留段首全角空格，只去掉首尾的 ASCII 空白；
- 诗词 <dd> 每句一行，行首加四个全角空格；
- 页眉表格、样式、版权框不进正文；多回之间空一行；文件用 LF 换行、UTF-8 无 BOM。
"""

import hashlib
import json
import re
import sys
from html.parser import HTMLParser

ASCII_WS = " \t\r\n"
TITLE_RE = re.compile(r'<td style="width:70%; text-align:center">(第[^<]+?回)\s*<b>([^<]+)</b>')


class BodyExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []  # [kind, parts]
        self.lines = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "dd"):
            self.stack.append([tag, []])

    def handle_endtag(self, tag):
        if tag in ("p", "dd") and self.stack and self.stack[-1][0] == tag:
            kind, parts = self.stack.pop()
            text = "".join(parts).strip(ASCII_WS)
            if text:
                self.lines.append(text if kind == "p" else "　　　　" + text)

    def handle_data(self, data):
        if self.stack:
            self.stack[-1][1].append(data)


def chapter_lines(html):
    m = TITLE_RE.search(html)
    if not m:
        raise SystemExit("找不到回目")
    title = m.group(1) + "　" + "　".join(m.group(2).split())
    body = html.split('<div class="licenseContainer', 1)[0]
    body = re.sub(r"<table\b.*?</table>", "", body, flags=re.S)
    body = re.sub(r"<style\b.*?</style>", "", body, flags=re.S)
    ex = BodyExtractor()
    ex.feed(body)
    return [title] + ex.lines


def main(out_path, *json_paths):
    chunks = []
    for path in json_paths:
        parsed = json.load(open(path, encoding="utf-8"))["parse"]
        lines = chapter_lines(parsed["text"])
        chunks.append("\n".join(lines))
        print(f"{parsed['title']}  revid={parsed['revid']}  段落={len(lines) - 1}")
    text = "\n\n".join(chunks) + "\n"
    data = text.encode("utf-8")
    with open(out_path, "wb") as f:
        f.write(data)
    visible = sum(1 for ch in text if not ch.isspace())
    print(f"写入 {out_path}：{len(data)} 字节，非空白字符 {visible}")
    print(f"sha256 {hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    main(*sys.argv[1:])
