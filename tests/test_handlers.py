from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dota_dog.bot.handlers.common import (
    HandlerDependencies,
    help_handler,
    last_handler,
    limits_handler,
    report_handler,
    resync_handler,
    status_handler,
    track_handler,
)
from dota_dog.domain.enums import PeriodType
from dota_dog.infra.db.base import Base
from dota_dog.infra.db.models import PlayerMatchORM
from dota_dog.infra.db.repositories.core import (
    PlayerRepository,
    ReportRunRepository,
    TopicPlayerRepository,
    TopicRepository,
    TopicRuntimeRepository,
)
from dota_dog.infra.opendota.client import OpenDotaRateLimitSnapshot
from dota_dog.infra.opendota.schemas import OpenDotaProfileResponse
from dota_dog.services.backfill import BackfillService
from dota_dog.services.constants import ConstantsService
from dota_dog.services.formatter import MessageFormatter
from dota_dog.services.permissions import PermissionService
from dota_dog.services.reporting import ReportingService
from dota_dog.services.tracking import TrackingService


class FakeOpenDotaClient:
    def __init__(self) -> None:
        self.rate_limits = OpenDotaRateLimitSnapshot(
            server_time=datetime(2026, 3, 11, 8, 1, 54, tzinfo=UTC),
            remaining_minute=2,
            limit_minute=60,
            remaining_day=2744,
            limit_day=30000,
            recommended_pause_seconds=3.0,
        )

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

    async def get_match_players(self, match_id: int) -> list[object]:
        return []

    async def get_rate_limits(self, *, refresh: bool = False) -> OpenDotaRateLimitSnapshot | None:
        return self.rate_limits


class FailingOpenDotaClient(FakeOpenDotaClient):
    async def get_player_matches(
        self,
        account_id: int,
        *,
        days: int,
        limit: int,
        offset: int,
    ) -> list[object]:
        msg = "OpenDota unavailable"
        raise RuntimeError(msg)


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
    return _make_deps_with_client(session_factory, FakeOpenDotaClient())


