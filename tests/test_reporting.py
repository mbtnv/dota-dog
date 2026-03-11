from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dota_dog.domain.enums import PeriodType
from dota_dog.domain.models import MatchSnapshot, TrackedPlayerRef
from dota_dog.services.reporting import ReportingService


def _match(match_id: int, is_win: bool, hero_id: int, ended_at: datetime) -> MatchSnapshot:
    start = ended_at - timedelta(minutes=30)
    radiant_win = True
    player_slot = 0 if is_win else 128
    return MatchSnapshot(
        player_id=1,
        match_id=match_id,
        start_time=start,
        end_time=ended_at,
        hero_id=hero_id,
        radiant_win=radiant_win,
        player_slot=player_slot,
        kills=10,
        deaths=5,
        assists=7,
        gpm=600,
        xpm=700,
        hero_damage=10000,
        tower_damage=3000,
        hero_healing=500,
        last_hits=200,
        game_mode=22,
        lobby_type=7,
        party_size=1,
        raw_payload={},
    )


def test_build_summary_calculates_winrate_and_streaks() -> None:
    service = ReportingService()
    period_start = datetime(2026, 3, 1, tzinfo=UTC)
    period_end = datetime(2026, 4, 1, tzinfo=UTC)
    matches = [
        _match(1, True, 1, datetime(2026, 3, 2, tzinfo=UTC)),
        _match(2, True, 1, datetime(2026, 3, 3, tzinfo=UTC)),
        _match(3, False, 74, datetime(2026, 3, 4, tzinfo=UTC)),
    ]

    summary = service.build_summary(
        player_id=1,
        label="Invoker spammer",
        period_type=PeriodType.MONTH,
        period_start=period_start,
        period_end=period_end,
        matches=matches,
    )

    assert summary.matches_count == 3
    assert summary.wins == 2
    assert summary.losses == 1
    assert round(summary.winrate, 2) == 66.67
    assert summary.best_streak == 2
    assert summary.worst_streak == 1
    assert summary.top_heroes[0] == (1, 2)


def test_build_topic_summaries_filters_by_alias() -> None:
    service = ReportingService()
    period_start = datetime(2026, 3, 1, tzinfo=UTC)
    period_end = datetime(2026, 4, 1, tzinfo=UTC)
    players = [
        TrackedPlayerRef(1, 111, "Sega", None, "mid", 10),
        TrackedPlayerRef(2, 222, "BIGBABY", None, "carry", 20),
    ]
    matches = [
        _match(1, True, 1, datetime(2026, 3, 2, tzinfo=UTC)),
        MatchSnapshot(
            player_id=2,
            match_id=2,
            start_time=datetime(2026, 3, 3, tzinfo=UTC),
            end_time=datetime(2026, 3, 3, 0, 30, tzinfo=UTC),
            hero_id=74,
            radiant_win=True,
            player_slot=128,
            kills=1,
            deaths=8,
            assists=3,
            gpm=350,
            xpm=450,
            hero_damage=5000,
            tower_damage=1000,
            hero_healing=0,
            last_hits=90,
            game_mode=23,
            lobby_type=0,
            party_size=2,
            raw_payload={},
        ),
    ]

    summaries = service.build_topic_summaries(
        period_type=PeriodType.MONTH,
        period_start=period_start,
        period_end=period_end,
        players=players,
        matches=matches,
        player_filter="mid",
    )

    assert len(summaries) == 1
    assert summaries[0].label == "mid"
