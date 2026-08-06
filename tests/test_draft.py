from dodoclaw.gsi.state import GameSnapshot, parse_gsi_payload
from dodoclaw.meta.draft import parse_draft_from_snapshot


def test_parse_draft_team_blocks():
    payload = {
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION", "clock_time": -30},
        "player": {"team_name": "radiant", "name": "me"},
        "draft": {
            "team2": {
                "pick0_id": "npc_dota_hero_axe",
                "pick1_id": "npc_dota_hero_crystal_maiden",
                "ban0_id": "npc_dota_hero_invoker",
            },
            "team3": {
                "pick0_id": "npc_dota_hero_pudge",
                "ban0_id": "npc_dota_hero_meepo",
            },
        },
    }
    snap = parse_gsi_payload(payload)
    assert snap.is_draft_phase
    ctx = parse_draft_from_snapshot(snap)
    assert ctx.is_draft
    assert "axe" in ",".join(ctx.radiant_picks).lower() or any(
        "axe" in p.lower() for p in ctx.radiant_picks
    )
    assert ctx.enemy_picks()  # dire as enemy when radiant


def test_summary_without_gsi():
    snap = GameSnapshot()
    ctx = parse_draft_from_snapshot(snap)
    assert "不在 BP" in ctx.summary_text() or "尚未" in ctx.summary_text() or ctx.phase