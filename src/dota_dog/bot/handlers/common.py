from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from dota_dog.domain.enums import PeriodType
from dota_dog.domain.models import MatchSnapshot
from dota_dog.infra.db.models import PlayerMatchORM
from dota_dog.infra.db.repositories.core import (
    MatchRepository,
    PlayerRepository,
    TopicPlayerRepository,
    TopicRepository,
    TopicRuntimeRepository,
)
from dota_dog.infra.opendota.client import OpenDotaClient
from dota_dog.services.backfill import BackfillService
from dota_dog.services.constants import ConstantsService
from dota_dog.services.formatter import MessageFormatter
from dota_dog.services.permissions import PermissionService
from dota_dog.services.reporting import ReportingService

router = Router()
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HandlerDependencies:
    session_factory: async_sessionmaker
    opendota_client: OpenDotaClient
    reporting_service: ReportingService
    formatter: MessageFormatter
    constants_service: ConstantsService
    backfill_service: BackfillService
    permission_service: PermissionService
    poll_interval_minutes: int
    default_timezone: str


def _is_group_message(message: Message) -> bool:
    return message.chat.type in {"group", "supergroup"}


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


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _parse_account_id(raw_value: str) -> int | None:
    if raw_value.isdigit():
        return int(raw_value)
    match = re.search(r"/players/(\d+)", raw_value)
    if match is not None:
        return int(match.group(1))
    return None


async def _require_manage_permission(message: Message, deps: HandlerDependencies) -> bool:
    if message.bot is None:
        await message.answer("Bot context is unavailable.")
        return False
    allowed = await deps.permission_service.can_manage_topic(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id if message.from_user else None,
    )
    if allowed:
        return True
    await message.answer("Команда доступна только админам чата или разрешенным пользователям.")
    return False


@router.message(Command("players"))
async def players_handler(message: Message, deps: HandlerDependencies) -> None:
    if not _is_group_message(message):
        await message.answer("Команда доступна только в группе или topic.")
        return
    async with deps.session_factory() as session:
        topics = TopicRepository(session)
        topic = await topics.get_by_chat_thread(message.chat.id, message.message_thread_id)
        if topic is None:
            await message.answer("В этом topic пока нет отслеживаемых игроков.")
            return
        players = await TopicPlayerRepository(session).list_topic_players(topic.id)
        if not players:
            await message.answer("В этом topic пока нет отслеживаемых игроков.")
            return
        lines = [
            f"{player.alias or player.display_name} ({player.dota_account_id})"
            for player in players
        ]
        await message.answer("\n".join(lines))


@router.message(Command("track"))
async def track_handler(message: Message, deps: HandlerDependencies) -> None:
    if not _is_group_message(message):
        await message.answer("Добавление игроков доступно только в группе или topic.")
        return
    if not await _require_manage_permission(message, deps):
        return
    args = (message.text or "").split(maxsplit=2)
    if len(args) < 2:
        await message.answer("Использование: /track <account_id> [alias]")
        return
    account_id = _parse_account_id(args[1])
    if account_id is None:
        await message.answer(
            "Не удалось распознать `account_id` или profile URL.",
            parse_mode="Markdown",
        )
        return
    alias = args[2] if len(args) > 2 else None
    profile = await deps.opendota_client.get_profile(account_id)
    if profile.account_id is None or profile.personaname is None:
        await message.answer("OpenDota не вернул корректный профиль игрока.")
        return
    async with deps.session_factory() as session:
        topics = TopicRepository(session)
        players = PlayerRepository(session)
        topic_players = TopicPlayerRepository(session)
        topic = await topics.get_or_create(
            telegram_chat_id=message.chat.id,
            telegram_thread_id=message.message_thread_id,
            title=message.chat.title,
            timezone=deps.default_timezone,
        )
        player = await players.get_or_create(
            dota_account_id=profile.account_id,
            display_name=profile.personaname,
            profile_url=profile.profile_url,
        )
        relation = await topic_players.add_player(
            topic_id=topic.id,
            player_id=player.id,
            alias=alias,
            added_by_telegram_user_id=message.from_user.id if message.from_user else None,
        )
        await session.commit()
    if relation is None:
        await message.answer("Игрок уже отслеживается в этом topic.")
        return
    await message.answer(f"Добавлен {alias or profile.personaname} ({profile.account_id}).")


