"""
STRATZ GraphQL meta client.

- API is free with user token: https://stratz.com/api
- Headers: Authorization: Bearer <token>, User-Agent: STRATZ_API
- Supports bracket + position filters (finer than OpenDota aggregates)

Users should register their own token when traffic grows.
"""

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

STRATZ_GQL = "https://api.stratz.com/graphql"

# Common STRATZ enums (may evolve; we send as strings)
BRACKET_PRESETS: dict[str, list[str]] = {
    "all": [],
    "low": ["HERALD_GUARDIAN", "CRUSADER_ARCHON"],
    "mid": ["LEGEND_ANCIENT"],
    "high": ["DIVINE_IMMORTAL"],
    "divine_immortal": ["DIVINE_IMMORTAL"],
    "legend_ancient": ["LEGEND_ANCIENT"],
    "crusader_archon": ["CRUSADER_ARCHON"],
    "herald_guardian": ["HERALD_GUARDIAN"],
}

POSITIONS = (
    "POSITION_1",
    "POSITION_2",
    "POSITION_3",
    "POSITION_4",
    "POSITION_5",
)

# Fallback if schema uses RankBracketBasicEnum differently
BRACKET_BASIC_FALLBACK: dict[str, list[str]] = {
    "low": ["CRUSADER_ARCHON"],
    "mid": ["LEGEND_ANCIENT"],
    "high": ["DIVINE_IMMORTAL"],
    "all": [],
}


