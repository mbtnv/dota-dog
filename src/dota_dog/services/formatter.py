from __future__ import annotations

from datetime import UTC
from html import escape

from dota_dog.domain.models import ConstantSnapshot, MatchSnapshot, ReportSummary, TrackedPlayerRef

HERO_NAMES = {
    1: "Anti-Mage",
    5: "Crystal Maiden",
    74: "Invoker",
    138: "Muerta",
}

GAME_MODES = {
    1: "All Pick",
    2: "Captains Mode",
    22: "All Pick",
    23: "Turbo",
}

LOBBY_TYPES = {
    0: "Normal",
    7: "Ranked",
    9: "Battle Cup",
}


def dotabuff_match_url(match_id: int) -> str:
    return f"https://www.dotabuff.com/matches/{match_id}"


def dotabuff_profile_url(account_id: int) -> str:
    return f"https://www.dotabuff.com/players/{account_id}"


class MessageFormatter:
    def format_match_notification(
        self,
        player: TrackedPlayerRef,
        match: MatchSnapshot,
        constants: ConstantSnapshot | None = None,
    ) -> str:
        profile_url = player.profile_url or dotabuff_profile_url(player.dota_account_id)
        hero = self._hero_name(match.hero_id, constants)
        outcome = self._format_outcome(match.is_win)
        ended_at = match.end_time.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
        duration_minutes = int(match.duration.total_seconds() // 60)
        parts = [
            f"<b>{escape(player.alias or player.display_name)}</b> · "
            f'<a href="{escape(profile_url)}">profile</a>',
            f"{outcome} · {escape(hero)}",
            f"<b>KDA</b>: {match.kills}/{match.deaths}/{match.assists}",
            f"<b>Ended</b>: {ended_at} ({duration_minutes} min)",
            f"<b>GPM/XPM</b>: {match.gpm} / {match.xpm}",
            f"<b>HD/TD/HH</b>: {self._format_k_value(match.hero_damage)} / "
            f"{self._format_k_value(match.tower_damage)} / "
            f"{self._format_k_value(match.hero_healing)}",
            f"<b>Last hits</b>: {match.last_hits}",
            f"<b>Mode</b>: {self._game_mode_name(match.game_mode, constants)} · "
            f"{self._lobby_type_name(match.lobby_type, constants)}"
            f"{self._format_party(match.party_size)}",
            f'<a href="{dotabuff_match_url(match.match_id)}">Dotabuff</a>',
        ]
        return "\n".join(parts)

    def format_report(
        self,
        summary: ReportSummary,
        constants: ConstantSnapshot | None = None,
    ) -> str:
        top_heroes = ", ".join(
            f"{self._hero_name(hero_id, constants)} x{count}"
            for hero_id, count in summary.top_heroes
        )
        return (
            f"<b>{escape(summary.label)}</b> · {summary.period_type.value}\n"
            f"Matches: {summary.matches_count} | "
            f"W/L: {summary.wins}/{summary.losses} | "
            f"WR: {summary.winrate:.2f}%\n"
            f"K/D/A avg: {summary.avg_kills:.2f}/"
            f"{summary.avg_deaths:.2f}/"
            f"{summary.avg_assists:.2f}\n"
            f"GPM/XPM avg: {summary.avg_gpm:.2f}/{summary.avg_xpm:.2f}\n"
            f"Avg duration: {summary.avg_duration_minutes:.2f} min\n"
            f"Avg hero damage: {summary.avg_hero_damage:.2f}\n"
            f"Best/Worst streak: {summary.best_streak}/{summary.worst_streak}\n"
            f"Top heroes: {escape(top_heroes or 'n/a')}"
        )

    def format_report_bundle(
        self,
        title: str,
        summaries: list[ReportSummary],
        constants: ConstantSnapshot | None = None,
    ) -> str:
        header = f"<b>{escape(title)}</b>"
        if not summaries:
            return f"{header}\nNo data."
        return f"{header}\n\n" + "\n\n".join(
            self.format_report(summary, constants) for summary in summaries
        )

    def format_recent_matches(
        self,
        title: str,
        items: list[list[tuple[TrackedPlayerRef, MatchSnapshot]]],
        constants: ConstantSnapshot | None = None,
    ) -> str:
        header = f"<b>{escape(title)}</b>"
        if not items:
            return f"{header}\nNo matches."
        body = "\n\n".join(self._format_recent_match_group(group, constants) for group in items)
        return f"{header}\n\n{body}"

    def format_leaderboard(self, title: str, summaries: list[ReportSummary]) -> str:
        header = f"<b>{escape(title)}</b>"
        if not summaries:
            return f"{header}\nNo data."
        lines = [header]
        for index, summary in enumerate(summaries, start=1):
            lines.append(
                f"{index}. {escape(summary.label)} | "
                f"matches {summary.matches_count} | "
                f"W {summary.wins} | WR {summary.winrate:.2f}%"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_party(party_size: int | None) -> str:
        if party_size is None:
            return ""
        if party_size == 1:
            return " · Solo"
        return f" · Party {party_size}"

    def _format_recent_match_group(
        self,
        group: list[tuple[TrackedPlayerRef, MatchSnapshot]],
        constants: ConstantSnapshot | None,
    ) -> str:
        first_match = group[0][1]
        ended_at = first_match.end_time.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
        duration_minutes = int(first_match.duration.total_seconds() // 60)
        labels = ", ".join(escape(player.alias or player.display_name) for player, _ in group)
        parts = [
            f"<b>{labels}</b>",
            f"<b>Ended</b>: {ended_at} ({duration_minutes} min)",
            f"<b>Mode</b>: {self._game_mode_name(first_match.game_mode, constants)} · "
            f"{self._lobby_type_name(first_match.lobby_type, constants)}",
        ]
        for player, match in group:
            profile_url = player.profile_url or dotabuff_profile_url(player.dota_account_id)
            hero = self._hero_name(match.hero_id, constants)
            outcome = self._format_outcome(match.is_win)
            parts.append(
                f"<b>{escape(player.alias or player.display_name)}</b> · "
                f'<a href="{escape(profile_url)}">profile</a> · '
                f"{outcome} · {escape(hero)}"
                f"{self._format_party(match.party_size)}"
            )
            parts.append(
                f"<b>KDA</b>: {match.kills}/{match.deaths}/{match.assists} | "
                f"<b>GPM/XPM</b>: {match.gpm} / {match.xpm} | "
                f"<b>Last hits</b>: {match.last_hits}"
            )
            parts.append(
                f"<b>HD/TD/HH</b>: {self._format_k_value(match.hero_damage)} / "
                f"{self._format_k_value(match.tower_damage)} / "
                f"{self._format_k_value(match.hero_healing)}"
            )
        parts.append(f'<a href="{dotabuff_match_url(first_match.match_id)}">Dotabuff</a>')
        return "\n".join(parts)

    @staticmethod
    def _hero_name(hero_id: int, constants: ConstantSnapshot | None) -> str:
        if constants is not None and hero_id in constants.heroes:
            return constants.heroes[hero_id]
        return HERO_NAMES.get(hero_id, f"Hero #{hero_id}")

    @staticmethod
    def _game_mode_name(game_mode: int, constants: ConstantSnapshot | None) -> str:
        if constants is not None and game_mode in constants.game_modes:
            return constants.game_modes[game_mode]
        return GAME_MODES.get(game_mode, str(game_mode))

    @staticmethod
    def _lobby_type_name(lobby_type: int, constants: ConstantSnapshot | None) -> str:
        if constants is not None and lobby_type in constants.lobby_types:
            return constants.lobby_types[lobby_type]
        return LOBBY_TYPES.get(lobby_type, str(lobby_type))

    @staticmethod
    def _format_outcome(is_win: bool) -> str:
        return "🟢<b>Win</b>" if is_win else "🔴<b>Lose</b>"

    @staticmethod
    def _format_k_value(value: int | float) -> str:
        return f"{value / 1000:.1f}K"
