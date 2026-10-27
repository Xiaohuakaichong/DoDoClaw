from dodoclaw.knowledge.retriever import format_context, retrieve, score_doc
from dodoclaw.knowledge.util import strip_html, tokenize


def test_strip_html():
    assert "hello" in strip_html("<b>hello</b> world")


def test_tokenize_cn_en():
    toks = tokenize("斧王 Berserker 补丁 7.41")
    assert any("斧" in t or t == "斧王" for t in toks) or "斧王" in toks or len(toks) >= 2
    assert "berserker" in toks or "7" in "".join(toks)


def test_retrieve_prefers_hero():
    docs = [
        {
            "id": "hero:npc_dota_hero_axe",
            "kind": "hero",
            "title": "Axe 技能与机制",
            "text": "英雄: Axe\n技能: Berserker's Call 嘲讽附近敌人",
            "tags": ["axe", "npc_dota_hero_axe", "hero"],
            "hero_key": "npc_dota_hero_axe",
            "localized_name": "Axe",
        },
        {
            "id": "patch:7.41:general",
            "kind": "patch_general",
            "title": "补丁 7.41 全局",
            "text": "野怪调整 神符",
            "tags": ["patch", "7.41", "general"],
        },
    ]
    hits = retrieve(docs, "斧王嘲讽技能怎么用", hero_keys=["npc_dota_hero_axe"], top_k=3)
    assert hits
    assert hits[0]["id"].startswith("hero:")
    ctx = format_context(hits)
    assert "知识库" in ctx
    assert score_doc(tokenize("axe"), docs[0]) > 0


def test_patch_to_documents_minimal():
    from dodoclaw.knowledge.patches import patch_to_documents

    patch = {
        "patch_number": "7.99z",
        "general_notes": [
            {"title": "地图", "generic": [{"note": "神符刷新调整"}]}
        ],
        "heroes": [
            {
                "hero_id": 2,
                "hero_notes": [{"note": "基础力量降低"}],
                "abilities": [
                    {
                        "ability_id": 5008,
                        "ability_notes": [{"note": "伤害降低"}],
                    }
                ],
            }
        ],
    }
    docs = patch_to_documents(
        patch,
        heroes_by_id={2: {"name": "npc_dota_hero_axe", "localized_name": "Axe"}},
        ability_id_to_name={5008: "axe_battle_hunger"},
    )
    kinds = {d["kind"] for d in docs}
    assert "patch_general" in kinds
    assert "patch_hero" in kinds


# ── Chinese questions, forced heroes, budget sharing ──
from dodoclaw.knowledge.retriever import _fit, _shares


def _hero(key, loc, text):
    return {"id": f"hero:{key}", "kind": "hero", "title": f"{loc} 技能与机制", "text": text,
            "tags": [loc.lower(), key, "hero"], "hero_key": key, "localized_name": loc}


def _patch(key, ver, text):
    return {"id": f"patch:{ver}:{key}", "kind": "patch_hero", "title": f"补丁 {ver}", "text": text,
            "tags": ["patch", ver], "patch": ver, "hero_key": key}


def test_tokenize_chinese_bigrams():
    assert tokenize("削弱了什么") == ["削弱", "弱了", "了什", "什么"]
    assert tokenize("BKB 冷却") == ["bkb", "冷却"]
    assert tokenize("兽") == ["兽"]


def test_named_hero_first_with_newest_patch_and_no_zero_score_filler():
    am = "npc_dota_hero_antimage"
    docs = [
        _patch(am, "7.41c", "旧改动"),
        _hero("npc_dota_hero_axe", "Axe", "斧王机制"),
        _hero(am, "Anti-Mage", "敌法机制"),
        _patch(am, "7.41e", "新改动"),
        {"id": "x", "kind": "patch_general", "title": "无关", "text": "野怪", "tags": []},
    ]
    hits = retrieve(docs, "敌法怎么打", hero_keys=[am, "npc_dota_hero_axe"])
    assert [h["id"] for h in hits] == [f"hero:{am}", f"patch:7.41e:{am}", "hero:npc_dota_hero_axe"]


def test_english_hero_name_in_question_is_forced_in():
    docs = [_hero("npc_dota_hero_storm_spirit", "Storm Spirit", "球状闪电"), _hero("npc_dota_hero_axe", "Axe", "x")]
    assert retrieve(docs, "how to fight storm spirit")[0]["id"] == "hero:npc_dota_hero_storm_spirit"


def test_budget_is_shared_and_long_hero_doc_keeps_every_ability():
    long_text = "\n".join(
        f"- 技能{i}\n  说明: 很重要的描述{i}\n  CD: 10  魔法: 50\n  数值: " + "X " * 200 for i in range(4)
    )
    docs = [_hero("npc_dota_hero_a", "Aaa", long_text), _hero("npc_dota_hero_b", "Bbb", "短文档")]
    hits = retrieve(docs, "q", hero_keys=["npc_dota_hero_a", "npc_dota_hero_b"], max_chars=1200)
    assert [h["id"] for h in hits] == ["hero:npc_dota_hero_a", "hero:npc_dota_hero_b"]
    assert all(f"技能{i}" in hits[0]["text"] for i in range(4)) and "数值" not in hits[0]["text"]
    assert sum(len(h["text"]) for h in hits) <= 1200


def test_shares_and_fit_helpers():
    assert _shares([5000, 100, 3000, 120], 2800) == [1720, 100, 860, 120]
    assert sum(_shares([9000, 9000, 9000], 2800)) <= 2800
    assert _fit("短", 10) == "短"
    assert _fit("a\n  数值: 123456789\nb", 6) == "a\nb"
    assert _fit("x" * 50, 10).endswith("…") and len(_fit("x" * 50, 10)) == 10
