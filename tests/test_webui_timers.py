from dodoclaw.webui.icons import IconCache
from dodoclaw.webui.timers import MatchTimers


def _keys(ts):
    return {t["key"]: t for t in ts}


def test_shrine_and_cube_countdown():
    mt = MatchTimers()
    t = _keys(mt.compute(400))
    assert t["shrine"]["remain"] == 20
    assert t["cube"]["remain"] == 500
    t = _keys(mt.compute(901))
    assert "cube" not in t
    assert t["shrine"]["remain"] == 1260 - 901


def test_roshan_and_aegis_from_events():
    mt = MatchTimers()
    mt.ingest({
        "map": {"matchid": "42", "clock_time": 1200, "game_time": 1200},
        "events": [
            {"event_type": "roshan_killed", "game_time": 1200},
            {"event_type": "aegis_picked_up", "game_time": 1201},
        ],
    })
    t = _keys(mt.compute(1200 + 460))
    assert t["roshan"]["remain"] == 20 and t["roshan"]["hot"]
    assert "aegis" not in t
    t = _keys(mt.compute(1201 + 250))
    assert t["aegis"]["hot"] and t["aegis"]["remain"] == 50
    mt.ingest({"map": {"matchid": "43"}})
    assert "roshan" not in _keys(mt.compute(1300))


def test_icon_key_normalize():
    assert IconCache.normalize("heroes", "npc_dota_hero_axe") == ("heroes", "axe")
    assert IconCache.normalize("items", "item_black_king_bar") == ("items", "black_king_bar")
    assert IconCache.normalize("items", "../etc") is None
    assert IconCache.normalize("bad", "axe") is None


def test_event_game_time_converted_to_clock_axis():
    from dodoclaw.webui.timers import MatchTimers

    t = MatchTimers()
    # 90 s of pre-horn time: game_time = clock_time + 90
    t.ingest({"map": {"matchid": "1", "clock_time": 1200, "game_time": 1290},
              "events": [{"event_type": "roshan_killed", "game_time": 1290},
                         {"event_type": "aegis_picked_up", "game_time": 1292}]})
    assert t.roshan_killed_at == 1200
    assert t.aegis_at == 1202
    rows = {r["key"]: r for r in t.compute(1200 + 60)}
    assert rows["roshan"]["remain"] == 480 - 60
    assert rows["aegis"]["remain"] == 300 - 58


def test_event_without_time_uses_arrival_clock():
    from dodoclaw.webui.timers import MatchTimers

    t = MatchTimers()
    t.ingest({"map": {"matchid": "1", "clock_time": 1500},
              "events": [{"event_type": "roshan_killed"}]})
    assert t.roshan_killed_at == 1500
