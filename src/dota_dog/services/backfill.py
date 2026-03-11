from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from dota_dog.domain.models import TrackedPlayerRef
from dota_dog.infra.db.repositories.core import MatchRepository, TopicPlayerRepository
from dota_dog.infra.opendota.schemas import OpenDotaPlayerMatch
from dota_dog.services.tracking import TrackingService

logger = logging.getLogger(__name__)


class MatchHistoryClient(Protocol):
    async def get_player_matches(
        self,
        account_id: int,
        *,
        days: int,
        limit: int,
        offset: int,
    ) -> Sequence[OpenDotaPlayerMatch]: ...

    async def get_match_players(self, match_id: int) -> Sequence[OpenDotaPlayerMatch]: ...


@dataclass(slots=True)
class ResyncResult:
    player_label: str
    inserted_matches: int
    fetched_matches: int
    failed_matches: int = 0


class BackfillService:
    def __init__(self, tracking_service: TrackingService) -> None:
        self._tracking_service = tracking_service

    async def resync_player(
        self,
        *,
        session: AsyncSession,
        client: MatchHistoryClient,
        topic_id: int,
        player: TrackedPlayerRef,
        days: int,
        page_size: int = 100,
    ) -> ResyncResult:
        match_repo = MatchRepository(session)
        topic_player_repo = TopicPlayerRepository(session)
        fetched_matches, failed_matches = await self._fetch_all_matches(
            client=client,
            account_id=player.dota_account_id,
            days=days,
            page_size=page_size,
        )
        snapshots = self._tracking_service.build_history_snapshots(
            player_id=player.player_id,
            matches=list(fetched_matches),
        )
        inserted = await match_repo.save_new_matches(snapshots)
        if fetched_matches:
            max_match_id = max(match.match_id for match in fetched_matches)
            current_last_seen = player.last_seen_match_id or 0
            if max_match_id > current_last_seen:
                await topic_player_repo.set_last_seen_match_id(
                    topic_id,
                    player.player_id,
                    max_match_id,
                )
        return ResyncResult(
            player_label=player.alias or player.display_name,
            inserted_matches=len(inserted),
            fetched_matches=len(fetched_matches),
            failed_matches=failed_matches,
        )

    async def _fetch_all_matches(
        self,
        *,
        client: MatchHistoryClient,
        account_id: int,
        days: int,
        page_size: int,
    ) -> tuple[list[OpenDotaPlayerMatch], int]:
        offset = 0
        summary_matches: list[OpenDotaPlayerMatch] = []
        while True:
            page = list(
                await client.get_player_matches(
                    account_id,
                    days=days,
                    limit=page_size,
                    offset=offset,
                )
            )
            if not page:
                break
            summary_matches.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        collected: list[OpenDotaPlayerMatch] = []
        failed_matches = 0
        for summary in summary_matches:
            try:
                match_players = await client.get_match_players(summary.match_id)
            except Exception:
                failed_matches += 1
                logger.exception(
                    "failed to fetch match details for resync",
                    extra={"account_id": account_id, "match_id": summary.match_id},
                )
                continue
            player_match = self._select_player_match(
                match_players=match_players,
                account_id=account_id,
                player_slot=summary.player_slot,
            )
            if player_match is None:
                failed_matches += 1
                logger.warning(
                    "tracked player not found in match details",
                    extra={"account_id": account_id, "match_id": summary.match_id},
                )
                continue
            collected.append(player_match)
        return collected, failed_matches

    @staticmethod
    def _select_player_match(
        *,
        match_players: Sequence[OpenDotaPlayerMatch],
        account_id: int,
        player_slot: int,
    ) -> OpenDotaPlayerMatch | None:
        for player in match_players:
            if player.account_id == account_id:
                return player
        for player in match_players:
            if player.player_slot == player_slot:
                return player
        return None
