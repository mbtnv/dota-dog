from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dota_dog.bot.handlers.common import HandlerDependencies, report_handler, track_handler
from dota_dog.infra.db.base import Base
from dota_dog.infra.db.models import PlayerMatchORM
from dota_dog.infra.db.repositories.core import (
    PlayerRepository,
    TopicPlayerRepository,
    TopicRepository,
)
from dota_dog.infra.opendota.schemas import OpenDotaProfileResponse
from dota_dog.services.backfill import BackfillService
from dota_dog.services.constants import ConstantsService
from dota_dog.services.formatter import MessageFormatter
from dota_dog.services.permissions import PermissionService
from dota_dog.services.reporting import ReportingService
from dota_dog.services.tracking import TrackingService


class FakeOpenDotaClient:
    async def get_profile(self, account_id: int) -> OpenDotaProfileResponse:
        return OpenDotaProfileResponse.model_validate(
            {
                "profile": {
                    "account_id": account_id,
                    "personaname": "Sega",
                    "profileurl": f"https://www.dotabuff.com/players/{account_id}",
                }
            }
        )

    async def get_constants_resource(self, resource: str) -> dict[str, object]:
        return {}

    async def get_player_matches(
        self,
        account_id: int,
        *,
        days: int,
        limit: int,
        offset: int,
    ) -> list[object]:
        return []


class FakeBot:
    def __init__(self, admin_ids: list[int]) -> None:
        self._admin_ids = admin_ids

    async def get_chat_administrators(self, chat_id: int) -> list[SimpleNamespace]:
        return [SimpleNamespace(user=SimpleNamespace(id=admin_id)) for admin_id in self._admin_ids]


@dataclass
class FakeMessage:
    text: str
    chat_type: str = "supergroup"
    chat_id: int = -1001
    thread_id: int | None = 10
    title: str = "Test topic"
    user_id: int = 1
    bot: Any = field(default_factory=lambda: FakeBot([1]))
    answers: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.chat = SimpleNamespace(id=self.chat_id, type=self.chat_type, title=self.title)
        self.message_thread_id = self.thread_id
        self.from_user = SimpleNamespace(id=self.user_id)

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append((text, kwargs))


def _make_deps(session_factory: async_sessionmaker) -> HandlerDependencies:
    tracking_service = TrackingService()
    return HandlerDependencies(
        session_factory=session_factory,
        opendota_client=FakeOpenDotaClient(),  # type: ignore[arg-type]
        reporting_service=ReportingService(),
        formatter=MessageFormatter(),
        constants_service=ConstantsService(sync_interval_hours=24),
        backfill_service=BackfillService(tracking_service),
        permission_service=PermissionService(
            allowed_user_ids=set(),
            telegram_admin_check_enabled=True,
        ),
        poll_interval_minutes=15,
        default_timezone="UTC",
    )


@pytest.mark.asyncio
async def test_track_handler_adds_player_from_profile_url() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    deps = _make_deps(session_factory)
    message = FakeMessage(text="/track https://www.dotabuff.com/players/123456 mid")

    await track_handler(message, deps)

    async with session_factory() as session:
        topic = await TopicRepository(session).get_by_chat_thread(
            message.chat_id, message.thread_id
        )
        assert topic is not None
        players = await TopicPlayerRepository(session).list_topic_players(topic.id)

    assert len(players) == 1
    assert players[0].dota_account_id == 123456
    assert players[0].alias == "mid"
    assert "Добавлен" in message.answers[0][0]

    await engine.dispose()


@pytest.mark.asyncio
async def test_report_handler_returns_html_report_for_filtered_player() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        topic = await TopicRepository(session).get_or_create(
            telegram_chat_id=-1001,
            telegram_thread_id=10,
            title="Test topic",
            timezone="UTC",
        )
        player = await PlayerRepository(session).get_or_create(
            dota_account_id=123456,
            display_name="Sega",
            profile_url="https://www.dotabuff.com/players/123456",
        )
        await TopicPlayerRepository(session).add_player(
            topic_id=topic.id,
            player_id=player.id,
            alias="mid",
            added_by_telegram_user_id=1,
        )
        session.add(
            PlayerMatchORM(
                player_id=player.id,
                match_id=1001,
                start_time=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
                end_time=datetime(2026, 3, 10, 12, 30, tzinfo=UTC),
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
                created_at=datetime(2026, 3, 10, 12, 31, tzinfo=UTC),
            )
        )
        await session.commit()

    deps = _make_deps(session_factory)
    message = FakeMessage(text="/report month mid")

    await report_handler(message, deps)

    assert len(message.answers) == 1
    assert "mid" in message.answers[0][0]
    assert "Matches:" in message.answers[0][0]
    assert message.answers[0][1]["parse_mode"] == "HTML"

    await engine.dispose()
