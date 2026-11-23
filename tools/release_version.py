"""Release filenames follow the application version in pyproject.toml."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "backend/pyproject.toml").read_text())["project"][
    "version"
]
PREFIX = "taleprism-v" + VERSION

# Historical book content and published filenames are not app version metadata.
BOOK_EDITION = "0.9.1"
FROZEN_BOOK_TAG = "v0.9.2"
FROZEN_BOOK_PREFIX = "taleprism-" + FROZEN_BOOK_TAG
