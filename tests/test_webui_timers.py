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
        "map": {"matchid": "42"},
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
