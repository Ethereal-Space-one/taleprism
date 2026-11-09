"""Read a local .env as data (never execute shell); process environment takes precedence."""

import os
import re
import shlex
from pathlib import Path


def load_env(path: Path):
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(
            r"\s*(STORYGAL_[A-Z0-9_]+|DEEPSEEK_API_KEY|OPENAI_API_KEY)\s*=\s*(.*?)\s*", line
        )
        if not match:
            continue
        values = shlex.split(match[2], comments=True)
        if len(values) <= 1:
            os.environ.setdefault(match[1], values[0] if values else "")
