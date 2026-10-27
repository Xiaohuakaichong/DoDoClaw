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


_TOKEN_RE = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """Lightweight tokens for EN/CN keyword retrieval.

    Latin/digit words stay whole; Chinese runs become overlapping bigrams
    ("削弱了什么" -> 削弱 弱了 了什 什么). Fixed 1–4 char chunks used to split
    the query and the documents at different places, so Chinese questions
    almost never matched anything.
    """
    if not text:
        return []
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text.lower()):
        p = m.group()
        if "\u4e00" <= p[0] <= "\u9fff":
            if len(p) == 1:
                out.append(p)
            else:
                out.extend(p[i : i + 2] for i in range(len(p) - 1))
        elif len(p) > 1:
            out.append(p)
    return out


def pretty_hero_key(name: str) -> str:
    n = (name or "").strip()
    if n.startswith("npc_dota_hero_"):
        n = n[len("npc_dota_hero_") :]
    return n.replace("_", " ")