class StratzClient:
    source_name = "stratz"

    def __init__(
        self,
        api_token: str,
        cache_ttl_sec: int = 6 * 3600,
        cache_dir: Path | None = None,
        bracket: str = "high",
        # which positions to prefetch for BP advice
        positions: list[str] | None = None,
    ) -> None:
        token = (api_token or "").strip()
        if not token:
            raise ValueError(
                "STRATZ 需要 API Token。请登录 https://stratz.com/api 获取后，"
                "在设置中填写 STRATZ_API_TOKEN。"
            )
        self.api_token = token
        self.cache_ttl_sec = cache_ttl_sec
        self.cache_dir = cache_dir or (app_dir() / "data" / "meta" / "stratz")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.bracket = (bracket or "high").lower()
        self.positions = positions or list(POSITIONS)
        self._meta: MetaSnapshot | None = None
        self._constants_heroes: dict[int, dict[str, Any]] = {}
        self._matchups_cache: dict[int, list[dict[str, Any]]] = {}

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "User-Agent": "STRATZ_API",
            "Authorization": f"Bearer {self.api_token}",
        }

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        with httpx.Client(timeout=45.0, headers=self._headers()) as client:
            r = client.post(STRATZ_GQL, json=payload)
            if r.status_code == 401:
                raise RuntimeError("STRATZ Token 无效或已过期，请重新在 stratz.com/api 获取。")
            if r.status_code == 403:
                raise RuntimeError(
                    "STRATZ 拒绝请求（403）。请确认 Token 有效且 Header 含 User-Agent: STRATZ_API。"
                )
            r.raise_for_status()
            body = r.json()
        if body.get("errors"):
            msgs = "; ".join(
                e.get("message", str(e)) for e in body["errors"] if isinstance(e, dict)
            )
            raise RuntimeError(f"STRATZ GraphQL 错误: {msgs}")
        return body.get("data") or {}

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
        self._cache_path(name).write_text(
            json.dumps({"_cached_at": time.time(), "data": data}, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_constants(self, force: bool = False) -> dict[int, dict[str, Any]]:
        if self._constants_heroes and not force:
            return self._constants_heroes
        cached = None if force else self._load_cache("constants_heroes.json")
        if cached is not None:
            self._constants_heroes = {int(k): v for k, v in cached.items()}
            return self._constants_heroes

        query = """
        query {
          constants {
            heroes {
              id
              name
              displayName
              shortName
            }
          }
        }
        """
        data = self.graphql(query)
        heroes = ((data.get("constants") or {}).get("heroes")) or []
        out: dict[int, dict[str, Any]] = {}
        for h in heroes:
            hid = int(h["id"])
            out[hid] = h
        self._constants_heroes = out
        self._save_cache(
            "constants_heroes.json", {str(k): v for k, v in out.items()}
        )
        return out

    def _bracket_ids(self) -> list[str]:
        return list(BRACKET_PRESETS.get(self.bracket, BRACKET_PRESETS["high"]))

    def _fetch_win_rows(
        self, position: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Try a few GraphQL shapes; STRATZ schema evolves.
        Prefer heroStats.winWeek with bracket + position filters.
        """
        bracket_ids = self._bracket_ids()
        pos_list = [position] if position else []

        # Query A: winWeek + bracketIds + positionIds
        q_a = """
        query($take: Int, $brackets: [RankBracket], $positions: [MatchPlayerPositionType]) {
          heroStats {
            winWeek(take: $take, bracketIds: $brackets, positionIds: $positions) {
              heroId
              matchCount
              winCount
            }
          }
        }
        """
        # Query B: bracketBasicIds variant
        q_b = """
        query($take: Int, $brackets: [RankBracketBasicEnum], $positions: [MatchPlayerPositionType]) {
          heroStats {
            winWeek(take: $take, bracketBasicIds: $brackets, positionIds: $positions) {
              heroId
              matchCount
              winCount
            }
          }
        }
        """
        # Query C: no filters
        q_c = """
        query($take: Int) {
          heroStats {
            winWeek(take: $take) {
              heroId
              matchCount
              winCount
            }
          }
        }
        """

        attempts: list[tuple[str, dict[str, Any]]] = []
        if bracket_ids and pos_list:
            attempts.append(
                (q_a, {"take": 200, "brackets": bracket_ids, "positions": pos_list})
            )
            attempts.append(
                (
                    q_b,
                    {
                        "take": 200,
                        "brackets": BRACKET_BASIC_FALLBACK.get(self.bracket, bracket_ids),
                        "positions": pos_list,
                    },
                )
            )
        if bracket_ids:
            attempts.append((q_a, {"take": 200, "brackets": bracket_ids, "positions": []}))
            attempts.append(
                (
                    q_b,
                    {
                        "take": 200,
                        "brackets": BRACKET_BASIC_FALLBACK.get(self.bracket, bracket_ids),
                        "positions": [],
                    },
                )
            )
        if pos_list:
            attempts.append((q_a, {"take": 200, "brackets": [], "positions": pos_list}))
        attempts.append((q_c, {"take": 200}))

        last_err: Exception | None = None
        for q, variables in attempts:
            try:
                data = self.graphql(q, variables)
                rows = ((data.get("heroStats") or {}).get("winWeek")) or []
                if rows:
                    return rows
            except Exception as exc:
                last_err = exc
                logger.debug("STRATZ query attempt failed: %s", exc)
                continue
        if last_err:
            raise last_err
        return []

    def get_meta(self, force: bool = False) -> MetaSnapshot:
        if self._meta and not force:
            if time.time() - self._meta.updated_at < self.cache_ttl_sec:
                return self._meta

        cache_key = f"meta_{self.bracket}.json"
        cached = None if force else self._load_cache(cache_key)
        constants = self._load_constants(force=force)

        if cached and isinstance(cached, dict) and cached.get("heroes"):
            snap = self._snapshot_from_cached(cached, constants)
            self._meta = snap
            return snap

        # Overall (no position)
        overall_rows = self._fetch_win_rows(position=None)
        by_pos_rows: dict[str, list[dict[str, Any]]] = {}
        for pos in self.positions:
            try:
                by_pos_rows[pos] = self._fetch_win_rows(position=pos)
            except Exception:
                logger.exception("STRATZ position %s failed", pos)
                by_pos_rows[pos] = []

        snap = MetaSnapshot(
            updated_at=time.time(),
            source="stratz",
            note=(
                f"STRATZ · bracket={self.bracket} · "
                f"positions={','.join(self.positions)} · Data by STRATZ"
            ),
        )
        total_picks = 0
        for row in overall_rows:
            hid = int(row.get("heroId") or row.get("hero_id") or 0)
            if not hid:
                continue
            c = constants.get(hid) or {}
            picks = int(row.get("matchCount") or row.get("match_count") or 0)
            wins = int(row.get("winCount") or row.get("win_count") or 0)
            name = str(c.get("name") or f"hero_{hid}")
            loc = str(c.get("displayName") or c.get("shortName") or name)
            hm = HeroMeta(
                hero_id=hid,
                name=name if name.startswith("npc_") else f"npc_dota_hero_{name}",
                localized_name=loc,
                picks=picks,
                wins=wins,
                # STRATZ free queries often lack pro_ban in this endpoint;
                # use pick volume as ban proxy later if needed
                pro_pick=picks,
                pro_ban=0,
                pro_win=wins,
                bracket=self.bracket,
                source="stratz",
            )
            total_picks += picks
            snap.heroes[hid] = hm
            snap.by_name[hm.name.lower()] = hm
            snap.by_localized[hm.localized_name.lower()] = hm

        if total_picks:
            for hm in snap.heroes.values():
                hm._pick_share = hm.picks / total_picks  # type: ignore[attr-defined]

        for pos, rows in by_pos_rows.items():
            ranked: list[HeroMeta] = []
            for row in rows:
                hid = int(row.get("heroId") or 0)
                if not hid:
                    continue
                base = snap.heroes.get(hid)
                c = constants.get(hid) or {}
                picks = int(row.get("matchCount") or 0)
                wins = int(row.get("winCount") or 0)
                loc = (
                    (base.localized_name if base else None)
                    or c.get("displayName")
                    or str(hid)
                )
                name = (base.name if base else None) or str(c.get("name") or hid)
                ranked.append(
                    HeroMeta(
                        hero_id=hid,
                        name=name,
                        localized_name=str(loc),
                        picks=picks,
                        wins=wins,
                        position=pos,
                        bracket=self.bracket,
                        source="stratz",
                    )
                )
            ranked.sort(key=lambda h: (h.picks, h.win_rate), reverse=True)
            snap.by_position[pos] = ranked

        # persist light cache
        self._save_cache(
            cache_key,
            {
                "heroes": {
                    str(hid): {
                        "hero_id": h.hero_id,
                        "name": h.name,
                        "localized_name": h.localized_name,
                        "picks": h.picks,
                        "wins": h.wins,
                    }
                    for hid, h in snap.heroes.items()
                },
                "by_position": {
                    pos: [
                        {
                            "hero_id": h.hero_id,
                            "name": h.name,
                            "localized_name": h.localized_name,
                            "picks": h.picks,
                            "wins": h.wins,
                            "position": pos,
                        }
                        for h in lst[:30]
                    ]
                    for pos, lst in snap.by_position.items()
                },
                "note": snap.note,
            },
        )
        self._meta = snap
        return snap

    def _snapshot_from_cached(
        self, cached: dict[str, Any], constants: dict[int, dict[str, Any]]
    ) -> MetaSnapshot:
        snap = MetaSnapshot(
            updated_at=time.time(),
            source="stratz",
            note=str(cached.get("note") or "STRATZ (cache)"),
        )
        total = 0
        for _k, raw in (cached.get("heroes") or {}).items():
            hm = HeroMeta(
                hero_id=int(raw["hero_id"]),
                name=str(raw.get("name") or ""),
                localized_name=str(raw.get("localized_name") or ""),
                picks=int(raw.get("picks") or 0),
                wins=int(raw.get("wins") or 0),
                source="stratz",
                bracket=self.bracket,
            )
            total += hm.picks
            snap.heroes[hm.hero_id] = hm
            if hm.name:
                snap.by_name[hm.name.lower()] = hm
            if hm.localized_name:
                snap.by_localized[hm.localized_name.lower()] = hm
        if total:
            for hm in snap.heroes.values():
                hm._pick_share = hm.picks / total  # type: ignore[attr-defined]
        for pos, rows in (cached.get("by_position") or {}).items():
            snap.by_position[pos] = [
                HeroMeta(
                    hero_id=int(r["hero_id"]),
                    name=str(r.get("name") or ""),
                    localized_name=str(r.get("localized_name") or ""),
                    picks=int(r.get("picks") or 0),
                    wins=int(r.get("wins") or 0),
                    position=pos,
                    source="stratz",
                )
                for r in rows
            ]
        return snap

    def get_matchups(self, hero_id: int, force: bool = False) -> list[dict[str, Any]]:
        """
        STRATZ hero matchup-style data when available.
        Falls back to empty → DraftAdvisor can still use position meta.
        """
        if not force and hero_id in self._matchups_cache:
            return self._matchups_cache[hero_id]
        cache_name = f"matchups_{hero_id}.json"
        cached = None if force else self._load_cache(cache_name)
        if cached is not None:
            self._matchups_cache[hero_id] = cached
            return cached

        # Best-effort query; schema may differ
        query = """
        query($heroId: Short!) {
          heroStats {
            matchUp(heroId: $heroId, take: 50) {
              heroId2
              matchCount
              winCount
            }
          }
        }
        """
        rows: list[dict[str, Any]] = []
        try:
            data = self.graphql(query, {"heroId": hero_id})
            raw = ((data.get("heroStats") or {}).get("matchUp")) or []
            for r in raw:
                games = int(r.get("matchCount") or 0)
                wins = int(r.get("winCount") or 0)
                rows.append(
                    {
                        "hero_id": int(r.get("heroId2") or 0),
                        "games_played": games,
                        # convert to "enemy win" perspective used by OpenDota path:
                        # here winCount is for the queried hero vs heroId2
                        # DraftAdvisor counters_for expects enemy's winrate vs others
                        "wins": games - wins,  # invert so counters_for logic stays
                    }
                )
            self._save_cache(cache_name, rows)
        except Exception:
            logger.debug("STRATZ matchUp unavailable for %s", hero_id, exc_info=True)
            rows = []
        self._matchups_cache[hero_id] = rows
        return rows

    def top_bans(self, n: int = 15, use_pro: bool = True) -> list[HeroMeta]:
        # Without dedicated ban endpoint in free queries, use high pick + high wr as "priority ban" proxy
        meta = self.get_meta()
        heroes = list(meta.heroes.values())
        heroes.sort(
            key=lambda h: (h.pick_rate_share * 100 + h.win_rate * 50), reverse=True
        )
        return heroes[:n]

    def top_picks(self, n: int = 20, use_pro: bool = False) -> list[HeroMeta]:
        meta = self.get_meta()
        heroes = list(meta.heroes.values())
        heroes.sort(key=lambda h: h.picks, reverse=True)
        return heroes[:n]

    def counters_for(self, enemy_hero_id: int, n: int = 8) -> list[tuple[HeroMeta, float]]:
        meta = self.get_meta()
        rows = self.get_matchups(enemy_hero_id)
        if not rows:
            return []
        scored: list[tuple[HeroMeta, float, int]] = []
        for row in rows:
            hid = int(row.get("hero_id") or 0)
            games = int(row.get("games_played") or 0)
            wins = int(row.get("wins") or 0)
            if games < 30 or hid not in meta.heroes:
                continue
            enemy_wr = wins / games
            scored.append((meta.heroes[hid], 1.0 - enemy_wr, games))
        scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return [(h, s) for h, s, _ in scored[:n]]

    def top_by_position(self, position: str, n: int = 10) -> list[HeroMeta]:
        meta = self.get_meta()
        pos = position.upper()
        if not pos.startswith("POSITION_") and pos.isdigit():
            pos = f"POSITION_{pos}"
        rows = meta.by_position.get(pos) or []
        return rows[:n]
