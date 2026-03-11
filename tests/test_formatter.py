from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dota_dog.domain.models import MatchSnapshot, TrackedPlayerRef
from dota_dog.services.formatter import MessageFormatter


def test_format_match_notification_contains_required_fields() -> None:
    formatter = MessageFormatter()
    player = TrackedPlayerRef(
        player_id=1,
        dota_account_id=123,
        display_name="Sega",
        profile_url=None,
        alias="mid",
        last_seen_match_id=1,
    )
    ended_at = datetime(2026, 3, 10, 15, 0, tzinfo=UTC)
    match = MatchSnapshot(
        player_id=1,
        match_id=999,
        start_time=ended_at - timedelta(minutes=35),
        end_time=ended_at,
        hero_id=74,
        radiant_win=True,
        player_slot=0,
        kills=12,
        deaths=1,
        assists=9,
        gpm=700,
        xpm=800,
        hero_damage=23000,
        tower_damage=5000,
        hero_healing=0,
        last_hits=320,
        game_mode=22,
        lobby_type=7,
        party_size=2,
        raw_payload={},
    )

    message = formatter.format_match_notification(player, match)

    assert "mid" in message
    assert "Invoker" in message
    assert "KDA: 12/1/9" in message
    assert "Dotabuff" in message
