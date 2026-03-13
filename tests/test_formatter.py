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
    assert "🟢<b>Win</b>" in message
    assert "Invoker" in message
    assert "<b>KDA</b>: 12/1/9" in message
    assert "<b>GPM/XPM</b>: 700 / 800" in message
    assert "<b>HD/TD/HH</b>: 23.0K / 5.0K / 0.0K" in message
    assert "Dotabuff" in message


def test_format_recent_matches_groups_shared_players_into_one_block() -> None:
    formatter = MessageFormatter()
    ended_at = datetime(2026, 3, 10, 15, 0, tzinfo=UTC)
    bigbaby = TrackedPlayerRef(
        player_id=1,
        dota_account_id=111,
        display_name="BIGBABY",
        profile_url=None,
        alias="BIGBABY",
        last_seen_match_id=1,
    )
    sega = TrackedPlayerRef(
        player_id=2,
        dota_account_id=222,
        display_name="Sega",
        profile_url=None,
        alias="sega",
        last_seen_match_id=1,
    )
    shared_match = [
        (
            bigbaby,
            MatchSnapshot(
                player_id=1,
                match_id=999,
                start_time=ended_at - timedelta(minutes=35),
                end_time=ended_at,
                hero_id=74,
                radiant_win=False,
                player_slot=0,
                kills=12,
                deaths=10,
                assists=9,
                gpm=425,
                xpm=700,
                hero_damage=23000,
                tower_damage=1687,
                hero_healing=0,
                last_hits=185,
                game_mode=22,
                lobby_type=7,
                party_size=2,
                raw_payload={},
            ),
        ),
        (
            sega,
            MatchSnapshot(
                player_id=2,
                match_id=999,
                start_time=ended_at - timedelta(minutes=35),
                end_time=ended_at,
                hero_id=5,
                radiant_win=False,
                player_slot=0,
                kills=3,
                deaths=7,
                assists=18,
                gpm=320,
                xpm=510,
                hero_damage=9000,
                tower_damage=500,
                hero_healing=1200,
                last_hits=55,
                game_mode=22,
                lobby_type=7,
                party_size=2,
                raw_payload={},
            ),
        ),
    ]

    message = formatter.format_recent_matches("Last matches", [shared_match])

    assert "BIGBABY" in message
    assert "sega" in message
    assert "🔴<b>Lose</b>" in message
    assert "Crystal Maiden" in message
    assert "<b>GPM/XPM</b>: 425 / 700" in message
    assert "<b>HD/TD/HH</b>: 23.0K / 1.7K / 0.0K" in message
    assert message.count("<b>Ended</b>:") == 1
    assert message.count("Dotabuff") == 1


def test_format_match_notification_uses_all_pick_for_game_mode_22_without_constants() -> None:
    formatter = MessageFormatter()
    player = TrackedPlayerRef(
        player_id=1,
        dota_account_id=123,
        display_name="Sega",
        profile_url=None,
        alias="Sega",
        last_seen_match_id=1,
    )
    ended_at = datetime(2026, 3, 13, 8, 41, tzinfo=UTC)
    match = MatchSnapshot(
        player_id=1,
        match_id=1001,
        start_time=ended_at - timedelta(minutes=26),
        end_time=ended_at,
        hero_id=14,
        radiant_win=True,
        player_slot=0,
        kills=3,
        deaths=3,
        assists=8,
        gpm=485,
        xpm=449,
        hero_damage=10856,
        tower_damage=3927,
        hero_healing=0,
        last_hits=137,
        game_mode=22,
        lobby_type=7,
        party_size=None,
        raw_payload={},
    )

    message = formatter.format_match_notification(player, match)

    assert "<b>Mode</b>: All Pick · Ranked" in message


def test_format_match_notification_uses_requested_timezone() -> None:
    formatter = MessageFormatter()
    player = TrackedPlayerRef(
        player_id=1,
        dota_account_id=123,
        display_name="Sega",
        profile_url=None,
        alias="Sega",
        last_seen_match_id=1,
    )
    ended_at = datetime(2026, 3, 13, 8, 41, tzinfo=UTC)
    match = MatchSnapshot(
        player_id=1,
        match_id=1001,
        start_time=ended_at - timedelta(minutes=26),
        end_time=ended_at,
        hero_id=14,
        radiant_win=True,
        player_slot=0,
        kills=3,
        deaths=3,
        assists=8,
        gpm=485,
        xpm=449,
        hero_damage=10856,
        tower_damage=3927,
        hero_healing=0,
        last_hits=137,
        game_mode=22,
        lobby_type=7,
        party_size=None,
        raw_payload={},
    )

    message = formatter.format_match_notification(
        player,
        match,
        timezone_name="Europe/Moscow",
    )

    assert "<b>Ended</b>: 2026-03-13 11:41 MSK (26 min)" in message
