from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import async_sessionmaker

from dota_dog.domain.models import TrackedTopicRef
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
            await self._constants_service.sync_if_stale(session, self._opendota_client)
            constants = await self._constants_service.get_snapshot(session)
            topics = await TopicRepository(session).list_refs()
            topic_players_repo = TopicPlayerRepository(session)
            match_repo = MatchRepository(session)
            topic_runtime_repo = TopicRuntimeRepository(session)
            for topic in topics:
                if topic.is_paused:
                    continue
                started_at = datetime.now(UTC)
                await topic_runtime_repo.mark_started(topic.id, started_at)
                try:
                    players = await topic_players_repo.list_topic_players(topic.id)
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
                            text = self._formatter.format_match_notification(
                                player,
                                snapshot,
                                constants,
                                topic.timezone,
                            )
                            await self._sender.send_to_topic(topic, text)
                            messages.append(text)
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
                    await topic_runtime_repo.mark_succeeded(
                        topic.id,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                    )
                except Exception as exc:
                    await topic_runtime_repo.mark_failed(
                        topic.id,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        error=str(exc),
                    )
            await session.commit()
        return messages
