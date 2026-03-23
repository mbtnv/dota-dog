from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from dota_dog.domain.models import MatchSnapshot


@dataclass(frozen=True, slots=True)
class MatchStatistic:
    key: str
    label: str
    value: str
    raw_value: float | int | None = None


class MatchStatisticCalculator(Protocol):
    key: str
    label: str

    def calculate(self, match: MatchSnapshot) -> MatchStatistic | None: ...


class GovnoedstvoCalculator:
    key = "govnoedstvo"
    label = "Govnoedstvo"

    def calculate(self, match: MatchSnapshot) -> MatchStatistic:
        value = self.calculate_percent(
            kills=match.kills,
            deaths=match.deaths,
            assists=match.assists,
        )
        return MatchStatistic(
            key=self.key,
            label=self.label,
            value=f"{value}%",
            raw_value=value,
        )

    @staticmethod
    def calculate_percent(kills: int, deaths: int, assists: int) -> int:
        # Deaths are weighed heavier so "a lot of deaths even with assists"
        # still reads as a bad game in the post-match message.
        impact_score = kills + assists - (deaths * 1.25)
        normalized_score = min(max(impact_score / 15, 0.0), 1.0)
        return round((1 - normalized_score) * 100)


class MatchStatisticsService:
    """Registry for derived per-match stats shown in notifications.

    Keeping calculators outside the formatter makes it easier to add more
    rule-based metrics now and swap in model-backed calculators later.
    """

    def __init__(
        self,
        calculators: Iterable[MatchStatisticCalculator] | None = None,
    ) -> None:
        self._calculators = tuple(calculators or (GovnoedstvoCalculator(),))

    def calculate_custom_statistics(self, match: MatchSnapshot) -> list[MatchStatistic]:
        statistics: list[MatchStatistic] = []
        for calculator in self._calculators:
            statistic = calculator.calculate(match)
            if statistic is not None:
                statistics.append(statistic)
        return statistics
