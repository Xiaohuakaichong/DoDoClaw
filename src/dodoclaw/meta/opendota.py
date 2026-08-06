"""OpenDota meta client — public REST API, rank brackets 1–8, no lane meta."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from dodoclaw.meta.base import HeroMeta, MetaSnapshot
from dodoclaw.paths import app_dir

logger = logging.getLogger(__name__)

OPENDOTA_BASE = "https://api.opendota.com/api"


class OpenDotaClient:
    source_name = "opendota"

    def __init__(
        self,
        api_key: str = "",
        cache_ttl_sec: int = 6 * 3600,
        cache_dir: Path | None = None,
        # bracket 0 = all (sum 1-8); 1-8 = single OpenDota bracket
        bracket: int = 0,
    ) -> None:
        self.api_key = api_key.strip()
        self.cache_ttl_sec = cache_ttl_sec
        self.cache_dir = cache_dir or (app_dir() / "data" / "meta" / "opendota")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.bracket = int(bracket or 0)
        self._meta: MetaSnapshot | None = None
        self._matchups_cache: dict[int, list[dict[str, Any]]] = {}

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": "DoDoClaw/0.1 (Dota2 voice coach; opendota)"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        params = dict(params or {})
        if self.api_key:
            params["api_key"] = self.api_key
        url = f"{OPENDOTA_BASE}{path}"
        with httpx.Client(timeout=30.0, headers=self._headers()) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            return r.json()

    def _cache_path(self, name: str) -> Path:
        return self.cache_dir / name

    def _load_cache(self, name: str) -> Any | None:
        path = self._cache_path(name)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(raw.get("_cached_at", 0)) > self.cache_ttl_sec:
                return None
            return raw.get("data")
        except Exception:
            return None

    def _save_cache(self, name: str, data: Any) -> None:
        path = self._cache_path(name)
        path.write_text(
            json.dumps({"_cached_at": time.time(), "data": data}, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_meta(self, force: bool = False) -> MetaSnapshot:
        if self._meta and not force:
            age = time.time() - self._meta.updated_at
            if age < self.cache_ttl_sec:
                return self._meta

        rows = None if force else self._load_cache("hero_stats.json")
        if rows is None:
            logger.info("Fetching OpenDota /heroStats …")
            rows = self._get("/heroStats")
            self._save_cache("hero_stats.json", rows)

        snap = MetaSnapshot(
            updated_at=time.time(),
            source="opendota",
            note=f"段位括号={self.bracket or '全部1-8合计'}（OpenDota 无分路聚合）",
        )
        total_picks = 0
        for row in rows:
            if self.bracket and 1 <= self.bracket <= 8:
                picks = int(row.get(f"{self.bracket}_pick") or 0)
                wins = int(row.get(f"{self.bracket}_win") or 0)
            else:
                picks = 0
                wins = 0
                for b in range(1, 9):
                    picks += int(row.get(f"{b}_pick") or 0)
                    wins += int(row.get(f"{b}_win") or 0)
            hm = HeroMeta(
                hero_id=int(row["id"]),
                name=str(row.get("name") or ""),
                localized_name=str(row.get("localized_name") or ""),
                roles=list(row.get("roles") or []),
                primary_attr=str(row.get("primary_attr") or ""),
                picks=picks,
                wins=wins,
                pro_pick=int(row.get("pro_pick") or 0),
                pro_ban=int(row.get("pro_ban") or 0),
                pro_win=int(row.get("pro_win") or 0),
                source="opendota",
            )
            total_picks += picks
            snap.heroes[hm.hero_id] = hm
            if hm.name:
                snap.by_name[hm.name.lower()] = hm
            if hm.localized_name:
                snap.by_localized[hm.localized_name.lower()] = hm

        if total_picks:
            for hm in snap.heroes.values():
                hm._pick_share = hm.picks / total_picks  # type: ignore[attr-defined]

        self._meta = snap
        return snap

    def get_matchups(self, hero_id: int, force: bool = False) -> list[dict[str, Any]]:
        if not force and hero_id in self._matchups_cache:
            return self._matchups_cache[hero_id]
        cache_name = f"matchups_{hero_id}.json"
        rows = None if force else self._load_cache(cache_name)
        if rows is None:
            try:
                rows = self._get(f"/heroes/{hero_id}/matchups")
                self._save_cache(cache_name, rows)
            except Exception:
                logger.exception("matchups fetch failed for %s", hero_id)
                rows = []
        self._matchups_cache[hero_id] = rows
        return rows

    def top_bans(self, n: int = 15, use_pro: bool = True) -> list[HeroMeta]:
        meta = self.get_meta()
        heroes = list(meta.heroes.values())
        if use_pro:
            heroes.sort(key=lambda h: h.pro_ban, reverse=True)
        else:
            heroes.sort(
                key=lambda h: (h.win_rate * 0.6 + h.pick_rate_share * 40), reverse=True
            )
        return heroes[:n]

    def top_picks(self, n: int = 20, use_pro: bool = False) -> list[HeroMeta]:
        meta = self.get_meta()
        heroes = list(meta.heroes.values())
        if use_pro:
            heroes.sort(key=lambda h: h.pro_pick, reverse=True)
        else:
            heroes.sort(key=lambda h: h.picks, reverse=True)
        return heroes[:n]

    def counters_for(self, enemy_hero_id: int, n: int = 8) -> list[tuple[HeroMeta, float]]:
        meta = self.get_meta()
        rows = self.get_matchups(enemy_hero_id)
        scored: list[tuple[HeroMeta, float, int]] = []
        for row in rows:
            hid = int(row.get("hero_id") or 0)
            games = int(row.get("games_played") or 0)
            wins = int(row.get("wins") or 0)
            if games < 50 or hid not in meta.heroes:
                continue
            enemy_wr = wins / games
            counter_score = 1.0 - enemy_wr
            scored.append((meta.heroes[hid], counter_score, games))
        scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return [(h, s) for h, s, _ in scored[:n]]

    def top_by_position(self, position: str, n: int = 10) -> list[HeroMeta]:
        # OpenDota has no position meta; approximate via role tags
        meta = self.get_meta()
        pos = (position or "").upper()
        role_map = {
            "POSITION_1": ("Carry",),
            "POSITION_2": ("Nuker", "Escape", "Carry"),
            "POSITION_3": ("Initiator", "Durable", "Disabler"),
            "POSITION_4": ("Support", "Disabler", "Nuker"),
            "POSITION_5": ("Support", "Disabler"),
            "1": ("Carry",),
            "2": ("Nuker", "Escape"),
            "3": ("Initiator", "Durable"),
            "4": ("Support",),
            "5": ("Support",),
        }
        want = role_map.get(pos) or role_map.get(position) or ()
        heroes = list(meta.heroes.values())
        if want:
            heroes = [h for h in heroes if any(r in h.roles for r in want)]
        heroes.sort(key=lambda h: h.picks, reverse=True)
        return heroes[:n]