def _make_deps_with_client(
    session_factory: async_sessionmaker,
    client: Any,
) -> HandlerDependencies:
    tracking_service = TrackingService()
    return HandlerDependencies(
        session_factory=session_factory,
        opendota_client=client,
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
async def test_help_handler_lists_available_commands() -> None:
    message = FakeMessage(text="/help", chat_type="private")

    await help_handler(message)

    assert len(message.answers) == 1
    help_text = message.answers[0][0]
    assert "Доступные команды:" in help_text
    assert "/help - Показывает этот список команд." in help_text
    assert "/limits - Показывает текущие лимиты запросов к OpenDota API." in help_text
    assert "Команды для группы или topic:" in help_text
    assert "/players - Показывает список отслеживаемых игроков" in help_text
    assert "/track <account_id|profile_url> [alias]" in help_text
    assert "Для админов чата или разрешенных пользователей:" in help_text


@pytest.mark.asyncio
async def test_limits_handler_returns_current_rate_limits() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    deps = _make_deps(session_factory)
    message = FakeMessage(text="/limits", chat_type="private")

    await limits_handler(message, deps)

    assert len(message.answers) == 1
    limits_text = message.answers[0][0]
    assert "Лимиты OpenDota API:" in limits_text
    assert "Обновлено: 2026-03-11 08:01 UTC" in limits_text
    assert "В минуту: 2/60" in limits_text
    assert "В день: 2744/30000" in limits_text
    assert "Рекомендуемая пауза: 3.0 сек." in limits_text

    await engine.dispose()


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
async def test_status_handler_returns_extended_topic_summary() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        topic = await TopicRepository(session).get_or_create(
            telegram_chat_id=-1001,
            telegram_thread_id=10,
            title="Test topic",
            timezone="Europe/Moscow",
        )
        mid = await PlayerRepository(session).get_or_create(
            dota_account_id=123456,
            display_name="Sega",
            profile_url="https://www.dotabuff.com/players/123456",
        )
        support = await PlayerRepository(session).get_or_create(
            dota_account_id=222222,
            display_name="Pablo",
            profile_url="https://www.dotabuff.com/players/222222",
        )
        mid_relation = await TopicPlayerRepository(session).add_player(
            topic_id=topic.id,
            player_id=mid.id,
            alias="mid",
            added_by_telegram_user_id=1,
        )
        support_relation = await TopicPlayerRepository(session).add_player(
            topic_id=topic.id,
            player_id=support.id,
            alias=None,
            added_by_telegram_user_id=1,
        )
        assert mid_relation is not None
        assert support_relation is not None
        mid_relation.last_seen_match_id = 1002
        runtime_repo = TopicRuntimeRepository(session)
        await runtime_repo.mark_succeeded(
            topic.id,
            started_at=datetime(2026, 3, 11, 8, 0, tzinfo=UTC),
            finished_at=datetime(2026, 3, 11, 8, 2, 30, tzinfo=UTC),
        )
        session.add_all(
            [
                PlayerMatchORM(
                    player_id=mid.id,
                    match_id=1001,
                    start_time=datetime(2026, 3, 11, 6, 50, tzinfo=UTC),
                    end_time=datetime(2026, 3, 11, 7, 30, tzinfo=UTC),
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
                    created_at=datetime(2026, 3, 11, 7, 31, tzinfo=UTC),
                ),
                PlayerMatchORM(
                    player_id=support.id,
                    match_id=1002,
                    start_time=datetime(2026, 3, 11, 7, 0, tzinfo=UTC),
                    end_time=datetime(2026, 3, 11, 7, 45, tzinfo=UTC),
                    hero_id=5,
                    radiant_win=False,
                    player_slot=128,
                    kills=2,
                    deaths=8,
                    assists=21,
                    gpm=320,
                    xpm=500,
                    hero_damage=9000,
                    tower_damage=400,
                    hero_healing=1200,
                    last_hits=44,
                    game_mode=22,
                    lobby_type=7,
                    party_size=2,
                    raw_payload={},
                    created_at=datetime(2026, 3, 11, 7, 46, tzinfo=UTC),
                ),
            ]
        )
        report_repo = ReportRunRepository(session)
        report = await report_repo.create(
            topic_id=topic.id,
            period_type=PeriodType.DAY.value,
            period_start=datetime(2026, 3, 10, 0, 0, tzinfo=UTC),
            period_end=datetime(2026, 3, 11, 0, 0, tzinfo=UTC),
            trigger_source="auto",
            telegram_message_id=None,
        )
        report.created_at = datetime(2026, 3, 11, 8, 5, tzinfo=UTC)
        await session.commit()

    deps = _make_deps(session_factory)
    message = FakeMessage(text="/status")

    await status_handler(message, deps)

    assert len(message.answers) == 1
    text = message.answers[0][0]
    assert "<b>Topic Status</b>" in text
    assert "Title: Test topic" in text
    assert "Chat ID: -1001" in text
    assert "Thread ID: 10" in text
    assert "<b>Config</b>" in text
    assert "Timezone: Europe/Moscow" in text
    assert "Realtime paused: no" in text
    assert "Poll interval: 15 min" in text
    assert "Players: 2 (1 initialized)" in text
    assert "<b>Polling</b>" in text
    assert "State: ok" in text
    assert "Last start: 2026-03-11 11:00 MSK" in text
    assert "Last finish: 2026-03-11 11:02 MSK" in text
    assert "Last success: 2026-03-11 11:02 MSK" in text
    assert "Last run duration: 2 min 30 sec" in text
    assert "Next poll: 2026-03-11 11:17 MSK" in text
    assert "Last error: none" in text
    assert "<b>Data</b>" in text
    assert "Match rows: 2" in text
    assert "Unique matches: 2" in text
    assert "Latest match in DB: 2026-03-11 10:45 MSK" in text
    assert "<b>Recent Reports</b>" in text
    assert (
        "- day: 2026-03-11 11:05 MSK (auto, 2026-03-10 03:00 MSK .. 2026-03-11 03:00 MSK)"
        in text
    )
    assert "- week: none" in text
    assert "- month: none" in text
    assert "<b>Players</b>" in text
    assert "- mid (123456) · last seen 1002" in text
    assert "- Pablo (222222) · last seen not initialized" in text
    assert message.answers[0][1]["parse_mode"] == "HTML"

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
            timezone="Europe/Moscow",
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


@pytest.mark.asyncio
async def test_last_handler_groups_shared_match_into_single_block() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        topic = await TopicRepository(session).get_or_create(
            telegram_chat_id=-1001,
            telegram_thread_id=10,
            title="Test topic",
            timezone="Europe/Moscow",
        )
        bigbaby = await PlayerRepository(session).get_or_create(
            dota_account_id=111111,
            display_name="BIGBABY",
            profile_url="https://www.dotabuff.com/players/111111",
        )
        sega = await PlayerRepository(session).get_or_create(
            dota_account_id=222222,
            display_name="Sega",
            profile_url="https://www.dotabuff.com/players/222222",
        )
        await TopicPlayerRepository(session).add_player(
            topic_id=topic.id,
            player_id=bigbaby.id,
            alias="BIGBABY",
            added_by_telegram_user_id=1,
        )
        await TopicPlayerRepository(session).add_player(
            topic_id=topic.id,
            player_id=sega.id,
            alias="sega",
            added_by_telegram_user_id=1,
        )
        session.add_all(
            [
                PlayerMatchORM(
                    player_id=bigbaby.id,
                    match_id=2002,
                    start_time=datetime(2026, 3, 11, 8, 10, tzinfo=UTC),
                    end_time=datetime(2026, 3, 11, 9, 2, tzinfo=UTC),
                    hero_id=74,
                    radiant_win=False,
                    player_slot=0,
                    kills=13,
                    deaths=10,
                    assists=18,
                    gpm=425,
                    xpm=700,
                    hero_damage=27187,
                    tower_damage=1687,
                    hero_healing=0,
                    last_hits=185,
                    game_mode=22,
                    lobby_type=7,
                    party_size=2,
                    raw_payload={},
                    created_at=datetime(2026, 3, 11, 9, 3, tzinfo=UTC),
                ),
                PlayerMatchORM(
                    player_id=sega.id,
                    match_id=2002,
                    start_time=datetime(2026, 3, 11, 8, 10, tzinfo=UTC),
                    end_time=datetime(2026, 3, 11, 9, 2, tzinfo=UTC),
                    hero_id=5,
                    radiant_win=False,
                    player_slot=0,
                    kills=2,
                    deaths=8,
                    assists=21,
                    gpm=320,
                    xpm=500,
                    hero_damage=9000,
                    tower_damage=400,
                    hero_healing=1200,
                    last_hits=44,
                    game_mode=22,
                    lobby_type=7,
                    party_size=2,
                    raw_payload={},
                    created_at=datetime(2026, 3, 11, 9, 3, tzinfo=UTC),
                ),
                PlayerMatchORM(
                    player_id=bigbaby.id,
                    match_id=2001,
                    start_time=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
                    end_time=datetime(2026, 3, 10, 12, 30, tzinfo=UTC),
                    hero_id=138,
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
                ),
            ]
        )
        await session.commit()

    deps = _make_deps(session_factory)
    message = FakeMessage(text="/last 1")

    await last_handler(message, deps)

    assert len(message.answers) == 1
    text = message.answers[0][0]
    assert "BIGBABY" in text
    assert "sega" in text
    assert "Crystal Maiden" in text
    assert "Muerta" not in text
    assert "<b>Ended</b>: 2026-03-11 12:02 MSK (52 min)" in text
    assert text.count("<b>Ended</b>:") == 1
    assert text.count("Dotabuff") == 1
    assert message.answers[0][1]["parse_mode"] == "HTML"
    assert message.answers[0][1]["disable_web_page_preview"] is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_last_handler_keeps_shared_players_when_filtered() -> None:
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
        bigbaby = await PlayerRepository(session).get_or_create(
            dota_account_id=111111,
            display_name="BIGBABY",
            profile_url="https://www.dotabuff.com/players/111111",
        )
        sega = await PlayerRepository(session).get_or_create(
            dota_account_id=222222,
            display_name="Sega",
            profile_url="https://www.dotabuff.com/players/222222",
        )
        await TopicPlayerRepository(session).add_player(
            topic_id=topic.id,
            player_id=bigbaby.id,
            alias="BIGBABY",
            added_by_telegram_user_id=1,
        )
        await TopicPlayerRepository(session).add_player(
            topic_id=topic.id,
            player_id=sega.id,
            alias="sega",
            added_by_telegram_user_id=1,
        )
        session.add_all(
            [
                PlayerMatchORM(
                    player_id=bigbaby.id,
                    match_id=2002,
                    start_time=datetime(2026, 3, 11, 8, 10, tzinfo=UTC),
                    end_time=datetime(2026, 3, 11, 9, 2, tzinfo=UTC),
                    hero_id=74,
                    radiant_win=False,
                    player_slot=0,
                    kills=13,
                    deaths=10,
                    assists=18,
                    gpm=425,
                    xpm=700,
                    hero_damage=27187,
                    tower_damage=1687,
                    hero_healing=0,
                    last_hits=185,
                    game_mode=22,
                    lobby_type=7,
                    party_size=2,
                    raw_payload={},
                    created_at=datetime(2026, 3, 11, 9, 3, tzinfo=UTC),
                ),
                PlayerMatchORM(
                    player_id=sega.id,
                    match_id=2002,
                    start_time=datetime(2026, 3, 11, 8, 10, tzinfo=UTC),
                    end_time=datetime(2026, 3, 11, 9, 2, tzinfo=UTC),
                    hero_id=5,
                    radiant_win=False,
                    player_slot=0,
                    kills=2,
                    deaths=8,
                    assists=21,
                    gpm=320,
                    xpm=500,
                    hero_damage=9000,
                    tower_damage=400,
                    hero_healing=1200,
                    last_hits=44,
                    game_mode=22,
                    lobby_type=7,
                    party_size=2,
                    raw_payload={},
                    created_at=datetime(2026, 3, 11, 9, 3, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()

    deps = _make_deps(session_factory)
    message = FakeMessage(text="/last 1 BIGBABY")

    await last_handler(message, deps)

    assert len(message.answers) == 1
    text = message.answers[0][0]
    assert "BIGBABY" in text
    assert "sega" in text
    assert text.count("Dotabuff") == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_resync_handler_reports_progress_and_result() -> None:
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
        await session.commit()

    deps = _make_deps(session_factory)
    message = FakeMessage(text="/resync 7")

    await resync_handler(message, deps)

    assert len(message.answers) == 2
    assert "Запускаю resync" in message.answers[0][0]
    assert "Resync for last 7 day(s):" in message.answers[1][0]
    assert "mid: fetched 0, inserted 0" in message.answers[1][0]

    await engine.dispose()


@pytest.mark.asyncio
async def test_resync_handler_reports_errors_in_chat() -> None:
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
        await session.commit()

    deps = _make_deps_with_client(session_factory, FailingOpenDotaClient())
    message = FakeMessage(text="/resync 7")

    await resync_handler(message, deps)

    assert len(message.answers) == 2
    assert "Запускаю resync" in message.answers[0][0]
    assert "Errors:" in message.answers[1][0]
    assert "mid: OpenDota unavailable" in message.answers[1][0]

    await engine.dispose()
