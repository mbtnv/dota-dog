from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dota_dog.domain.enums import PeriodType
from dota_dog.domain.models import TrackedTopicRef
from dota_dog.infra.db.base import Base
from dota_dog.infra.db.models import PlayerMatchORM
from dota_dog.infra.db.repositories.core import (
    PlayerRepository,
    ReportRunRepository,
    TopicPlayerRepository,
    TopicRepository,
)
from dota_dog.jobs.send_reports import SendReportsJob
from dota_dog.services.constants import ConstantsService
from dota_dog.services.formatter import MessageFormatter
from dota_dog.services.reporting import ReportingService


class FakeTelegramSender:
    def __init__(self) -> None:
        self.sent: list[tuple[TrackedTopicRef, str]] = []

    async def send_to_topic(self, topic: TrackedTopicRef, text: str) -> None:
        self.sent.append((topic, text))


@pytest.mark.asyncio
async def test_send_reports_job_is_idempotent_for_same_period() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    reporting = ReportingService()
    now = datetime.now(UTC)
    period_start, period_end = reporting.previous_period_bounds(PeriodType.DAY, now, "UTC")

    async with session_factory() as session:
        topic = await TopicRepository(session).get_or_create(
            telegram_chat_id=1,
            telegram_thread_id=10,
            title="Test",
            timezone="UTC",
        )
        player = await PlayerRepository(session).get_or_create(
            dota_account_id=123,
            display_name="Sega",
            profile_url=None,
        )
        await TopicPlayerRepository(session).add_player(
            topic_id=topic.id,
            player_id=player.id,
            alias="mid",
            added_by_telegram_user_id=99,
        )
        session.add(
            PlayerMatchORM(
                player_id=player.id,
                match_id=1001,
                start_time=period_start,
                end_time=period_start.replace(hour=1),
                hero_id=74,
                radiant_win=True,
                player_slot=0,
                kills=10,
                deaths=2,
                assists=9,
                gpm=700,
                xpm=800,
                hero_damage=21000,
                tower_damage=5000,
                hero_healing=0,
                last_hits=250,
                game_mode=22,
                lobby_type=7,
                party_size=1,
                raw_payload={},
                created_at=period_end,
            )
        )
        await session.commit()

    sender = FakeTelegramSender()
    job = SendReportsJob(
        session_factory=session_factory,
        constants_service=ConstantsService(sync_interval_hours=24),
        reporting_service=reporting,
        formatter=MessageFormatter(),
        sender=sender,
    )

    first_run = await job.run_once(PeriodType.DAY)
    second_run = await job.run_once(PeriodType.DAY)

    async with session_factory() as session:
        topic = await TopicRepository(session).get_by_chat_thread(1, 10)
        assert topic is not None
        has_run = await ReportRunRepository(session).has_run(
            topic.id,
            PeriodType.DAY.value,
            period_start,
            period_end,
        )

    assert len(first_run) == 1
    assert second_run == []
    assert len(sender.sent) == 1
    assert has_run is True

    await engine.dispose()
