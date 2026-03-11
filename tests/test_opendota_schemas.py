from __future__ import annotations

from dota_dog.infra.opendota.schemas import OpenDotaPlayerMatch


def test_player_match_allows_missing_optional_metrics() -> None:
    match = OpenDotaPlayerMatch.model_validate(
        {
            "match_id": 8724273727,
            "player_slot": 128,
            "radiant_win": False,
            "duration": 2156,
            "game_mode": 22,
            "lobby_type": 7,
            "hero_id": 74,
            "start_time": 1_741_427_200,
            "kills": 8,
            "deaths": 7,
            "assists": 11,
            "party_size": None,
        }
    )

    assert match.xp_per_min == 0
    assert match.gold_per_min == 0
    assert match.hero_damage == 0
    assert match.tower_damage == 0
    assert match.hero_healing == 0
    assert match.last_hits == 0
