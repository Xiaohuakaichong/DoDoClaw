from dodoclaw.gsi.state import GameSnapshot, GameStateStore
from dodoclaw.reminders.engine import ReminderEngine
from dodoclaw.reminders.rules import power_rune_rule


def test_power_rune_at_six_min():
    snap = GameSnapshot(
        game_state="DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
        clock_time=360,
    )
    hits = power_rune_rule(snap, None)
    assert hits
    assert "神符" in hits[0].message


def test_engine_cooldown():
    store = GameStateStore()
    # inject snapshot
    store.update(
        {
            "map": {
                "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
                "clock_time": 360,
            }
        }
    )
    engine = ReminderEngine(store, cooldown_sec=60)
    first = engine.tick()
    second = engine.tick()
    assert first
    assert second == []