@router.message(Command("status"))
async def status_handler(message: Message, deps: HandlerDependencies) -> None:
    if not _is_group_message(message):
        await message.answer("Команда доступна только в группе или topic.")
        return
    async with deps.session_factory() as session:
        topic = await TopicRepository(session).get_by_chat_thread(
            message.chat.id,
            message.message_thread_id,
        )
        if topic is None:
            await message.answer("Topic еще не инициализирован.")
            return
        players = await TopicPlayerRepository(session).list_topic_players(topic.id)
        runtime_status = await TopicRuntimeRepository(session).get_status(topic.id)
    next_poll_at = None
    if runtime_status is not None and runtime_status.last_poll_succeeded_at is not None:
        next_poll_at = runtime_status.last_poll_succeeded_at + timedelta(
            minutes=deps.poll_interval_minutes
        )
    await message.answer(
        f"Players: {len(players)}\n"
        f"Timezone: {topic.timezone}\n"
        f"Paused: {'yes' if topic.is_paused else 'no'}\n"
        f"Last poll start: "
        f"{_fmt_dt(runtime_status.last_poll_started_at if runtime_status else None)}\n"
        f"Last poll success: "
        f"{_fmt_dt(runtime_status.last_poll_succeeded_at if runtime_status else None)}\n"
        f"Next poll: {_fmt_dt(next_poll_at)}\n"
        f"Last error: {runtime_status.last_poll_error if runtime_status else '-'}"
    )


@router.message(Command("untrack"))
async def untrack_handler(message: Message, deps: HandlerDependencies) -> None:
    if not _is_group_message(message):
        await message.answer("Удаление игроков доступно только в группе или topic.")
        return
    if not await _require_manage_permission(message, deps):
        return
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /untrack <account_id|alias>")
        return
    async with deps.session_factory() as session:
        topic = await TopicRepository(session).get_by_chat_thread(
            message.chat.id,
            message.message_thread_id,
        )
        if topic is None:
            await message.answer("В этом topic нет отслеживаемых игроков.")
            return
        removed = await TopicPlayerRepository(session).remove_player(topic.id, args[1])
        if not removed:
            await message.answer("Игрок не найден в этом topic.")
            return
        await session.commit()
    await message.answer(f"Игрок {args[1]} удален из topic.")


@router.message(Command("report"))
async def report_handler(message: Message, deps: HandlerDependencies) -> None:
    if not _is_group_message(message):
        await message.answer("Команда доступна только в группе или topic.")
        return
    args = (message.text or "").split(maxsplit=2)
    if len(args) < 2 or args[1] not in {item.value for item in PeriodType}:
        await message.answer("Использование: /report <day|week|month> [account_id|alias]")
        return
    period_type = PeriodType(args[1])
    player_filter = args[2] if len(args) > 2 else None
    async with deps.session_factory() as session:
        topic = await TopicRepository(session).get_by_chat_thread(
            message.chat.id,
            message.message_thread_id,
        )
        if topic is None:
            await message.answer("В этом topic нет данных для отчета.")
            return
        players = await TopicPlayerRepository(session).list_topic_players(topic.id)
        if not players:
            await message.answer("В этом topic нет отслеживаемых игроков.")
            return
        period_start, period_end = deps.reporting_service.calculate_period_bounds(
            period_type=period_type,
            now=datetime.now(UTC),
            timezone_name=topic.timezone,
        )
        orm_matches = await MatchRepository(session).list_matches_for_players(
            [player.player_id for player in players],
            period_start,
            period_end,
        )
        constants = await deps.constants_service.get_snapshot(session)
    summaries = deps.reporting_service.build_topic_summaries(
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        players=players,
        matches=[_orm_to_snapshot(match) for match in orm_matches],
        player_filter=player_filter,
    )
    if player_filter is not None and not summaries:
        await message.answer("Игрок для отчета не найден в этом topic.")
        return
    if not summaries:
        await message.answer("Для выбранного периода данных нет.")
        return
    text = "\n\n".join(deps.formatter.format_report(summary, constants) for summary in summaries)
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("pause"))
async def pause_handler(message: Message, deps: HandlerDependencies) -> None:
    if not _is_group_message(message):
        await message.answer("Команда доступна только в группе или topic.")
        return
    if not await _require_manage_permission(message, deps):
        return
    async with deps.session_factory() as session:
        topics = TopicRepository(session)
        topic = await topics.get_or_create(
            telegram_chat_id=message.chat.id,
            telegram_thread_id=message.message_thread_id,
            title=message.chat.title,
            timezone=deps.default_timezone,
        )
        await topics.set_paused(topic.id, True)
        await session.commit()
    await message.answer("Realtime-уведомления для topic поставлены на паузу.")


