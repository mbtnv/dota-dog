from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dota_dog.domain.models import MatchSnapshot
from dota_dog.services.match_statistics import (
    GovnoedstvoCalculator,
    MatchStatistic,
    MatchStatisticsService,
)


def make_match_snapshot(
    *,
    kills: int = 5,
    deaths: int = 5,
    assists: int = 10,
) -> MatchSnapshot:
    ended_at = datetime(2026, 3, 10, 15, 0, tzinfo=UTC)
    return MatchSnapshot(
        player_id=1,
        match_id=999,
        start_time=ended_at - timedelta(minutes=35),
        end_time=ended_at,
        hero_id=74,
        radiant_win=True,
        player_slot=0,
        kills=kills,
        deaths=deaths,
        assists=assists,
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


@pytest.mark.parametrize(
    ("kills", "deaths", "assists", "expected_percent"),
    [
        (0, 6, 1, 100),
        (0, 10, 11, 100),
        (1, 14, 1, 100),
        (12, 2, 26, 0),
        (9, 2, 12, 0),
        (15, 8, 27, 0),
        (5, 5, 10, 42),
    ],
)
def test_govnoedstvo_calculator_uses_kda_balance(
    kills: int,
    deaths: int,
    assists: int,
    expected_percent: int,
) -> None:
    assert GovnoedstvoCalculator.calculate_percent(kills, deaths, assists) == expected_percent


def test_match_statistics_service_returns_default_custom_statistic() -> None:
    statistics = MatchStatisticsService().calculate_custom_statistics(
        make_match_snapshot(kills=12, deaths=1, assists=9)
    )

    assert statistics == [
        MatchStatistic(
            key="govnoedstvo",
            label="Govnoedstvo",
            value="0%",
            raw_value=0,
        )
    ]


def test_match_statistics_service_supports_custom_calculator_registration() -> None:
    class DummyCalculator:
        key = "dummy"
        label = "Dummy"

        def calculate(self, match: MatchSnapshot) -> MatchStatistic:
            return MatchStatistic(
                key=self.key,
                label=self.label,
                value=f"{match.last_hits} lh",
                raw_value=match.last_hits,
            )

    statistics = MatchStatisticsService(
        calculators=[DummyCalculator()]
    ).calculate_custom_statistics(make_match_snapshot())

    assert statistics == [
        MatchStatistic(
            key="dummy",
            label="Dummy",
            value="320 lh",
            raw_value=320,
        )
    ]
