"""Simple keyword retrieval over knowledge documents (no vector DB required)."""

from __future__ import annotations

from typing import Any

from dodoclaw.knowledge.util import tokenize


def score_doc(query_tokens: list[str], doc: dict[str, Any]) -> float:
    if not query_tokens:
        return 0.0
    text = f"{doc.get('title', '')} {doc.get('text', '')} {' '.join(doc.get('tags') or [])}"
    tokens = set(tokenize(text))
    tags = {str(t).lower() for t in (doc.get("tags") or [])}
    score = 0.0
    for qt in query_tokens:
        if qt in tags:
            score += 3.0
        if qt in tokens:
            score += 1.0
        # partial for longer tokens
        if len(qt) >= 3:
            for t in tokens:
                if qt in t or t in qt:
                    score += 0.25
                    break
    # prefer patch docs slightly when query mentions patch/version
    kind = doc.get("kind") or ""
    if kind.startswith("patch") and any(
        x in query_tokens for x in ("patch", "补丁", "版本", "改动", "削弱", "增强")
    ):
        score *= 1.25
    if kind == "hero" and any(x in query_tokens for x in ("技能", "机制", "大招", "加点")):
        score *= 1.15
    return score


def retrieve(
    docs: list[dict[str, Any]],
    query: str,
    *,
    hero_keys: list[str] | None = None,
    top_k: int = 6,
    max_chars: int = 2800,
) -> list[dict[str, Any]]:
    q_tokens = tokenize(query)
    # boost with hero names from GSI
    for hk in hero_keys or []:
        q_tokens.extend(tokenize(hk.replace("npc_dota_hero_", "").replace("_", " ")))
        q_tokens.append(hk.lower())

    # force-include matching hero docs
    forced: list[dict[str, Any]] = []
    rest = []
    hero_set = {h.lower() for h in (hero_keys or [])}
    for d in docs:
        key = str(d.get("hero_key") or "").lower()
        loc = str(d.get("localized_name") or "").lower()
        if key and key in hero_set:
            forced.append(d)
        elif loc and any(loc in tokenize(query) or loc in q_tokens for _ in [0]):
            # weak: if localized name appears in query tokens
            if loc in " ".join(q_tokens) or any(loc in t or t in loc for t in q_tokens if len(t) > 2):
                forced.append(d)
            else:
                rest.append(d)
        else:
            rest.append(d)

    scored = [(score_doc(q_tokens, d), d) for d in rest]
    scored.sort(key=lambda x: -x[0])

    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in forced:
        did = str(d.get("id"))
        if did not in seen:
            picked.append(d)
            seen.add(did)
    for sc, d in scored:
        if sc <= 0 and len(picked) >= 2:
            continue
        did = str(d.get("id"))
        if did in seen:
            continue
        picked.append(d)
        seen.add(did)
        if len(picked) >= top_k:
            break

    # trim by chars
    out: list[dict[str, Any]] = []
    total = 0
    for d in picked:
        chunk = d.get("text") or ""
        if total + len(chunk) > max_chars:
            remain = max_chars - total
            if remain < 200:
                break
            d = {**d, "text": chunk[: remain - 1] + "…"}
            out.append(d)
            break
        out.append(d)
        total += len(chunk)
    return out


def format_context(docs: list[dict[str, Any]]) -> str:
    if not docs:
        return ""
    parts = ["【知识库检索 · 英雄机制 / 官方补丁】"]
    for d in docs:
        parts.append(f"### {d.get('title') or d.get('id')}")
        parts.append((d.get("text") or "").strip())
        parts.append("")
    return "\n".join(parts).strip()
