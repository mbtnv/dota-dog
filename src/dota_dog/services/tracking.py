from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dota_dog.domain.models import MatchSnapshot, TrackedPlayerRef
from dota_dog.infra.opendota.schemas import OpenDotaPlayerMatch, OpenDotaRecentMatch


class TrackingService:
    def build_match_snapshots(
        self,
        *,
        player_id: int,
        recent_matches: list[OpenDotaRecentMatch],
        last_seen_match_id: int | None,
    ) -> list[MatchSnapshot]:
        matches = [
            self._to_snapshot(player_id=player_id, match=match)
            for match in recent_matches
            if last_seen_match_id is None or match.match_id > last_seen_match_id
        ]
        matches.sort(key=lambda item: item.match_id)
        return matches

    def next_last_seen_match_id(
        self, player: TrackedPlayerRef, new_matches: list[MatchSnapshot]
    ) -> int | None:
        if not new_matches:
            return player.last_seen_match_id
        return max(match.match_id for match in new_matches)

    def build_history_snapshots(
        self,
        *,
        player_id: int,
        matches: list[OpenDotaPlayerMatch],
    ) -> list[MatchSnapshot]:
        snapshots = [self._to_snapshot(player_id=player_id, match=match) for match in matches]
        snapshots.sort(key=lambda item: item.match_id)
        return snapshots

    @staticmethod
    def _to_snapshot(player_id: int, match: OpenDotaRecentMatch) -> MatchSnapshot:
        start = datetime.fromtimestamp(match.start_time, tz=UTC)
        end = start + timedelta(seconds=match.duration)
        return MatchSnapshot(
            player_id=player_id,
            match_id=match.match_id,
            start_time=start,
            end_time=end,
            hero_id=match.hero_id,
            radiant_win=match.radiant_win,
            player_slot=match.player_slot,
            kills=match.kills,
            deaths=match.deaths,
            assists=match.assists,
            gpm=match.gold_per_min,
            xpm=match.xp_per_min,
            hero_damage=match.hero_damage,
            tower_damage=match.tower_damage,
            hero_healing=match.hero_healing,
            last_hits=match.last_hits,
            game_mode=match.game_mode,
            lobby_type=match.lobby_type,
            party_size=match.party_size,
            raw_payload=match.model_dump(),
        )
