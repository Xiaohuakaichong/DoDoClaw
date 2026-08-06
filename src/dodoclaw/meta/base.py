"""Shared meta types for OpenDota / STRATZ providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class HeroMeta:
    hero_id: int
    name: str  # npc_dota_hero_* or short name
    localized_name: str
    roles: list[str] = field(default_factory=list)
    primary_attr: str = ""
    picks: int = 0
    wins: int = 0
    pro_pick: int = 0
    pro_ban: int = 0
    pro_win: int = 0
    # Optional STRATZ extras
    position: str = ""  # e.g. POSITION_2
    bracket: str = ""
    source: str = ""

    @property
    def win_rate(self) -> float:
        return (self.wins / self.picks) if self.picks else 0.0

    @property
    def pick_rate_share(self) -> float:
        return float(getattr(self, "_pick_share", 0.0) or 0.0)

    @property
    def pro_ban_rate(self) -> float:
        den = self.pro_pick + self.pro_ban
        return (self.pro_ban / den) if den else 0.0


@dataclass
class MetaSnapshot:
    updated_at: float = 0.0
    source: str = ""
    heroes: dict[int, HeroMeta] = field(default_factory=dict)
    by_name: dict[str, HeroMeta] = field(default_factory=dict)
    by_localized: dict[str, HeroMeta] = field(default_factory=dict)
    # STRATZ: position-scoped leaderboards
    by_position: dict[str, list[HeroMeta]] = field(default_factory=dict)
    note: str = ""

    def get_hero(self, key: str | int) -> HeroMeta | None:
        if isinstance(key, int):
            return self.heroes.get(key)
        k = key.strip().lower()
        if k in self.by_name:
            return self.by_name[k]
        if k in self.by_localized:
            return self.by_localized[k]
        if not k.startswith("npc_dota_hero_"):
            alt = f"npc_dota_hero_{k}"
            if alt in self.by_name:
                return self.by_name[alt]
        # strip npc prefix partial
        for name, hm in self.by_name.items():
            if name.endswith(k) or k in name:
                return hm
        for loc, hm in self.by_localized.items():
            if k in loc:
                return hm
        return None


class MetaProvider(Protocol):
    source_name: str

    def get_meta(self, force: bool = False) -> MetaSnapshot: ...

    def get_matchups(self, hero_id: int, force: bool = False) -> list[dict[str, Any]]: ...

    def top_bans(self, n: int = 15, use_pro: bool = True) -> list[HeroMeta]: ...

    def top_picks(self, n: int = 20, use_pro: bool = False) -> list[HeroMeta]: ...

    def counters_for(self, enemy_hero_id: int, n: int = 8) -> list[tuple[HeroMeta, float]]: ...

    def top_by_position(
        self, position: str, n: int = 10
    ) -> list[HeroMeta]: ...
