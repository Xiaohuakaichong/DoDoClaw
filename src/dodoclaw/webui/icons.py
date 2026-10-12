"""Runtime download + local cache for official Dota 2 hero/item icons.

Icons are NOT shipped with the app (Valve assets); they are fetched on first
use from Valve's CDN and cached under the user data dir. Failures return ""
so the UI can fall back to a text label.
"""

from __future__ import annotations

import base64
import logging
import re
import threading
import time
from pathlib import Path

from dodoclaw.paths import user_data_dir

logger = logging.getLogger(__name__)

CDN = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/{kind}/{key}.png"
KINDS = {"heroes", "items", "abilities"}
_KEY_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_FAIL_RETRY_SEC = 300


class IconCache:
    def __init__(self, root: Path | None = None, timeout: float = 5.0) -> None:
        self.root = root or (user_data_dir() / "icons")
        self.timeout = timeout
        self._failed: dict[str, float] = {}
        self._mem: dict[str, str] = {}
        self._lock = threading.Lock()

    @staticmethod
    def normalize(kind: str, key: str) -> tuple[str, str] | None:
        kind = (kind or "").strip().lower()
        key = (key or "").strip().lower()
        for prefix in ("npc_dota_hero_", "item_"):
            if key.startswith(prefix):
                key = key[len(prefix):]
        if kind not in KINDS or not _KEY_RE.match(key):
            return None
        return kind, key

    def path_for(self, kind: str, key: str) -> Path:
        return self.root / kind / f"{key}.png"

    def get_path(self, kind: str, key: str) -> Path | None:
        norm = self.normalize(kind, key)
        if not norm:
            return None
        kind, key = norm
        path = self.path_for(kind, key)
        if path.exists() and path.stat().st_size > 0:
            return path
        tag = f"{kind}/{key}"
        with self._lock:
            if time.time() - self._failed.get(tag, 0) < _FAIL_RETRY_SEC:
                return None
        try:
            import httpx

            r = httpx.get(
                CDN.format(kind=kind, key=key),
                timeout=self.timeout,
                headers={"User-Agent": "DoDoClaw-icons/0.1"},
                follow_redirects=True,
            )
            if r.status_code != 200 or not r.content.startswith(b"\x89PNG"):
                raise RuntimeError(f"HTTP {r.status_code}")
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(r.content)
            tmp.replace(path)
            return path
        except Exception as exc:
            logger.info("icon %s unavailable: %s", tag, exc)
            with self._lock:
                self._failed[tag] = time.time()
            return None

    def data_url(self, kind: str, key: str) -> str:
        norm = self.normalize(kind, key)
        if not norm:
            return ""
        tag = "/".join(norm)
        if tag in self._mem:
            return self._mem[tag]
        path = self.get_path(*norm)
        if not path:
            return ""
        url = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        self._mem[tag] = url
        return url
