"""Schedules from domain/reminder-budget.md (7.41f + lotus)."""

from dodoclaw.gsi.state import GameSnapshot, GameStateStore
from dodoclaw.reminders.engine import ReminderEngine
from dodoclaw.reminders import schedule as sch
from dodoclaw.reminders.rules import (
    bounty_rune_rule,
    lotus_pool_rule,
    power_rune_rule,
    water_rune_rule,
)
from dodoclaw.webui import settings_store as st


def _snap(clock: int) -> GameSnapshot:
    return GameSnapshot(
        game_state="DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
        clock_time=clock,
    )


def test_water_warn_at_145_and_345():
    assert [w.fire_at for w in sch.water_windows()] == [105, 225]  # 1:45, 3:45
    h = water_rune_rule(_snap(105), None)
    assert h and h[0].message == "15 秒后河道水符"
    assert water_rune_rule(_snap(120), None) == []  # at spawn, not at warn


def test_power_warn_from_six():
    wins = sch.power_windows()
    assert wins[0].fire_at == 6 * 60 - 15
    assert wins[0].message == "15 秒后河道神符"
    assert power_rune_rule(_snap(wins[0].fire_at), None)
    # old behaviour fired at spawn second — must NOT fire at exact 6:00 anymore
    assert power_rune_rule(_snap(360), None) == []


def test_bounty_skip_zero_warn_20s():
    wins = sch.bounty_windows()
    assert wins[0].spawn_sec == 180
    assert wins[0].fire_at == 160  # 2:40
    assert wins[0].message == "20 秒后赏金神符"
    assert bounty_rune_rule(_snap(0), None) == []
    assert bounty_rune_rule(_snap(160), None)


def test_lotus_at_mark_exact_wording_no_count():
    assert sch.LOTUS_MSG == "莲花池该刷新了，路过可以采"
    assert "朵" not in sch.LOTUS_MSG and "6" not in sch.LOTUS_MSG
    marks = sch.lotus_marks()
    assert marks[:3] == [360, 720, 1080]
    h = lotus_pool_rule(_snap(360), None)
    assert h and h[0].message == sch.LOTUS_MSG
    assert lotus_pool_rule(_snap(360 - 15), None) == []  # no early warn


def test_defaults_by_position():
    assert st.default_on("bounty", [1]) is False
    assert st.default_on("bounty", [4]) is True
    assert st.default_on("runes", [2]) is True
    assert st.default_on("runes", [1]) is False
    assert st.default_on("lotus", [3]) is True
    assert st.default_on("lotus", [1]) is False
    # All rows visible (not pending)
    assert "lotus" not in st.PENDING
    assert "bounty" not in st.PENDING
    assert "runes" not in st.PENDING


def test_budget_caps_after_lotus():
    # Live meter == domain table now that every row has a rule:
    # pos1 16 / pos2 26 / pos3 16→20 / pos4·5 22→26 (shared rows: 神龛5 魔方2 肉山2 盾2 TP2 买活3).
    common = 5 + 2 + 2 + 2 + 2 + 3
    assert st.budget(st.defaults([1])["reminders"]) == common == 16
    assert st.budget(st.defaults([3])["reminders"]) == common + 4 == 20  # + lotus
    assert st.budget(st.defaults([4])["reminders"]) == common + 6 + 4 == 26  # + bounty + lotus
    assert st.budget(st.defaults([2])["reminders"]) == common + 10 == 26  # + water/power
    assert all(st.budget(st.defaults([p])["reminders"]) <= st.BUDGET_CAP for p in range(1, 6))


def test_engine_cooldown():
    store = GameStateStore()
    store.update(
        {
            "map": {
                "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
                "clock_time": 105,  # water warn
            }
        }
    )
    engine = ReminderEngine(store, cooldown_sec=60)
    first = engine.tick()
    second = engine.tick()
    assert first
    assert second == []


# ── catch-up, new objective rules, TP, buyback (domain/reminder-budget.md) ──
from dodoclaw.gsi.objectives import MatchEvents
from dodoclaw.gsi.state import parse_gsi_payload
from dodoclaw.reminders.rules import (
    NoTpRule,
    ObjectiveRule,
    buyback_ready_rule,
    default_rules,
    shrine_rule,
    tormentor_rule,
)

