"""Chinese display names for heroes / items, and hero detection in free text.

Data files (bundled in ``dodoclaw/data``):
- ``hero_aliases.json`` — Valve herolist (schinese) + community aliases
- ``item_names_zh.json`` — Valve item names (schinese)

Shared by the coach context, the knowledge retriever and the web UI.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
HERO_PREFIX = "npc_dota_hero_"


def hero_key(name: str) -> str:
    """``npc_dota_hero_axe`` -> ``axe``."""
    return (name or "").removeprefix(HERO_PREFIX)


@lru_cache(maxsize=1)
def _hero_data() -> tuple[dict[str, Any], ...]:
    try:
        data = json.loads((DATA_DIR / "hero_aliases.json").read_text(encoding="utf-8"))
        return tuple(h for h in data.get("heroes") or [] if isinstance(h, dict) and h.get("key"))
    except Exception:
        logger.exception("hero_aliases.json load failed")
        return ()


@lru_cache(maxsize=1)
def _hero_zh_map() -> dict[str, str]:
    return {hero_key(h["key"]): h.get("name_zh") or "" for h in _hero_data()}


@lru_cache(maxsize=1)
def _item_zh_map() -> dict[str, str]:
    try:
        return json.loads((DATA_DIR / "item_names_zh.json").read_text(encoding="utf-8"))
    except Exception:
        logger.exception("item_names_zh.json load failed")
        return {}


def hero_zh(key: str) -> str:
    """Chinese hero name for ``axe`` / ``npc_dota_hero_axe``; falls back to the key."""
    k = hero_key(key)
    return _hero_zh_map().get(k) or k


def item_zh(key: str, default: str = "物品") -> str:
    """Chinese item name for ``item_blink`` / ``blink``; ``default`` when unknown."""
    k = (key or "").removeprefix("item_")
    return _item_zh_map().get(k, default)


def item_label(key: str) -> str:
    """Chinese item name, or the bare internal key when we have no translation."""
    k = (key or "").removeprefix("item_")
    return _item_zh_map().get(k) or k


# ── hero mentions in free text ─────────────────────────
# hero_aliases.json asks for exact / prefix matching, never loose substring
# matching (e.g. "兽" must not hit "兽王"). In a sentence we scan left to right
# and always take the LONGEST name starting at that position, so "兽王" wins
# over "兽" and "痛苦女王" over "女王". One-character Chinese aliases are too
# ambiguous inside a sentence and are skipped; Latin aliases must stand alone
# as a word, and in an all-English sentence two-letter ones (AM, ES, SF…) must
# be typed in upper case so words like "am" / "es" don't count.
_LATIN = re.compile(r"[A-Za-z0-9]")
_CJK = re.compile(r"[\u4e00-\u9fff]")


@lru_cache(maxsize=1)
def _alias_table() -> tuple[dict[str, str], tuple[int, ...]]:
    table: dict[str, str] = {}
    for h in _hero_data():
        key = h["key"]
        short = hero_key(key)  # "antimage", "storm_spirit"
        names = (
            h.get("name_zh"),
            h.get("name_en"),
            short,
            short.replace("_", " "),
            *(h.get("aliases") or []),
        )
        for name in names:
            name = str(name or "").strip()
            if not name:
                continue
            is_latin = bool(_LATIN.match(name[0]))
            if not is_latin and len(name) < 2:
                continue
            table.setdefault(name.lower(), key)
    lengths = tuple(sorted({len(a) for a in table}, reverse=True))
    return table, lengths


def find_heroes(text: str, limit: int = 5) -> list[str]:
    """Hero keys (``npc_dota_hero_*``) named in ``text``, in order of first mention."""
    if not text:
        return []
    table, lengths = _alias_table()
    low = text.lower()
    if len(low) != len(text):  # rare case-folding that changes length: keep indices aligned
        low = text
    chinese = bool(_CJK.search(text))  # "sf怎么出装" is fine in lower case
    out: list[str] = []
    i, n = 0, len(text)
    while i < n and len(out) < limit:
        hit = 0
        for ln in lengths:
            if i + ln > n:
                continue
            frag = low[i : i + ln]
            key = table.get(frag)
            if key is None:
                continue
            if _LATIN.match(frag[0]):
                before = text[i - 1] if i > 0 else " "
                after = text[i + ln] if i + ln < n else " "
                if _LATIN.match(before) or _LATIN.match(after):
                    continue
                if ln <= 2 and not chinese and not text[i : i + ln].isupper():
                    continue
            if key not in out:
                out.append(key)
            hit = ln
            break
        i += hit or 1
    return out
