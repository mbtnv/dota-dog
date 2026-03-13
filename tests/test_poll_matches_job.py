from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dota_dog.domain.models import TrackedTopicRef
from dota_dog.infra.db.base import Base
from dota_dog.infra.db.repositories.core import (
    MatchRepository,
    PlayerRepository,
    TopicPlayerRepository,
    TopicRepository,
)
from dota_dog.infra.opendota.schemas import OpenDotaRecentMatch
from dota_dog.jobs.poll_matches import PollMatchesJob
from dota_dog.services.constants import ConstantsService
from dota_dog.services.formatter import MessageFormatter
from dota_dog.services.tracking import TrackingService


class FakeOpenDotaClient:
    def __init__(self, matches: list[OpenDotaRecentMatch]) -> None:
        self._matches = matches

    async def get_recent_matches(self, account_id: int) -> list[OpenDotaRecentMatch]:
        return self._matches

    async def get_constants_resource(self, resource: str) -> dict[str, object]:
        if resource == "heroes":
            return {"74": {"id": 74, "localized_name": "Invoker"}}
        if resource == "game_mode":
            return {"22": {"id": 22, "name": "All Pick"}}
        if resource == "lobby_type":
            return {"7": {"id": 7, "name": "Ranked"}}
        return {}


class FakeTelegramSender:
    def __init__(self) -> None:
        self.sent: list[tuple[TrackedTopicRef, str]] = []

    async def send_to_topic(self, topic: TrackedTopicRef, text: str) -> None:
        self.sent.append((topic, text))


def _recent_match(match_id: int) -> OpenDotaRecentMatch:
    started_at = datetime(2026, 3, 10, tzinfo=UTC) - timedelta(minutes=30)
    return OpenDotaRecentMatch(
        match_id=match_id,
        player_slot=0,
        radiant_win=True,
        duration=1800,
        game_mode=22,
        lobby_type=7,
        hero_id=74,
        start_time=int(started_at.timestamp()),
        kills=10,
        deaths=2,
        assists=11,
        xp_per_min=700,
        gold_per_min=650,
        hero_damage=20000,
        tower_damage=4000,
        hero_healing=0,
        last_hits=250,
        party_size=1,
    )


@pytest.mark.asyncio
async def test_poll_job_initial_sync_persists_without_notification() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        topic = await TopicRepository(session).get_or_create(
            telegram_chat_id=1,
            telegram_thread_id=10,
            title="Test",
            timezone="Europe/Moscow",
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
        await session.commit()

    sender = FakeTelegramSender()
    job = PollMatchesJob(
        session_factory=session_factory,
        opendota_client=FakeOpenDotaClient([_recent_match(1001)]),
        constants_service=ConstantsService(sync_interval_hours=24),
        tracking_service=TrackingService(),
        formatter=MessageFormatter(),
        sender=sender,
    )

    messages = await job.run_once()

    async with session_factory() as session:
        matches = await MatchRepository(session).list_matches_for_players(
            [player.id],
            datetime(2026, 3, 1, tzinfo=UTC),
            datetime(2026, 4, 1, tzinfo=UTC),
        )
        refs = await TopicPlayerRepository(session).list_topic_players(topic.id)

    assert messages == []
    assert len(sender.sent) == 0
    assert len(matches) == 1
    assert refs[0].last_seen_match_id == 1001

    await engine.dispose()


@pytest.mark.asyncio
async def test_poll_job_notifies_only_once_for_new_match() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        topic = await TopicRepository(session).get_or_create(
            telegram_chat_id=1,
            telegram_thread_id=10,
            title="Test",
            timezone="Europe/Moscow",
        )
        player = await PlayerRepository(session).get_or_create(
            dota_account_id=123,
            display_name="Sega",
            profile_url=None,
        )
        relation = await TopicPlayerRepository(session).add_player(
            topic_id=topic.id,
            player_id=player.id,
            alias="mid",
            added_by_telegram_user_id=99,
        )
        assert relation is not None
        relation.last_seen_match_id = 1001
        await session.commit()

    sender = FakeTelegramSender()
    job = PollMatchesJob(
        session_factory=session_factory,
        opendota_client=FakeOpenDotaClient([_recent_match(1001), _recent_match(1002)]),
        constants_service=ConstantsService(sync_interval_hours=24),
        tracking_service=TrackingService(),
        formatter=MessageFormatter(),
        sender=sender,
    )

    first_run = await job.run_once()
    second_run = await job.run_once()

    async with session_factory() as session:
        matches = await MatchRepository(session).list_matches_for_players(
            [player.id],
            datetime(2026, 3, 1, tzinfo=UTC),
            datetime(2026, 4, 1, tzinfo=UTC),
        )

    assert len(first_run) == 1
    assert second_run == []
    assert len(sender.sent) == 1
    assert "<b>Ended</b>: 2026-03-10 03:00 MSK (30 min)" in first_run[0]
    assert "Dotabuff" in first_run[0]
    assert sorted(match.match_id for match in matches) == [1002]

    await engine.dispose()
