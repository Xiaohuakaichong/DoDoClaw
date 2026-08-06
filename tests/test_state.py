from dodoclaw.gsi.state import parse_gsi_payload


def test_parse_basic_payload():
    payload = {
        "map": {
            "name": "start",
            "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "clock_time": 372,
            "daytime": True,
            "matchid": "123",
        },
        "player": {
            "name": "Tester",
            "team_name": "radiant",
            "gold": 1200,
            "gold_reliable": 400,
            "gold_unreliable": 800,
            "gpm": 450,
            "xpm": 500,
            "kills": 2,
            "deaths": 1,
            "assists": 3,
            "last_hits": 40,
            "denies": 5,
            "buyback_cost": 900,
            "buyback_cooldown": 0,
        },
        "hero": {
            "name": "npc_dota_hero_axe",
            "level": 12,
            "alive": True,
            "health": 800,
            "max_health": 1600,
            "mana": 200,
            "max_mana": 400,
        },
        "abilities": {
            "ability0": {"name": "axe_berserkers_call", "cooldown": 0, "ultimate": False},
            "ability5": {"name": "axe_culling_blade", "cooldown": 40, "ultimate": True, "level": 2},
        },
        "items": {
            "slot0": {"name": "item_blink"},
            "slot1": {"name": "item_black_king_bar"},
        },
        "auth": {"token": "dodoclaw_secret"},
    }
    snap = parse_gsi_payload(payload)
    assert snap.clock_time == 372
    assert snap.clock_mmss == "06:12"
    assert snap.hero_name == "npc_dota_hero_axe"
    assert snap.gold == 1200
    assert "axe" in snap.summary_for_llm().lower() or "npc_dota_hero_axe" in snap.summary_for_llm()
    assert any(i.get("name") == "item_blink" for i in snap.items)
