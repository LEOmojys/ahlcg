"""Card image cache.

ArkhamDB publishes one image per card; the card database records the relative
path in the imagesrc field, so the absolute URL is https://arkhamdb.com plus
that path.  Images are cached on disk at assets/cards/{code}.png so the game is
playable without a network connection once a card has been seen.

Everything network related is injectable: CardImageStore takes a fetch callable
and an enabled flag, which is what the tests use to stay offline.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

#: repository root / assets / cards
DEFAULT_DIRECTORY = Path(__file__).resolve().parents[2] / "assets" / "cards"

ARKHAMDB_BASE = "https://arkhamdb.com"

#: how long a failed download is remembered before it is retried
FAILURE_TTL_SECONDS = 300.0

FetchImage = Callable[[str], bytes]


def download_image(url: str, timeout: float = 8.0) -> bytes:
    """Download one card image.  Raises on any network or HTTP failure."""
    request = Request(url, headers={"User-Agent": "ahlcg-web/0.1 (local rules engine)"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https base
        return response.read()


def sniff_media_type(data: bytes) -> str:
    """Guess the image media type from the magic bytes."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/png"


class CardImageStore:
    """Disk cache of card images."""

    def __init__(
        self,
        directory: str | Path = DEFAULT_DIRECTORY,
        *,
        fetch: FetchImage | None = None,
        enabled: bool = True,
        timeout: float = 8.0,
    ) -> None:
        self.directory = Path(directory)
        self.timeout = timeout
        self.enabled = bool(enabled)
        self._fetch: FetchImage | None = fetch or self._default_fetch
        self._lock = threading.Lock()
        self._failures: dict[str, float] = {}
        self._downloads = 0

    # -- configuration --------------------------------------------------
    def _default_fetch(self, url: str) -> bytes:
        return download_image(url, timeout=self.timeout)

    def source_url(self, imagesrc: str) -> str:
        if imagesrc.startswith("http://") or imagesrc.startswith("https://"):
            return imagesrc
        return f"{ARKHAMDB_BASE}{imagesrc}"

    def path_for(self, code: str) -> Path:
        return self.directory / f"{code}.png"

    # -- cache ----------------------------------------------------------
    def cached(self, code: str) -> Path | None:
        path = self.path_for(code)
        try:
            if path.is_file() and path.stat().st_size > 0:
                return path
        except OSError:
            return None
        return None

    def media_type(self, path: Path) -> str:
        try:
            with open(path, "rb") as handle:
                return sniff_media_type(handle.read(16))
        except OSError:
            return "image/png"

    def recently_failed(self, code: str) -> bool:
        stamp = self._failures.get(code)
        if stamp is None:
            return False
        if time.monotonic() - stamp > FAILURE_TTL_SECONDS:
            del self._failures[code]
            return False
        return True

    def note_failure(self, code: str) -> None:
        self._failures[code] = time.monotonic()

    @property
    def download_count(self) -> int:
        return self._downloads

    def ensure(self, code: str, imagesrc: str | None) -> Path | None:
        """Return the cached image, downloading it once when possible."""
        cached = self.cached(code)
        if cached is not None:
            return cached
        if not self.enabled or self._fetch is None or not imagesrc:
            return None
        if self.recently_failed(code):
            return None
        with self._lock:
            cached = self.cached(code)
            if cached is not None:
                return cached
            if self.recently_failed(code):
                return None
            try:
                data = self._fetch(self.source_url(imagesrc))
            except Exception:
                self.note_failure(code)
                return None
            if not data:
                self.note_failure(code)
                return None
            self._downloads += 1
            return self._write(code, data)

    def _write(self, code: str, data: bytes) -> Path | None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.path_for(code)
            temporary = path.with_name(path.name + ".part")
            temporary.write_bytes(data)
            temporary.replace(path)
            return path
        except OSError:
            self.note_failure(code)
            return None


def store_from_environment(**kwargs) -> CardImageStore:
    """Build the store used by the real server (images can be disabled)."""
    import os

    enabled = os.environ.get("AHLCG_WEB_IMAGES", "1") not in ("0", "false", "False")
    return CardImageStore(enabled=enabled, **kwargs)
