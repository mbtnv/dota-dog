from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dota_dog.infra.db.base import Base
from dota_dog.infra.db.repositories.core import TopicRepository


@pytest.mark.asyncio
async def test_topic_repository_updates_timezone_and_pause() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        repo = TopicRepository(session)
        topic = await repo.get_or_create(
            telegram_chat_id=1,
            telegram_thread_id=10,
            title="Test",
            timezone="UTC",
        )
        await repo.update_timezone(topic.id, "Europe/Moscow")
        await repo.set_paused(topic.id, True)
        await session.commit()

    async with session_factory() as session:
        topic = await TopicRepository(session).get_by_chat_thread(1, 10)

    assert topic is not None
    assert topic.timezone == "Europe/Moscow"
    assert topic.is_paused is True

    await engine.dispose()