@router.message(Command("resume"))
async def resume_handler(message: Message, deps: HandlerDependencies) -> None:
    if not _is_group_message(message):
        await message.answer("Команда доступна только в группе или topic.")
        return
    if not await _require_manage_permission(message, deps):
        return
    async with deps.session_factory() as session:
        topics = TopicRepository(session)
        topic = await topics.get_or_create(
            telegram_chat_id=message.chat.id,
            telegram_thread_id=message.message_thread_id,
            title=message.chat.title,
            timezone=deps.default_timezone,
        )
        await topics.set_paused(topic.id, False)
        await session.commit()
    await message.answer("Realtime-уведомления для topic возобновлены.")


@router.message(Command("set_timezone"))
async def set_timezone_handler(message: Message, deps: HandlerDependencies) -> None:
    if not _is_group_message(message):
        await message.answer("Команда доступна только в группе или topic.")
        return
    if not await _require_manage_permission(message, deps):
        return
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /set_timezone <TZ>")
        return
    timezone_name = args[1].strip()
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        await message.answer("Неизвестная таймзона. Пример: Europe/Moscow")
        return
    async with deps.session_factory() as session:
        topics = TopicRepository(session)
        topic = await topics.get_or_create(
            telegram_chat_id=message.chat.id,
            telegram_thread_id=message.message_thread_id,
            title=message.chat.title,
            timezone=deps.default_timezone,
        )
        await topics.update_timezone(topic.id, timezone_name)
        await session.commit()
    await message.answer(f"Таймзона topic обновлена: {timezone_name}")


