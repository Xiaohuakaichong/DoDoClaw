from dodoclaw.gsi.state import parse_gsi_payload
from dodoclaw.meta.bp_board import build_bp_board
from dodoclaw.meta.opendota import OpenDotaClient


class _FakeClient:
    source_name = "fake"

    def get_meta(self, force=False):
        # reuse real OpenDota cache if available; else minimal
        try:
            return OpenDotaClient(cache_ttl_sec=86400 * 30).get_meta()
        except Exception:
            from dodoclaw.meta.base import HeroMeta, MetaSnapshot

            snap = MetaSnapshot(source="fake")
            for i, name in enumerate(
                ["Axe", "Pudge", "Invoker", "Crystal Maiden", "Anti-Mage"], start=1
            ):
                hm = HeroMeta(
                    hero_id=i,
                    name=f"npc_dota_hero_{name.lower().replace(' ', '_')}",
                    localized_name=name,
                    roles=["Carry"] if i == 5 else ["Support"],
                    picks=1000 + i * 10,
                    wins=520 + i,
                    pro_ban=50 - i,
                    pro_pick=40,
                )
                hm._pick_share = 0.05
                snap.heroes[i] = hm
                snap.by_name[hm.name.lower()] = hm
                snap.by_localized[name.lower()] = hm
            return snap

    def top_bans(self, n=15, use_pro=True):
        m = self.get_meta()
        return list(m.heroes.values())[:n]

    def top_picks(self, n=20, use_pro=False):
        m = self.get_meta()
        return sorted(m.heroes.values(), key=lambda h: h.picks, reverse=True)[:n]

    def counters_for(self, enemy_hero_id, n=8):
        m = self.get_meta()
        others = [h for h in m.heroes.values() if h.hero_id != enemy_hero_id][:n]
        return [(h, 0.6) for h in others]

    def get_matchups(self, hero_id, force=False):
        m = self.get_meta()
        return [
            {"hero_id": h.hero_id, "games_played": 100, "wins": 60}
            for h in m.heroes.values()
            if h.hero_id != hero_id
        ][:8]

    def top_by_position(self, position, n=10):
        return self.top_picks(n=n)


def test_build_bp_board_basic():
    payload = {
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION", "clock_time": -20},
        "player": {"team_name": "radiant", "name": "me"},
        "draft": {
            "team2": {"pick0_id": "npc_dota_hero_axe", "ban0_id": "npc_dota_hero_invoker"},
            "team3": {"pick0_id": "npc_dota_hero_pudge"},
        },
    }
    snap = parse_gsi_payload(payload)
    board = build_bp_board(_FakeClient(), snap, top_n=5)
    assert board.ally_picks or board.enemy_picks
    assert board.ban_priority is not None
    assert board.pick_hot is not None
    assert isinstance(board.lanes, list)
