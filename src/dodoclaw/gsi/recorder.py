"""Optional raw GSI payload recorder (JSONL, one file per match).

Enable with GSI_RECORD=1 in .env. Files go to <app_dir>/logs/gsi/.
Auth token is stripped before writing.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GsiRecorder:
    def __init__(self, out_dir: Path, max_bytes_per_file: int = 50 * 1024 * 1024) -> None:
        self.out_dir = out_dir
        self.max_bytes = max_bytes_per_file
        self._lock = threading.Lock()
        self._fh = None
        self._match_id: str | None = None
        self._written = 0

    def _open_for(self, match_id: str) -> None:
        self.close()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        name = f"{stamp}_{match_id or 'nomatch'}.jsonl"
        self._fh = (self.out_dir / name).open("a", encoding="utf-8")
        self._match_id = match_id
        self._written = 0
        logger.info("GSI recording -> %s", self.out_dir / name)

    def record(self, payload: dict[str, Any]) -> None:
        try:
            data = dict(payload)
            data.pop("auth", None)
            match_id = str((data.get("map") or {}).get("matchid") or "")
            line = json.dumps({"t": time.time(), "p": data}, ensure_ascii=False) + "\n"
            with self._lock:
                if self._fh is None or match_id != self._match_id:
                    self._open_for(match_id)
                if self._written + len(line) > self.max_bytes:
                    return
                self._fh.write(line)
                self._fh.flush()
                self._written += len(line)
        except Exception:
            logger.exception("GSI record failed")

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
