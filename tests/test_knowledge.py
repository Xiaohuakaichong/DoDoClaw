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
