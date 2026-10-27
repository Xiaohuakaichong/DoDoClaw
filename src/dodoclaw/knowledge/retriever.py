"""Simple keyword retrieval over knowledge documents (no vector DB required)."""

from __future__ import annotations

import re
from typing import Any

from dodoclaw.knowledge.util import tokenize

# Document token sets are the expensive part of scoring; docs only change on a
# knowledge sync, so cache them by (id, text hash). str hashes are cached by
# Python itself, so the lookup is cheap.
_TOKEN_CACHE: dict[tuple[str, int], frozenset[str]] = {}
_TOKEN_CACHE_MAX = 4000

MIN_DOC_CHARS = 600  # a doc we have to cut keeps at least this much, else it's dropped


def _doc_tokens(doc: dict[str, Any]) -> frozenset[str]:
    text = f"{doc.get('title', '')} {doc.get('text', '')} {' '.join(doc.get('tags') or [])}"
    key = (str(doc.get("id")), hash(text))
    toks = _TOKEN_CACHE.get(key)
    if toks is None:
        if len(_TOKEN_CACHE) >= _TOKEN_CACHE_MAX:
            _TOKEN_CACHE.clear()
        toks = _TOKEN_CACHE[key] = frozenset(tokenize(text))
    return toks


def score_doc(query_tokens: list[str], doc: dict[str, Any]) -> float:
    if not query_tokens:
        return 0.0
    tokens = _doc_tokens(doc)
    tags = {str(t).lower() for t in (doc.get("tags") or [])}
    score = 0.0
    for qt in set(query_tokens):
        if qt in tags:
            score += 3.0
        if qt in tokens:
            score += 1.0
        elif len(qt) >= 3:
            # partial match for longer latin words ("blink" ~ "blinks")
            if any(qt in t or t in qt for t in tokens if len(t) >= 3):
                score += 0.25
    # prefer patch docs slightly when query mentions patch/version
    kind = doc.get("kind") or ""
    if kind.startswith("patch") and any(
        x in query_tokens for x in ("patch", "补丁", "版本", "改动", "削弱", "增强")
    ):
        score *= 1.25
    if kind == "hero" and any(x in query_tokens for x in ("技能", "机制", "大招", "加点")):
        score *= 1.15
    return score


def _patch_order(doc: dict[str, Any]) -> tuple:
    """Newest patch first: '7.41e' > '7.41d' > '7.40'. Hero docs before patches."""
    if doc.get("kind") == "hero":
        return (0,)
    ver = str(doc.get("patch") or "").lower()
    nums = [int(x) for x in re.findall(r"\d+", ver)][:3]
    nums += [0] * (3 - len(nums))
    letter = re.search(r"[a-z]$", ver)
    sub = ord(letter.group()) - 96 if letter else 0  # 7.41 < 7.41a < 7.41e
    return (1, *(-x for x in nums), -sub)


def retrieve(
    docs: list[dict[str, Any]],
    query: str,
    *,
    hero_keys: list[str] | None = None,
    top_k: int = 6,
    max_chars: int = 2800,
) -> list[dict[str, Any]]:
    """Pick docs for the coach prompt.

    ``hero_keys`` (``npc_dota_hero_*``, most relevant first — heroes named in
    the question, then the player's own) force in that hero's mechanics doc and
    its newest patch note. The rest is filled by keyword score; docs with no
    keyword overlap are never added just to fill ``top_k``.
    """
    # Score on the question's own words only: the forced heroes are already in,
    # and their names as extra keywords dragged in look-alikes (axe → "Wild Axes").
    q_tokens = tokenize(query)
    keys = [h.lower() for h in (hero_keys or []) if h]
    q_low = (query or "").lower()

    by_hero: dict[str, list[dict[str, Any]]] = {}
    rest: list[dict[str, Any]] = []
    for d in docs:
        key = str(d.get("hero_key") or "").lower()
        loc = str(d.get("localized_name") or "").lower()
        if key and key in keys:
            by_hero.setdefault(key, []).append(d)
        elif key and len(loc) > 2 and re.search(rf"(?<![a-z]){re.escape(loc)}(?![a-z])", q_low):
            # English hero name typed in the question ("antimage", "Storm Spirit")
            by_hero.setdefault(key, []).append(d)
            if key not in keys:
                keys.append(key)
        else:
            rest.append(d)

    picked: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(d: dict[str, Any]) -> None:
        did = str(d.get("id"))
        if did not in seen:
            picked.append(d)
            seen.add(did)

    for key in keys:
        group = sorted(by_hero.get(key, []), key=_patch_order)
        for d in group[:2]:  # mechanics doc + newest patch note
            _add(d)

    scored = [(score_doc(q_tokens, d), d) for d in rest]
    scored.sort(key=lambda x: (-x[0], _patch_order(x[1])))  # ties: newest patch first
    for sc, d in scored:
        if len(picked) >= top_k:
            break
        if sc <= 0:
            break
        _add(d)

    return _fit_budget(picked, max_chars)


def _shares(needs: list[int], budget: int) -> list[int]:
    """Split ``budget`` chars over docs (first doc weighted x2). Short docs take only
    what they need and the rest flows to the long ones (water filling)."""
    caps = [0] * len(needs)
    weights = [2 if i == 0 else 1 for i in range(len(needs))]
    active = set(range(len(needs)))
    left = budget
    while active:
        total_w = sum(weights[i] for i in active)
        fair = {i: left * weights[i] // total_w for i in active}
        done = [i for i in active if needs[i] <= fair[i]]
        if not done:
            for i in active:
                caps[i] = fair[i]
            break
        for i in done:
            caps[i] = needs[i]
            left -= needs[i]
            active.discard(i)
    return caps


def _fit(text: str, cap: int) -> str:
    """Shorten a doc to ``cap`` chars: drop the long per-level 数值 lines first
    (keeps every ability's name, description and CD), then cut."""
    if len(text) <= cap:
        return text
    lines = text.splitlines()
    slim = "\n".join(ln for ln in lines if not ln.lstrip().startswith("数值:"))
    if len(slim) <= cap:
        return slim
    return slim[: cap - 1].rstrip() + "…"


def _fit_budget(picked: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    """Fit the picked docs into ``max_chars`` (most relevant first). If a doc would
    have to be cut below MIN_DOC_CHARS, drop docs from the least relevant end."""

    def size(d: dict[str, Any]) -> int:
        return len(d.get("text") or "")

    docs = list(picked)
    while docs:
        caps = _shares([size(d) for d in docs], max_chars)
        cut = [c for c, d in zip(caps, docs) if c < size(d)]
        if not cut or min(cut) >= MIN_DOC_CHARS or len(docs) == 1:
            break
        docs.pop()
    if not docs:
        return []
    caps = _shares([size(d) for d in docs], max_chars)
    return [d if size(d) <= c else {**d, "text": _fit(d.get("text") or "", c)} for d, c in zip(docs, caps)]


def format_context(docs: list[dict[str, Any]]) -> str:
    if not docs:
        return ""
    parts = ["【知识库检索 · 英雄机制 / 官方补丁】"]
    for d in docs:
        parts.append(f"### {d.get('title') or d.get('id')}")
        parts.append((d.get("text") or "").strip())
        parts.append("")
    return "\n".join(parts).strip()