IN_GAME = "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"


def _p(clock: int, **extra) -> GameSnapshot:
    payload = {"map": {"matchid": "7", "game_state": IN_GAME, "clock_time": clock, "game_time": clock + 90}}
    payload.update(extra)
    return parse_gsi_payload(payload)


def test_skipped_second_still_fires_when_clock_jumps_over_warn_point():
    # packets at 1:43 then 1:47 — the 1:45 water warning used to be lost
    assert water_rune_rule(_p(107), _p(103))
    # ...but not a stale catch-up long after the point, and not across matches
    assert water_rune_rule(_p(150), _p(100)) == []
    other = parse_gsi_payload({"map": {"matchid": "8", "game_state": IN_GAME, "clock_time": 103}})
    assert water_rune_rule(_p(107), other) == []


def test_shrine_every_seven_minutes_warn_15s():
    assert [w.fire_at for w in sch.shrine_windows()][:3] == [405, 825, 1245]
    hit = shrine_rule(_snap(405), None)
    assert hit and hit[0].key == "shrine:420" and hit[0].message == "15 秒后智慧神龛"
    assert shrine_rule(_snap(420), None) == []


def test_tormentor_first_spawn_warn_30s():
    hit = tormentor_rule(_snap(870), None)
    assert hit and hit[0].key == "cube:900" and hit[0].message == "魔方 30 秒后刷新"
    assert tormentor_rule(_snap(1770), None) == []  # no respawn timing without a kill event


def _rosh(clock: int, killed_game_time: int) -> GameSnapshot:
    return _p(clock, events=[{"event_type": "roshan_killed", "game_time": killed_game_time}])


def test_roshan_warns_30s_before_earliest_respawn_from_event():
    rule = ObjectiveRule()  # keeps its own tracker
    assert rule(_rosh(1200, 1290), None) == []  # killed at 20:00 (game_time is +90)
    hits = rule(_rosh(1200 + 480 - 30, 1290), None)
    assert [h.key for h in hits] == ["roshan:1200"]
    assert hits[0].message == "肉山快复活了"
    assert "已经" not in hits[0].message  # GSI can't see him: never claim he is up


def test_aegis_warns_with_one_minute_left_and_denied_clears():
    ev = MatchEvents()
    rule = ObjectiveRule(ev)  # shared tracker, fed by the service
    snap = _p(1250, events=[{"event_type": "aegis_picked_up", "game_time": 1300}])  # picked 20:10
    ev.ingest(snap.raw)
    assert rule(_p(1210 + 240), None)[0].message == "盾还剩 1 分钟"  # 捡盾后 4:00
    ev.ingest(_p(1260, events=[{"event_type": "aegis_denied", "game_time": 1350}]).raw)
    assert rule(_p(1210 + 240), None) == []


def _items(tp: str | None, travel: bool = False) -> dict:
    items = {f"slot{i}": {"name": "empty"} for i in range(9)}
    if travel:
        items["slot0"] = {"name": "item_travel_boots"}
    items["teleport0"] = {"name": tp or "empty"}
    if tp:
        items["teleport0"]["charges"] = 1
    return {"items": items, "hero": {"name": "npc_dota_hero_axe", "alive": True}}


def test_no_tp_checked_at_ten_and_twenty_minutes_only():
    rule = NoTpRule()
    assert rule(_p(590, **_items(None)), None) == []  # before 10:00
    first = rule(_p(600, **_items(None)), None)
    assert first and first[0].key == "no_tp:600" and first[0].message == "身上没带回城卷轴，记得补一个"
    assert rule(_p(610, **_items(None)), None) == []  # checked once
    assert rule(_p(900, **_items(None)), None) == []  # no nagging between checks
    assert rule(_p(1201, **_items(None)), None)[0].key == "no_tp:1200"
    assert rule(_p(1800, **_items(None)), None) == []  # at most twice a game
    fresh = NoTpRule()
    assert fresh(_p(600, **_items("item_tpscroll")), None) == []
    assert fresh(_p(1200, **_items(None, travel=True)), None) == []  # Boots of Travel count
    dead = NoTpRule()
    corpse = _items(None)
    corpse["hero"]["alive"] = False
    assert dead(_p(600, **corpse), None) == []  # dead at 10:00: look again a bit later
    assert dead(_p(615, **_items(None)), None)
    no_slot = parse_gsi_payload({"map": {"matchid": "7", "game_state": IN_GAME, "clock_time": 600}})
    assert NoTpRule()(no_slot, None) == [] and no_slot.has_tp is None  # can't tell → stay quiet


