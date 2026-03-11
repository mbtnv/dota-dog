from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import async_sessionmaker

from dota_dog.domain.enums import PeriodType
from dota_dog.domain.models import MatchSnapshot, TrackedTopicRef
from dota_dog.infra.db.models import PlayerMatchORM
from dota_dog.infra.db.repositories.core import (
    MatchRepository,
    ReportRunRepository,
    TopicPlayerRepository,
    TopicRepository,
)
from dota_dog.services.constants import ConstantsService
from dota_dog.services.formatter import MessageFormatter
from dota_dog.services.reporting import ReportingService


def _orm_to_snapshot(match: PlayerMatchORM) -> MatchSnapshot:
    return MatchSnapshot(
        player_id=match.player_id,
        match_id=match.match_id,
        start_time=match.start_time,
        end_time=match.end_time,
        hero_id=match.hero_id,
        radiant_win=match.radiant_win,
        player_slot=match.player_slot,
        kills=match.kills,
        deaths=match.deaths,
        assists=match.assists,
        gpm=match.gpm,
        xpm=match.xpm,
        hero_damage=match.hero_damage,
        tower_damage=match.tower_damage,
        hero_healing=match.hero_healing,
        last_hits=match.last_hits,
        game_mode=match.game_mode,
        lobby_type=match.lobby_type,
        party_size=match.party_size,
        raw_payload=match.raw_payload,
    )


class SendReportsJob:
    class TopicMessageSender(Protocol):
        async def send_to_topic(self, topic: TrackedTopicRef, text: str) -> None: ...

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker,
        constants_service: ConstantsService,
        reporting_service: ReportingService,
        formatter: MessageFormatter,
        sender: TopicMessageSender,
    ) -> None:
        self._session_factory = session_factory
        self._constants_service = constants_service
        self._reporting_service = reporting_service
        self._formatter = formatter
        self._sender = sender

    async def run_once(self, period_type: PeriodType) -> list[str]:
        messages: list[str] = []
        async with self._session_factory() as session:
            constants = await self._constants_service.get_snapshot(session)
            topic_repo = TopicRepository(session)
            topic_player_repo = TopicPlayerRepository(session)
            match_repo = MatchRepository(session)
            report_run_repo = ReportRunRepository(session)
            for topic in await topic_repo.list_refs():
                period_start, period_end = self._reporting_service.previous_period_bounds(
                    period_type, datetime.now(UTC), topic.timezone
                )
                if await report_run_repo.has_run(
                    topic.id,
                    period_type.value,
                    period_start,
                    period_end,
                ):
                    continue
                players = await topic_player_repo.list_topic_players(topic.id)
                if not players:
                    continue
                orm_matches = await match_repo.list_matches_for_players(
                    [player.player_id for player in players],
                    period_start,
                    period_end,
                )
                summaries = self._reporting_service.build_topic_summaries(
                    period_type=period_type,
                    period_start=period_start,
                    period_end=period_end,
                    players=players,
                    matches=[_orm_to_snapshot(match) for match in orm_matches],
                )
                text = self._formatter.format_report_bundle(
                    title=f"{period_type.value.title()} report",
                    summaries=summaries,
                    constants=constants,
                )
                await self._sender.send_to_topic(topic, text)
                await report_run_repo.create(
                    topic_id=topic.id,
                    period_type=period_type.value,
                    period_start=period_start,
                    period_end=period_end,
                    trigger_source="auto",
                    telegram_message_id=None,
                )
                messages.append(text)
            await session.commit()
        return messages