@router.message(Command("last"))
async def last_handler(message: Message, deps: HandlerDependencies) -> None:
    if not _is_group_message(message):
        await message.answer("Команда доступна только в группе или topic.")
        return
    args = (message.text or "").split(maxsplit=2)
    count = 5
    player_filter: str | None = None
    if len(args) >= 2:
        if args[1].isdigit():
            count = max(1, min(int(args[1]), 10))
            if len(args) == 3:
                player_filter = args[2]
        else:
            player_filter = args[1]
    async with deps.session_factory() as session:
        topic = await TopicRepository(session).get_by_chat_thread(
            message.chat.id,
            message.message_thread_id,
        )
        if topic is None:
            await message.answer("В этом topic нет данных.")
            return
        players = await TopicPlayerRepository(session).list_topic_players(topic.id)
        selected_players = deps.reporting_service.select_players(players, player_filter)
        if player_filter is not None and not selected_players:
            await message.answer("Игрок не найден в этом topic.")
            return
        orm_matches = await MatchRepository(session).list_recent_matches_for_players(
            [player.player_id for player in selected_players or players],
            limit=count,
        )
        constants = await deps.constants_service.get_snapshot(session)
    player_by_id = {player.player_id: player for player in players}
    items = [
        (player_by_id[match.player_id], _orm_to_snapshot(match))
        for match in orm_matches
        if match.player_id in player_by_id
    ]
    text = deps.formatter.format_recent_matches("Last matches", items, constants)
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("leaders"))
async def leaders_handler(message: Message, deps: HandlerDependencies) -> None:
    if not _is_group_message(message):
        await message.answer("Команда доступна только в группе или topic.")
        return
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or args[1] not in {item.value for item in PeriodType}:
        await message.answer("Использование: /leaders <day|week|month>")
        return
    period_type = PeriodType(args[1])
    async with deps.session_factory() as session:
        topic = await TopicRepository(session).get_by_chat_thread(
            message.chat.id,
            message.message_thread_id,
        )
        if topic is None:
            await message.answer("В этом topic нет данных.")
            return
        players = await TopicPlayerRepository(session).list_topic_players(topic.id)
        period_start, period_end = deps.reporting_service.calculate_period_bounds(
            period_type=period_type,
            now=datetime.now(UTC),
            timezone_name=topic.timezone,
        )
        orm_matches = await MatchRepository(session).list_matches_for_players(
            [player.player_id for player in players],
            period_start,
            period_end,
        )
    summaries = deps.reporting_service.build_topic_summaries(
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        players=players,
        matches=[_orm_to_snapshot(match) for match in orm_matches],
    )
    summaries.sort(
        key=lambda summary: (summary.winrate, summary.wins, summary.matches_count),
        reverse=True,
    )
    text = deps.formatter.format_leaderboard(
        title=f"Leaders {period_type.value}",
        summaries=summaries[:10],
    )
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("resync"))
async def resync_handler(message: Message, deps: HandlerDependencies) -> None:
    if not _is_group_message(message):
        await message.answer("Команда доступна только в группе или topic.")
        return
    if not await _require_manage_permission(message, deps):
        return
    args = (message.text or "").split(maxsplit=2)
    days = 7
    player_filter: str | None = None
    if len(args) >= 2:
        if args[1].isdigit():
            days = max(1, min(int(args[1]), 365))
            if len(args) == 3:
                player_filter = args[2]
        else:
            player_filter = args[1]
    async with deps.session_factory() as session:
        topic = await TopicRepository(session).get_by_chat_thread(
            message.chat.id,
            message.message_thread_id,
        )
        if topic is None:
            await message.answer("В этом topic нет данных для resync.")
            return
        players = await TopicPlayerRepository(session).list_topic_players(topic.id)
        selected_players = deps.reporting_service.select_players(players, player_filter)
        if player_filter is not None and not selected_players:
            await message.answer("Игрок не найден в этом topic.")
            return
        scope = selected_players or players
        await message.answer(
            f"Запускаю resync за последние {days} дн. для {len(scope)} игрок(ов). "
            "Это может занять до нескольких минут."
        )
        results = []
        failures = []
        for player in scope:
            try:
                result = await deps.backfill_service.resync_player(
                    session=session,
                    client=deps.opendota_client,
                    topic_id=topic.id,
                    player=player,
                    days=days,
                )
                results.append(result)
            except Exception as exc:
                player_label = player.alias or player.display_name
                logger.exception(
                    "resync failed",
                    extra={
                        "chat_id": message.chat.id,
                        "thread_id": message.message_thread_id,
                        "topic_id": topic.id,
                        "player_id": player.player_id,
                        "dota_account_id": player.dota_account_id,
                    },
                )
                failures.append(f"{player_label}: {exc}")
        await session.commit()
    lines = [f"Resync for last {days} day(s):"]
    for result in results:
        line = (
            f"{result.player_label}: fetched {result.fetched_matches}, "
            f"inserted {result.inserted_matches}"
        )
        if result.failed_matches:
            line += f", failed {result.failed_matches}"
        lines.append(line)
    if failures:
        lines.append("")
        lines.append("Errors:")
        lines.extend(failures)
    await message.answer("\n".join(lines))
