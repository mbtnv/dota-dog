from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import async_sessionmaker

from dota_dog.domain.models import (
    ConstantSnapshot,
    MatchSnapshot,
    TrackedPlayerRef,
    TrackedTopicRef,
)
from dota_dog.infra.db.repositories.core import (
    MatchRepository,
    TopicPlayerRepository,
    TopicRepository,
    TopicRuntimeRepository,
)
from dota_dog.infra.opendota.schemas import OpenDotaRecentMatch
from dota_dog.services.constants import ConstantsService
from dota_dog.services.formatter import MessageFormatter
from dota_dog.services.tracking import TrackingService

logger = logging.getLogger(__name__)


class RecentMatchesClient(Protocol):
    async def get_recent_matches(self, account_id: int) -> Sequence[OpenDotaRecentMatch]: ...

    async def get_constants_resource(self, resource: str) -> dict[str, object]: ...


class TopicMessageSender(Protocol):
    async def send_to_topic(self, topic: TrackedTopicRef, text: str) -> None: ...


class PollMatchesJob:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker,
        opendota_client: RecentMatchesClient,
        constants_service: ConstantsService,
        tracking_service: TrackingService,
        formatter: MessageFormatter,
        sender: TopicMessageSender,
    ) -> None:
        self._session_factory = session_factory
        self._opendota_client = opendota_client
        self._constants_service = constants_service
        self._tracking_service = tracking_service
        self._formatter = formatter
        self._sender = sender

    async def run_once(self) -> list[str]:
        messages: list[str] = []
        async with self._session_factory() as session:
            try:
                await self._constants_service.sync_if_stale(session, self._opendota_client)
            except Exception:
                await session.rollback()
                logger.exception("failed to sync OpenDota constants; using cached constants")
            constants = await self._constants_service.get_snapshot(session)
            topics = await TopicRepository(session).list_refs()
            await session.commit()

        for topic in topics:
            if topic.is_paused:
                continue
            started_at = datetime.now(UTC)
            await self._mark_started(topic.id, started_at)
            try:
                messages.extend(
                    await self._process_topic(
                        topic=topic,
                        constants=constants,
                        started_at=started_at,
                    )
                )
            except Exception as exc:
                await self._mark_failed(topic.id, started_at, exc)
        return messages

    async def _process_topic(
        self,
        *,
        topic: TrackedTopicRef,
        constants: ConstantSnapshot,
        started_at: datetime,
    ) -> list[str]:
        messages: list[str] = []
        async with self._session_factory() as session:
            topic_players_repo = TopicPlayerRepository(session)
            match_repo = MatchRepository(session)
            topic_runtime_repo = TopicRuntimeRepository(session)

            try:
                players = await topic_players_repo.list_topic_players(topic.id)
                player_order = {player.player_id: index for index, player in enumerate(players)}
                fresh_matches_by_match_id: dict[
                    int, list[tuple[TrackedPlayerRef, MatchSnapshot]]
                ] = {}
                notification_match_order: list[int] = []
                for player in players:
                    recent_matches = list(
                        await self._opendota_client.get_recent_matches(player.dota_account_id)
                    )
                    snapshots = self._tracking_service.build_match_snapshots(
                        player_id=player.player_id,
                        recent_matches=recent_matches,
                        last_seen_match_id=player.last_seen_match_id,
                    )
                    if player.last_seen_match_id is None:
                        await match_repo.save_new_matches(snapshots)
                        next_match_id = self._tracking_service.next_last_seen_match_id(
                            player,
                            snapshots,
                        )
                        if next_match_id is not None:
                            await topic_players_repo.set_last_seen_match_id(
                                topic.id,
                                player.player_id,
                                next_match_id,
                            )
                        continue
                    fresh_snapshots = await match_repo.save_new_matches(snapshots)
                    for snapshot in fresh_snapshots:
                        if snapshot.match_id not in fresh_matches_by_match_id:
                            fresh_matches_by_match_id[snapshot.match_id] = []
                            notification_match_order.append(snapshot.match_id)
                        fresh_matches_by_match_id[snapshot.match_id].append((player, snapshot))
                    next_match_id = self._tracking_service.next_last_seen_match_id(
                        player,
                        snapshots,
                    )
                    if next_match_id is not None:
                        await topic_players_repo.set_last_seen_match_id(
                            topic.id,
                            player.player_id,
                            next_match_id,
                        )
                for match_id in notification_match_order:
                    group = sorted(
                        fresh_matches_by_match_id[match_id],
                        key=lambda item: player_order[item[0].player_id],
                    )
                    text = self._formatter.format_match_group_notification(
                        group,
                        constants,
                        topic.timezone,
                    )
                    await self._sender.send_to_topic(topic, text)
                    messages.append(text)
                await topic_runtime_repo.mark_succeeded(
                    topic.id,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return messages

    async def _mark_started(self, topic_id: int, started_at: datetime) -> None:
        async with self._session_factory() as session:
            await TopicRuntimeRepository(session).mark_started(topic_id, started_at)
            await session.commit()

    async def _mark_failed(self, topic_id: int, started_at: datetime, exc: Exception) -> None:
        async with self._session_factory() as session:
            await TopicRuntimeRepository(session).mark_failed(
                topic_id,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error=str(exc),
            )
            await session.commit()
