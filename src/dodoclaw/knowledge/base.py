"""Knowledge base: sync OpenDota hero mechanics + Valve patch notes, retrieve for coach."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from dodoclaw.knowledge.heroes import build_hero_documents
from dodoclaw.knowledge.patches import build_recent_patch_documents
from dodoclaw.knowledge.retriever import format_context, retrieve
from dodoclaw.paths import app_dir

logger = logging.getLogger(__name__)


class KnowledgeBase:
    def __init__(
        self,
        cache_dir: Path | None = None,
        *,
        language: str = "schinese",
        patch_last_n: int = 3,
        ttl_sec: int = 24 * 3600,
    ) -> None:
        self.cache_dir = cache_dir or (app_dir() / "data" / "knowledge")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.language = language
        self.patch_last_n = patch_last_n
        self.ttl_sec = ttl_sec
        self._docs: list[dict[str, Any]] = []
        self._loaded_at = 0.0

    @property
    def index_path(self) -> Path:
        return self.cache_dir / "index.json"

    def is_stale(self) -> bool:
        if not self.index_path.exists():
            return True
        try:
            age = time.time() - self.index_path.stat().st_mtime
            return age > self.ttl_sec
        except OSError:
            return True

    def load(self) -> int:
        if not self.index_path.exists():
            self._docs = []
            return 0
        raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        self._docs = list(raw.get("docs") or [])
        self._loaded_at = float(raw.get("updated_at") or 0)
        return len(self._docs)

    def save(self, docs: list[dict[str, Any]]) -> Path:
        payload = {
            "updated_at": time.time(),
            "language": self.language,
            "patch_last_n": self.patch_last_n,
            "count": len(docs),
            "docs": docs,
        }
        self.index_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        self._docs = docs
        self._loaded_at = payload["updated_at"]
        return self.index_path

    def sync(self, *, force: bool = False) -> dict[str, Any]:
        """Download/build hero + patch docs. Returns stats."""
        if not force and not self.is_stale() and self.load() > 0:
            return {
                "ok": True,
                "skipped": True,
                "count": len(self._docs),
                "path": str(self.index_path),
            }

        logger.info("Syncing knowledge base (heroes + patches)…")
        hero_docs = build_hero_documents()
        # heroes map for patch names
        heroes_by_id: dict[int, dict[str, Any]] = {}
        for d in hero_docs:
            hid = d.get("hero_id")
            if hid is not None:
                heroes_by_id[int(hid)] = {
                    "id": hid,
                    "name": d.get("hero_key"),
                    "localized_name": d.get("localized_name"),
                }

        patch_docs = build_recent_patch_documents(
            language=self.language,
            last_n=self.patch_last_n,
            heroes_by_id=heroes_by_id,
        )
        docs = hero_docs + patch_docs
        path = self.save(docs)
        return {
            "ok": True,
            "skipped": False,
            "heroes": len(hero_docs),
            "patches": len(patch_docs),
            "count": len(docs),
            "path": str(path),
        }

    def ensure_ready(self, *, auto_sync: bool = True) -> None:
        if self._docs:
            return
        n = self.load()
        if n > 0 and not self.is_stale():
            return
        if auto_sync:
            try:
                self.sync(force=self.is_stale() or n == 0)
            except Exception:
                logger.exception("knowledge auto-sync failed; using cached if any")
                if not self._docs:
                    self.load()

    def context_for(
        self,
        question: str,
        *,
        hero_keys: list[str] | None = None,
        top_k: int = 6,
        max_chars: int = 2800,
    ) -> str:
        self.ensure_ready(auto_sync=True)
        if not self._docs:
            return ""
        hits = retrieve(
            self._docs,
            question,
            hero_keys=hero_keys,
            top_k=top_k,
            max_chars=max_chars,
        )
        return format_context(hits)

    def stats(self) -> dict[str, Any]:
        self.load()
        kinds: dict[str, int] = {}
        for d in self._docs:
            k = str(d.get("kind") or "?")
            kinds[k] = kinds.get(k, 0) + 1
        return {
            "count": len(self._docs),
            "kinds": kinds,
            "path": str(self.index_path),
            "stale": self.is_stale(),
            "updated_at": self._loaded_at,
        }
