from __future__ import annotations

import re
from html import unescape


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    if not text:
        return ""
    t = unescape(str(text))
    t = _TAG_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


def tokenize(text: str) -> list[str]:
    """Lightweight tokens for EN/CN keyword retrieval."""
    if not text:
        return []
    text = text.lower()
    # keep cjk as unigrams/bigrams-ish by chars groups + latin words
    parts = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{1,4}", text)
    return [p for p in parts if len(p) > 1 or "\u4e00" <= p <= "\u9fff"]


def pretty_hero_key(name: str) -> str:
    n = (name or "").strip()
    if n.startswith("npc_dota_hero_"):
        n = n[len("npc_dota_hero_") :]
    return n.replace("_", " ")
