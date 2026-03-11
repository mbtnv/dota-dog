from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dota_dog.infra.db.base import Base
from dota_dog.services.constants import ConstantsService


class FakeConstantsClient:
    async def get_constants_resource(self, resource: str) -> dict[str, object]:
        if resource == "heroes":
            return {"74": {"id": 74, "localized_name": "Invoker"}}
        if resource == "game_mode":
            return {"22": {"id": 22, "name": "all_pick"}}
        return {"7": {"id": 7, "name": "ranked"}}


@pytest.mark.asyncio
async def test_constants_service_syncs_snapshot_to_db() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    service = ConstantsService(sync_interval_hours=24)

    async with session_factory() as session:
        await service.sync_if_stale(session, FakeConstantsClient())
        await session.commit()

    async with session_factory() as session:
        snapshot = await service.get_snapshot(session)

    assert snapshot.heroes[74] == "Invoker"
    assert snapshot.game_modes[22] == "All Pick"
    assert snapshot.lobby_types[7] == "Ranked"

    await engine.dispose()
