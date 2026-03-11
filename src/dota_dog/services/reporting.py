from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from dota_dog.domain.enums import PeriodType
from dota_dog.domain.models import MatchSnapshot, ReportSummary, TrackedPlayerRef


class ReportingService:
    def calculate_period_bounds(
        self, period_type: PeriodType, now: datetime, timezone_name: str
    ) -> tuple[datetime, datetime]:
        tz = ZoneInfo(timezone_name)
        local_now = now.astimezone(tz)
        if period_type == PeriodType.DAY:
            local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            local_end = local_start + timedelta(days=1)
        elif period_type == PeriodType.WEEK:
            local_start = (local_now - timedelta(days=local_now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            local_end = local_start + timedelta(days=7)
        else:
            local_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if local_start.month == 12:
                local_end = local_start.replace(year=local_start.year + 1, month=1)
            else:
                local_end = local_start.replace(month=local_start.month + 1)
        return local_start.astimezone(UTC), local_end.astimezone(UTC)

    def previous_period_bounds(
        self, period_type: PeriodType, now: datetime, timezone_name: str
    ) -> tuple[datetime, datetime]:
        current_start, current_end = self.calculate_period_bounds(period_type, now, timezone_name)
        if period_type == PeriodType.MONTH:
            tz = ZoneInfo(timezone_name)
            current_local_start = current_start.astimezone(tz)
            previous_local_end = current_local_start
            if current_local_start.month == 1:
                previous_local_start = current_local_start.replace(
                    year=current_local_start.year - 1,
                    month=12,
                )
            else:
                previous_local_start = current_local_start.replace(
                    month=current_local_start.month - 1,
                )
            return previous_local_start.astimezone(UTC), previous_local_end.astimezone(UTC)
        duration = current_end - current_start
        return current_start - duration, current_start

    def build_summary(
        self,
        *,
        player_id: int,
        label: str,
        period_type: PeriodType,
        period_start: datetime,
        period_end: datetime,
        matches: list[MatchSnapshot],
    ) -> ReportSummary:
        if not matches:
            return ReportSummary(
                player_id=player_id,
                label=label,
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                matches_count=0,
                wins=0,
                losses=0,
                winrate=0.0,
                avg_kills=0.0,
                avg_deaths=0.0,
                avg_assists=0.0,
                avg_gpm=0.0,
                avg_xpm=0.0,
                avg_duration_minutes=0.0,
                avg_hero_damage=0.0,
                best_streak=0,
                worst_streak=0,
                top_heroes=[],
            )

        wins = sum(1 for match in matches if match.is_win)
        losses = len(matches) - wins
        hero_counts = Counter(match.hero_id for match in matches)
        best_streak, worst_streak = self._calculate_streaks(matches)
        total_duration_minutes = sum(match.duration.total_seconds() / 60 for match in matches)
        return ReportSummary(
            player_id=player_id,
            label=label,
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
            matches_count=len(matches),
            wins=wins,
            losses=losses,
            winrate=(wins / len(matches)) * 100,
            avg_kills=sum(match.kills for match in matches) / len(matches),
            avg_deaths=sum(match.deaths for match in matches) / len(matches),
            avg_assists=sum(match.assists for match in matches) / len(matches),
            avg_gpm=sum(match.gpm for match in matches) / len(matches),
            avg_xpm=sum(match.xpm for match in matches) / len(matches),
            avg_duration_minutes=total_duration_minutes / len(matches),
            avg_hero_damage=sum(match.hero_damage for match in matches) / len(matches),
            best_streak=best_streak,
            worst_streak=worst_streak,
            top_heroes=hero_counts.most_common(3),
        )

    def build_topic_summaries(
        self,
        *,
        period_type: PeriodType,
        period_start: datetime,
        period_end: datetime,
        players: list[TrackedPlayerRef],
        matches: list[MatchSnapshot],
        player_filter: str | None = None,
    ) -> list[ReportSummary]:
        selected_players = self.select_players(players, player_filter)
        summaries: list[ReportSummary] = []
        for player in selected_players:
            player_matches = [match for match in matches if match.player_id == player.player_id]
            summaries.append(
                self.build_summary(
                    player_id=player.player_id,
                    label=player.alias or player.display_name,
                    period_type=period_type,
                    period_start=period_start,
                    period_end=period_end,
                    matches=player_matches,
                )
            )
        return summaries

    @staticmethod
    def select_players(
        players: list[TrackedPlayerRef],
        player_filter: str | None,
    ) -> list[TrackedPlayerRef]:
        if player_filter is None:
            return players
        for player in players:
            if player.alias == player_filter or str(player.dota_account_id) == player_filter:
                return [player]
        return []

    @staticmethod
    def _calculate_streaks(matches: list[MatchSnapshot]) -> tuple[int, int]:
        ordered = sorted(matches, key=lambda item: item.end_time)
        best_streak = 0
        worst_streak = 0
        current_win = 0
        current_loss = 0
        for match in ordered:
            if match.is_win:
                current_win += 1
                current_loss = 0
            else:
                current_loss += 1
                current_win = 0
            best_streak = max(best_streak, current_win)
            worst_streak = max(worst_streak, current_loss)
        return best_streak, worst_streak
