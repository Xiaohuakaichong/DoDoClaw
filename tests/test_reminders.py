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
    # App budget excludes PENDING rows (神龛/魔方/…). Implemented: bounty/runes/lotus/buyback.
    # Domain table (with pending) is pos3 16→20 / pos4·5 22→26; here we assert the live meter.
    d3 = st.defaults([3])
    assert st.budget(d3["reminders"]) == 7  # lotus4 + buyback3
    d4 = st.defaults([4])
    assert st.budget(d4["reminders"]) == 13  # bounty6 + lotus4 + buyback3
    d2 = st.defaults([2])
    assert st.budget(d2["reminders"]) == 13  # runes10 + buyback3
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
