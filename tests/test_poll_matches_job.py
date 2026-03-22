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
    def __init__(
        self,
        matches: list[OpenDotaRecentMatch] | None = None,
        *,
        matches_by_account_id: dict[int, list[OpenDotaRecentMatch]] | None = None,
        game_modes_payload: dict[str, object] | None = None,
    ) -> None:
        self._matches = matches if matches is not None else []
        self._matches_by_account_id = matches_by_account_id or {}
        self._game_modes_payload = game_modes_payload or {"22": {"id": 22, "name": "All Pick"}}

    async def get_recent_matches(self, account_id: int) -> list[OpenDotaRecentMatch]:
        return self._matches_by_account_id.get(account_id, self._matches)

    async def get_constants_resource(self, resource: str) -> dict[str, object]:
        if resource == "heroes":
            return {"74": {"id": 74, "localized_name": "Invoker"}}
        if resource == "game_mode":
            return self._game_modes_payload
        if resource == "lobby_type":
            return {"7": {"id": 7, "name": "Ranked"}}
        return {}


class FakeTelegramSender:
    def __init__(self) -> None:
        self.sent: list[tuple[TrackedTopicRef, str]] = []

    async def send_to_topic(self, topic: TrackedTopicRef, text: str) -> None:
        self.sent.append((topic, text))


def _recent_match(
    match_id: int,
    *,
    player_slot: int = 0,
    radiant_win: bool = True,
    game_mode: int = 22,
    lobby_type: int = 7,
    hero_id: int = 74,
    kills: int = 10,
    deaths: int = 2,
    assists: int = 11,
    xpm: int = 700,
    gpm: int = 650,
    hero_damage: int = 20000,
    tower_damage: int = 4000,
    hero_healing: int = 0,
    last_hits: int = 250,
    party_size: int | None = 1,
) -> OpenDotaRecentMatch:
    started_at = datetime(2026, 3, 10, tzinfo=UTC) - timedelta(minutes=30)
    return OpenDotaRecentMatch(
        match_id=match_id,
        player_slot=player_slot,
        radiant_win=radiant_win,
        duration=1800,
        game_mode=game_mode,
        lobby_type=lobby_type,
        hero_id=hero_id,
        start_time=int(started_at.timestamp()),
        kills=kills,
        deaths=deaths,
        assists=assists,
        xp_per_min=xpm,
        gold_per_min=gpm,
        hero_damage=hero_damage,
        tower_damage=tower_damage,
        hero_healing=hero_healing,
        last_hits=last_hits,
        party_size=party_size,
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


@pytest.mark.asyncio
async def test_poll_job_groups_shared_match_into_single_notification() -> None:
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
        player_one = await PlayerRepository(session).get_or_create(
            dota_account_id=123,
            display_name="Myrade",
            profile_url=None,
        )
        player_two = await PlayerRepository(session).get_or_create(
            dota_account_id=456,
            display_name="BIGBABY",
            profile_url=None,
        )
        relation_one = await TopicPlayerRepository(session).add_player(
            topic_id=topic.id,
            player_id=player_one.id,
            alias="myrade",
            added_by_telegram_user_id=99,
        )
        relation_two = await TopicPlayerRepository(session).add_player(
            topic_id=topic.id,
            player_id=player_two.id,
            alias="BIGBABY",
            added_by_telegram_user_id=99,
        )
        assert relation_one is not None
        assert relation_two is not None
        relation_one.last_seen_match_id = 1001
        relation_two.last_seen_match_id = 1001
        await session.commit()

    sender = FakeTelegramSender()
    job = PollMatchesJob(
        session_factory=session_factory,
        opendota_client=FakeOpenDotaClient(
            matches_by_account_id={
                123: [
                    _recent_match(1001),
                    _recent_match(
                        1002,
                        hero_id=23,
                        kills=10,
                        deaths=4,
                        assists=18,
                        gpm=640,
                        xpm=698,
                        hero_damage=11300,
                        tower_damage=5700,
                        last_hits=208,
                        party_size=2,
                    ),
                ],
                456: [
                    _recent_match(1001),
                    _recent_match(
                        1002,
                        player_slot=1,
                        hero_id=123,
                        kills=12,
                        deaths=2,
                        assists=26,
                        gpm=459,
                        xpm=579,
                        hero_damage=17100,
                        tower_damage=2400,
                        last_hits=61,
                        party_size=2,
                    ),
                ],
            },
            game_modes_payload={"22": {"id": 22, "name": "All Draft"}},
        ),
        constants_service=ConstantsService(sync_interval_hours=24),
        tracking_service=TrackingService(),
        formatter=MessageFormatter(),
        sender=sender,
    )

    messages = await job.run_once()

    async with session_factory() as session:
        refs = await TopicPlayerRepository(session).list_topic_players(topic.id)

    assert len(messages) == 1
    assert len(sender.sent) == 1
    assert "myrade" in messages[0]
    assert "BIGBABY" in messages[0]
    assert messages[0].count("<b>Ended</b>:") == 1
    assert messages[0].count("Dotabuff") == 1
    assert "<b>Mode</b>: All Pick · Ranked" in messages[0]
    assert sorted(ref.last_seen_match_id for ref in refs) == [1002, 1002]

    await engine.dispose()