def _bb(clock: int, *, alive=True, gold=3000, cost=2000, cd=0) -> GameSnapshot:
    return _p(
        clock,
        player={"gold": gold, "buyback_cost": cost, "buyback_cooldown": cd},
        hero={"name": "npc_dota_hero_axe", "alive": alive},
    )


def test_buyback_dead_prompt_only_late_game():
    assert buyback_ready_rule(_bb(300, alive=False, cost=200), None) == []  # 5:00 death
    hit = buyback_ready_rule(_bb(26 * 60, alive=False), None)
    assert hit and hit[0].key.startswith("buyback_while_dead")


def test_buyback_short_when_gold_drops_below_price():
    hit = buyback_ready_rule(_bb(30 * 60, gold=1500), _bb(30 * 60 - 1, gold=4000))
    assert hit and hit[0].key.startswith("buyback_short") and "买活" in hit[0].message
    assert buyback_ready_rule(_bb(10 * 60, gold=100, cost=500), _bb(599, gold=900, cost=500)) == []


def test_buyback_ready_after_cooldown_any_time_or_when_affordable_late():
    hit = buyback_ready_rule(_bb(900, cd=0), _bb(899, cd=3))
    assert hit and hit[0].key.startswith("buyback_ready")
    # late game: gold just reached the price
    hit = buyback_ready_rule(_bb(26 * 60, gold=2100), _bb(26 * 60 - 1, gold=1900))
    assert hit and hit[0].message == "买活可用了，关键团再考虑买活。"
    # early game: affording buyback is not news
    assert buyback_ready_rule(_bb(600, gold=600, cost=500), _bb(599, gold=400, cost=500)) == []


def test_engine_default_rules_use_shared_events():
    store = GameStateStore()
    ev = MatchEvents()
    engine = ReminderEngine(store, cooldown_sec=0, events=ev)
    assert any(isinstance(r, ObjectiveRule) and r.events is ev for r in engine.rules)
    assert len([r for r in default_rules() if isinstance(r, NoTpRule)]) == 1
    payload = {"map": {"matchid": "9", "game_state": IN_GAME, "clock_time": 1200, "game_time": 1290},
               "events": [{"event_type": "roshan_killed", "game_time": 1290}]}
    ev.ingest(payload)
    payload["map"] = {**payload["map"], "clock_time": 1650}
    store.update(payload)
    assert [e.key for e in engine.tick()] == ["roshan:1200"]


def test_paused_inside_fire_window_does_not_repeat(monkeypatch):
    import dodoclaw.reminders.engine as eng_mod

    now = [1000.0]
    monkeypatch.setattr(eng_mod.time, "time", lambda: now[0])
    store = GameStateStore()
    engine = ReminderEngine(store, cooldown_sec=25)
    payload = {"map": {"matchid": "5", "game_state": IN_GAME, "clock_time": 105}}
    store.update(payload)
    assert [e.key for e in engine.tick()] == ["water_rune:120"]
    for _ in range(5):  # paused at 1:45 for minutes: packets keep coming, clock doesn't move
        now[0] += 30
        store.update(payload)
        assert engine.tick() == []
    # a new match starts the once-per-match memory over
    store.update({"map": {"matchid": "6", "game_state": IN_GAME, "clock_time": 105}})
    now[0] += 30
    assert [e.key for e in engine.tick()] == ["water_rune:120"]


def test_dead_buyback_prompt_once_per_death():
    a = buyback_ready_rule(_p(1600, player={"gold": 5000, "buyback_cost": 2000, "deaths": 3},
                              hero={"alive": False}), None)
    b = buyback_ready_rule(_p(1640, player={"gold": 5000, "buyback_cost": 2000, "deaths": 3},
                              hero={"alive": False}), None)
    assert a[0].key == b[0].key == "buyback_while_dead:3"
