from __future__ import annotations

from dota_dog.infra.opendota.schemas import OpenDotaRecentMatch
from dota_dog.services.tracking import TrackingService


def test_build_match_snapshots_filters_by_last_seen_match_id() -> None:
    service = TrackingService()
    recent_matches = [
        OpenDotaRecentMatch(
            match_id=100,
            player_slot=0,
            radiant_win=True,
            duration=1200,
            game_mode=22,
            lobby_type=7,
            hero_id=1,
            start_time=1_700_000_000,
            kills=10,
            deaths=2,
            assists=5,
            xp_per_min=500,
            gold_per_min=600,
            hero_damage=10000,
            tower_damage=5000,
            hero_healing=1000,
            last_hits=250,
            party_size=1,
        ),
        OpenDotaRecentMatch(
            match_id=101,
            player_slot=0,
            radiant_win=False,
            duration=1400,
            game_mode=23,
            lobby_type=0,
            hero_id=74,
            start_time=1_700_100_000,
            kills=5,
            deaths=8,
            assists=9,
            xp_per_min=450,
            gold_per_min=480,
            hero_damage=9000,
            tower_damage=2000,
            hero_healing=0,
            last_hits=180,
            party_size=2,
        ),
    ]

    snapshots = service.build_match_snapshots(
        player_id=1,
        recent_matches=recent_matches,
        last_seen_match_id=100,
    )

    assert [snapshot.match_id for snapshot in snapshots] == [101]
