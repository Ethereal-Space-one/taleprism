"""Release filenames follow the application version in pyproject.toml."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "backend/pyproject.toml").read_text())["project"][
    "version"
]
PREFIX = "taleprism-v" + VERSION
