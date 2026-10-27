"""What the coach sees: Chinese situation report, objective timers, heroes named
in the question, short per-match memory, and fast failure (no 6-minute hangs)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from dodoclaw.coach import agent as agent_mod
from dodoclaw.coach.agent import CoachAgent, clip_reply
from dodoclaw.coach.prompts import CORE_RULES, DEFAULT_SYSTEM, build_system_prompt
from dodoclaw.gsi.objectives import MatchEvents
from dodoclaw.gsi.state import GameSnapshot, parse_gsi_payload
from dodoclaw.names import find_heroes, hero_zh, item_label

IN_GAME = "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"


def _payload(**over) -> dict:
    p = {
        "map": {"matchid": "77", "game_state": IN_GAME, "clock_time": 1500, "game_time": 1590, "daytime": False},
        "player": {"team_name": "radiant", "gold": 1800, "gold_reliable": 900, "gpm": 520, "xpm": 610,
                   "kills": 5, "deaths": 2, "assists": 7, "last_hits": 180, "denies": 12,
                   "buyback_cost": 2100, "buyback_cooldown": 0},
        "hero": {"name": "npc_dota_hero_axe", "level": 18, "alive": True, "health": 900, "max_health": 2400,
                 "mana": 300, "max_mana": 700},
        "abilities": {
            "ability0": {"name": "axe_berserkers_call", "level": 4, "cooldown": 0, "can_cast": True},
            "ability3": {"name": "axe_culling_blade", "level": 3, "cooldown": 42, "ultimate": True},
            "ability4": {"name": "special_bonus_unique_axe_2", "level": 1},
            "ability5": {"name": "plus_high_five", "level": 1},
        },
        "items": {
            "slot0": {"name": "item_blink", "cooldown": 3},
            "slot1": {"name": "item_black_king_bar"},
            "slot2": {"name": "empty"},
            "slot6": {"name": "item_magic_wand", "charges": 12},
            "stash0": {"name": "item_ultimate_orb"},
            "teleport0": {"name": "empty"},
            "neutral0": {"name": "empty"},
        },
    }
    p.update(over)
    return p


# ── names ─────────────────────────────────────────────
def test_find_heroes_longest_alias_first_and_no_loose_substrings():
    assert find_heroes("敌法怎么打") == ["npc_dota_hero_antimage"]
    assert find_heroes("兽王和野兽") == ["npc_dota_hero_beastmaster"]  # "兽" alone never matches
    assert find_heroes("痛苦女王怎么克") == ["npc_dota_hero_queenofpain"]
    assert find_heroes("我玩斧子对线火女") == ["npc_dota_hero_axe", "npc_dota_hero_lina"]
    assert find_heroes("sf怎么出装") == ["npc_dota_hero_nevermore"]  # Chinese context: lower case ok
    assert find_heroes("i am here") == []  # English "am" is not Anti-Mage
    assert find_heroes("I am playing SF vs AM") == ["npc_dota_hero_nevermore", "npc_dota_hero_antimage"]
    assert find_heroes("antimage blink") == ["npc_dota_hero_antimage"]
    assert find_heroes("") == []


def test_chinese_names():
    assert hero_zh("npc_dota_hero_axe") == hero_zh("axe") == "斧王"
    assert item_label("item_blink") == "闪烁匕首"
    assert item_label("item_not_a_thing") == "not_a_thing"


# ── snapshot summary ──────────────────────────────────
def test_summary_is_chinese_and_slot_aware():
    snap = parse_gsi_payload(_payload())
    text = snap.summary_for_llm()
    assert "斧王(axe) 18级 天辉 存活" in text and "(38%)" in text
    assert "比赛时间 25:00 夜晚" in text
    assert "物品栏: 闪烁匕首(冷却3s)，黑皇杖" in text
    assert "背包: 魔杖(12层)" in text
    assert "储藏处(未带在身上): 极限法球" in text
    assert "回城卷轴: 没有" in text
    assert "买活: 2100 金，差 300 金" in text
    assert "axe_culling_blade(3级 大招 冷却42s)" in text and "axe_berserkers_call(4级 就绪)" in text
    assert "special_bonus" not in text and "plus_high_five" not in text
    assert "npc_dota_hero_" not in text and "item_" not in text


def test_slots_and_tp_helpers():
    snap = parse_gsi_payload(_payload())
    assert [i["name"] for i in snap.inventory] == ["item_blink", "item_black_king_bar"]
    assert snap.has_tp is False and snap.can_buyback is False
    p = _payload()
    p["items"]["teleport0"] = {"name": "item_tpscroll", "charges": 2}
    p["player"]["gold"] = 5000
    snap = parse_gsi_payload(p)
    assert snap.has_tp is True and snap.can_buyback is True
    assert "买活: 2100 金，可用" in snap.summary_for_llm()
    assert GameSnapshot().summary_for_llm().startswith("当前没有收到")


# ── objective timers ──────────────────────────────────
def test_objective_context_lines_from_events():
    ev = MatchEvents()
    assert ev.context_lines(-30) == []
    lines = ev.context_lines(400)
    assert "下个智慧神龛: 07:00" in lines and "痛苦魔方首次刷新: 15:00" in lines
    assert any("肉山: 本局还没被击杀" in x for x in lines)
    ev.ingest({"map": {"matchid": "1", "clock_time": 1300, "game_time": 1390},
               "events": [{"event_type": "roshan_killed", "game_time": 1390},
                          {"event_type": "aegis_picked_up", "game_time": 1392}]})
    lines = ev.context_lines(1500)
    assert "肉山: 第 1 次击杀于 21:40，复活窗口 29:40–32:40（未复活）" in lines
    assert "不朽盾: 场上有人持有，约 102s 后消失" in lines
    assert "下个智慧神龛: 28:00" in lines
    assert any("可能已复活" in x for x in ev.context_lines(1300 + 500))


# ── prompts ───────────────────────────────────────────
def test_custom_style_keeps_core_rules():
    assert build_system_prompt(None) == DEFAULT_SYSTEM
    custom = build_system_prompt("你是毒舌教练。")
    assert custom.startswith("你是毒舌教练。") and CORE_RULES in custom
    assert build_system_prompt(DEFAULT_SYSTEM) == DEFAULT_SYSTEM  # no duplicated rules


def test_clip_reply_prefers_sentence_end():
    text = "先出跳刀。再补黑皇杖，团战先手。最后看对面阵容决定"
    assert clip_reply(text, 20) == "先出跳刀。再补黑皇杖，团战先手。"
    assert clip_reply("一二三四五六七八九十", 6) == "一二三四五…"
    assert clip_reply("短句", 0) == "短句"


# ── coach agent ───────────────────────────────────────
def _coach(create, responses=None):
    coach = CoachAgent("fake-key", "https://api.example.com/v1", "m", provider_id="deepseek")
    coach._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        responses=SimpleNamespace(create=responses or (lambda **kw: pytest.fail("no fallback expected"))),
    )
    return coach


def _snap(match="77"):
    return SimpleNamespace(summary_for_llm=lambda: "局势", match_id=match)


def test_follow_up_sees_previous_turns_and_new_match_forgets():
    seen = []

    def create(**req):
        seen.append(req["messages"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=f"答{len(seen)}"))])

    coach = _coach(create)
    coach.answer("出什么装", _snap(), objectives_context="肉山: …", heroes_context="敌法师(antimage)")
    coach.answer("那第二件呢", _snap())
    roles = [m["role"] for m in seen[1]]
    assert roles == ["system", "user", "assistant", "user"]
    assert "出什么装" in seen[1][1]["content"] and seen[1][2]["content"] == "答1"
    assert "【目标计时】" in seen[0][-1]["content"] and "【问题里提到的英雄】" in seen[0][-1]["content"]
    for i in range(5):
        coach.answer(f"问{i}", _snap())
    assert len(seen[-1]) == 2 + 2 * agent_mod.HISTORY_TURNS  # capped
    coach.answer("新的一局", _snap(match="78"))
    assert [m["role"] for m in seen[-1]] == ["system", "user"]


def _status_error(code: int):
    req = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    return openai.APIStatusError(f"Error code: {code}", response=httpx.Response(code, request=req), body=None)


@pytest.mark.parametrize("exc", [
    _status_error(401),
    _status_error(429),
    openai.APITimeoutError(request=httpx.Request("POST", "https://x")),
])
def test_no_responses_fallback_for_auth_rate_or_network(exc):
    def create(**_):
        raise exc

    coach = _coach(create)  # responses.create fails the test if called
    with pytest.raises(RuntimeError) as info:
        coach.answer("出什么", _snap())
    assert info.value.__cause__ is exc


def test_responses_fallback_only_on_404():
    def create(**_):
        raise _status_error(404)

    coach = _coach(create, responses=lambda **kw: SimpleNamespace(output_text="走 responses"))
    assert coach.answer("出什么", _snap()) == "走 responses"


def test_client_has_short_timeout_and_one_retry(monkeypatch):
    got = {}

    class FakeOpenAI:
        def __init__(self, **kw):
            got.update(kw)

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    CoachAgent("k", "https://api.example.com/v1", "m")._get_client()
    assert got["max_retries"] == 1
    assert got["timeout"].read == agent_mod.REQUEST_TIMEOUT_SEC and got["timeout"].connect == 10.0


# ── service.ask wiring ────────────────────────────────
def test_service_ask_passes_objectives_heroes_and_knowledge_keys():
    from dodoclaw.gsi.state import GameStateStore
    from dodoclaw.service import DoDoClawService

    svc = DoDoClawService.__new__(DoDoClawService)
    svc.store = GameStateStore()
    svc.objectives = MatchEvents()
    svc._draft_advisor = None
    svc._gsi_updates = 1
    svc._recorder = None
    svc.on_gsi_cb = None
    svc.on_log = lambda *_a: None
    payload = _payload(events=[{"event_type": "roshan_killed", "game_time": 1390}])
    svc.store.update(payload)
    svc._on_gsi(payload)  # feeds the shared objective tracker

    kb_calls = {}

    class KB:
        def context_for(self, question, *, hero_keys, top_k, max_chars):
            kb_calls["hero_keys"] = hero_keys
            return "【知识库检索】…"

    svc._knowledge = KB()
    svc.yaml = {}
    got = {}

    class Coach:
        api_key = "k"

        def answer(self, question, snap, **ctx):
            got.update(ctx)
            return "好"

    svc.coach = Coach()
    assert svc.ask("对面敌法怎么打", speak=False) == "好"
    assert kb_calls["hero_keys"] == ["npc_dota_hero_antimage", "npc_dota_hero_axe"]
    assert got["heroes_context"] == "敌法师(antimage)"
    assert "肉山: 第 1 次击杀于 21:40" in got["objectives_context"]
    assert got["knowledge_context"] == "【知识库检索】…"


def test_service_ask_error_text_is_short_chinese_reason():
    from dodoclaw.gsi.state import GameStateStore
    from dodoclaw.service import DoDoClawService

    svc = DoDoClawService.__new__(DoDoClawService)
    svc.store, svc.objectives = GameStateStore(), MatchEvents()
    svc._draft_advisor = svc._knowledge = None

    class Coach:
        api_key = "k"

        def answer(self, *_a, **_k):
            raise RuntimeError("LLM 调用失败") from _status_error(401)

    svc.coach = Coach()
    assert svc.ask("出什么", speak=False) == "教练调用失败：Key 无效或已过期"
