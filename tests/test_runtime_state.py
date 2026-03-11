from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dota_dog.infra.db.base import Base
from dota_dog.infra.db.repositories.core import TopicRepository, TopicRuntimeRepository


@pytest.mark.asyncio
async def test_topic_runtime_repository_tracks_success_state() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    started_at = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    finished_at = datetime(2026, 3, 10, 12, 1, tzinfo=UTC)

    async with session_factory() as session:
        topic = await TopicRepository(session).get_or_create(
            telegram_chat_id=1,
            telegram_thread_id=10,
            title="test",
            timezone="UTC",
        )
        runtime_repo = TopicRuntimeRepository(session)
        await runtime_repo.mark_started(topic.id, started_at)
        await runtime_repo.mark_succeeded(
            topic.id,
            started_at=started_at,
            finished_at=finished_at,
        )
        await session.commit()

    async with session_factory() as session:
        topic = await TopicRepository(session).get_by_chat_thread(1, 10)
        assert topic is not None
        status = await TopicRuntimeRepository(session).get_status(topic.id)

    assert status is not None
    assert status.last_poll_started_at == started_at
    assert status.last_poll_succeeded_at == finished_at
    assert status.last_poll_error is None

    await engine.dispose()
