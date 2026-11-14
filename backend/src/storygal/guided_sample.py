"""One fixed, hash-pinned public tutorial. No provider credentials or user uploads."""

import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from .exporter import REPO

ARCHIVE_FILE = "taleprism-v0.3.0-last-light-project.zip"
ARCHIVE_URL = (
    "https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.3.0/" + ARCHIVE_FILE
)
ARCHIVE_SHA256 = "e556e026b7d8a5763250623d74b6329d2b40892744b26f04861f1ae4e1682f4e"
MAX_ARCHIVE_BYTES = 25_000_000
DOWNLOAD_SECONDS = 45
MAX_REDIRECTS = 3
ASSET_HOSTS = {"release-assets.githubusercontent.com", "objects.githubusercontent.com"}
FALLBACK = "可重试，或展开「手动导入与原文练习」下载公开工程后导入。已有项目未改动。"


def _spec():
    """The catalog is descriptive, not an arbitrary URL or file-fetch capability."""
    try:
        catalog = json.loads((REPO / "samples/content-packs/catalog.json").read_text())
        spec = next(s for s in catalog if s["id"] == "last-light")
        if (
            spec["file"] != ARCHIVE_FILE
            or spec["download_url"] != ARCHIVE_URL
            or spec["sha256"] != ARCHIVE_SHA256
        ):
            raise ValueError("pinned sample changed")
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        raise ValueError(
            "引导样例目录与固定公开版本不一致，请更新程序后重试。" + FALLBACK
        ) from None
    return spec


def _checked(path: Path):
    try:
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_ARCHIVE_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) <= MAX_ARCHIVE_BYTES and hashlib.sha256(raw).hexdigest() == ARCHIVE_SHA256:
        return raw
    return None


def _asset_redirect(url):
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in ASSET_HOSTS
            and parsed.port in {None, 443}
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
        )
    except ValueError:
        return False


def _download():
    """Only GitHub's fixed release and bounded HTTPS asset redirects are reachable."""
    deadline = time.monotonic() + DOWNLOAD_SECONDS
    url = ARCHIVE_URL
    try:
        with httpx.Client(
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(10, connect=8),
            headers={"User-Agent": "Taleprism-public-sample/0.3.0", "Accept-Encoding": "identity"},
        ) as client:
            for hop in range(MAX_REDIRECTS + 1):
                if time.monotonic() >= deadline:
                    raise ValueError("公开样例下载超时。" + FALLBACK)
                with client.stream("GET", url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        target = urljoin(url, response.headers.get("location", ""))
                        if hop == MAX_REDIRECTS or not _asset_redirect(target):
                            raise ValueError("公开样例下载重定向不符合固定来源限制。" + FALLBACK)
                        url = target
                        continue
                    response.raise_for_status()
                    length = response.headers.get("content-length")
                    if length and (not length.isdigit() or int(length) > MAX_ARCHIVE_BYTES):
                        raise ValueError("公开样例下载大小超过限制。" + FALLBACK)
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline:
                            raise ValueError("公开样例下载超时。" + FALLBACK)
                        if len(raw) + len(chunk) > MAX_ARCHIVE_BYTES:
                            raise ValueError("公开样例下载大小超过限制。" + FALLBACK)
                        raw.extend(chunk)
                    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
                        raise ValueError("公开样例校验未通过，未创建项目。" + FALLBACK)
                    return bytes(raw)
    except httpx.HTTPError:
        # Never surface transport details or signed asset URLs in the UI.
        raise ValueError("暂时无法获取公开样例，网络或发布服务不可用。" + FALLBACK) from None
    raise ValueError("公开样例下载未完成。" + FALLBACK)


def mount_guided_sample(app):
    lock = threading.Lock()
    cache_dir = app.state.store.root / "sample-cache"
    cache_path = cache_dir / f"last-light-{ARCHIVE_SHA256}.zip"

    @app.get("/api/samples/last-light/guided")
    def status():
        spec = _spec()
        return {
            "title": spec["title"],
            "download_url": ARCHIVE_URL,
            "sha256": ARCHIVE_SHA256,
            "cached": bool(
                _checked(cache_path) or _checked(REPO / "samples/content-packs" / ARCHIVE_FILE)
            ),
            "requires_api_key": False,
            "download_limit_bytes": MAX_ARCHIVE_BYTES,
        }

    @app.post("/api/samples/last-light/guided", status_code=201)
    def open_sample():
        _spec()
        with lock:
            raw = _checked(cache_path) or _checked(REPO / "samples/content-packs" / ARCHIVE_FILE)
            if raw is None:
                raw = _download()
                try:
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    with tempfile.NamedTemporaryFile(
                        dir=cache_dir, suffix=".part", delete=False
                    ) as f:
                        temporary = Path(f.name)
                        try:
                            f.write(raw)
                            f.flush()
                            os.fsync(f.fileno())
                            os.replace(temporary, cache_path)
                        finally:
                            temporary.unlink(missing_ok=True)
                except OSError:
                    # A read-only cache must not prevent using already-verified bytes.
                    pass
            # Existing importer validates all contents and atomically publishes a new project.
            project = app.state.bundles.import_project(raw)
            return project | {"guided_sample": "last-light", "guided_shot_id": "negotiation"}
