from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dota_dog.infra.db.base import Base
from dota_dog.infra.db.repositories.core import (
    MatchRepository,
    PlayerRepository,
    TopicPlayerRepository,
    TopicRepository,
)
from dota_dog.infra.opendota.schemas import OpenDotaPlayerMatch
from dota_dog.services.backfill import BackfillService
from dota_dog.services.tracking import TrackingService


class FakeHistoryClient:
    def __init__(self, matches: list[OpenDotaPlayerMatch]) -> None:
        self._matches = matches

    async def get_player_matches(
        self,
        account_id: int,
        *,
        days: int,
        limit: int,
        offset: int,
    ) -> list[OpenDotaPlayerMatch]:
        return self._matches[offset : offset + limit]


def _player_match(match_id: int, start_time: int) -> OpenDotaPlayerMatch:
    return OpenDotaPlayerMatch(
        match_id=match_id,
        player_slot=0,
        radiant_win=True,
        duration=1800,
        game_mode=22,
        lobby_type=7,
        hero_id=74,
        start_time=start_time,
        kills=10,
        deaths=2,
        assists=5,
        xp_per_min=700,
        gold_per_min=650,
        hero_damage=20000,
        tower_damage=4000,
        hero_healing=0,
        last_hits=250,
        party_size=1,
    )


@pytest.mark.asyncio
async def test_backfill_service_persists_matches_and_updates_last_seen() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

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
        relation = await TopicPlayerRepository(session).add_player(
            topic_id=topic.id,
            player_id=player.id,
            alias="mid",
            added_by_telegram_user_id=99,
        )
        assert relation is not None
        relation.last_seen_match_id = 1000
        await session.commit()

    client = FakeHistoryClient(
        [
            _player_match(1001, 1_700_000_000),
            _player_match(1002, 1_700_010_000),
        ]
    )
    service = BackfillService(TrackingService())

    async with session_factory() as session:
        topic = await TopicRepository(session).get_by_chat_thread(1, 10)
        assert topic is not None
        players = await TopicPlayerRepository(session).list_topic_players(topic.id)
        result = await service.resync_player(
            session=session,
            client=client,
            topic_id=topic.id,
            player=players[0],
            days=7,
        )
        await session.commit()

    async with session_factory() as session:
        matches = await MatchRepository(session).list_matches_for_players(
            [player.id],
            datetime(2023, 1, 1, tzinfo=UTC),
            datetime(2027, 1, 1, tzinfo=UTC),
        )
        players = await TopicPlayerRepository(session).list_topic_players(topic.id)

    assert result.fetched_matches == 2
    assert result.inserted_matches == 2
    assert sorted(match.match_id for match in matches) == [1001, 1002]
    assert players[0].last_seen_match_id == 1002

    await engine.dispose()
