from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dota_dog.domain.enums import ConstantResource
from dota_dog.domain.models import (
    ConstantEntry,
    ConstantSnapshot,
    MatchSnapshot,
    TopicRuntimeStatus,
    TrackedPlayerRef,
    TrackedTopicRef,
)
from dota_dog.infra.db.models import (
    ConstantEntryORM,
    PlayerMatchORM,
    PlayerORM,
    ReportRunORM,
    TopicPlayerORM,
    TopicRuntimeStateORM,
    TrackedTopicORM,
)


class TopicRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self,
        *,
        telegram_chat_id: int,
        telegram_thread_id: int | None,
        title: str | None,
        timezone: str,
    ) -> TrackedTopicORM:
        query = select(TrackedTopicORM).where(
            TrackedTopicORM.telegram_chat_id == telegram_chat_id,
            TrackedTopicORM.telegram_thread_id == telegram_thread_id,
        )
        topic = await self._session.scalar(query)
        if topic is not None:
            return topic
        topic = TrackedTopicORM(
            telegram_chat_id=telegram_chat_id,
            telegram_thread_id=telegram_thread_id,
            title=title,
            timezone=timezone,
        )
        self._session.add(topic)
        await self._session.flush()
        return topic

    async def get_by_chat_thread(
        self, telegram_chat_id: int, telegram_thread_id: int | None
    ) -> TrackedTopicORM | None:
        return await self._session.scalar(
            select(TrackedTopicORM).where(
                TrackedTopicORM.telegram_chat_id == telegram_chat_id,
                TrackedTopicORM.telegram_thread_id == telegram_thread_id,
            )
        )

    async def list_refs(self) -> list[TrackedTopicRef]:
        rows = await self._session.scalars(select(TrackedTopicORM))
        return [
            TrackedTopicRef(
                id=row.id,
                telegram_chat_id=row.telegram_chat_id,
                telegram_thread_id=row.telegram_thread_id,
                title=row.title,
                timezone=row.timezone,
                is_paused=row.is_paused,
            )
            for row in rows
        ]

    async def update_timezone(self, topic_id: int, timezone: str) -> None:
        topic = await self._session.get(TrackedTopicORM, topic_id)
        if topic is not None:
            topic.timezone = timezone
            await self._session.flush()

    async def set_paused(self, topic_id: int, is_paused: bool) -> None:
        topic = await self._session.get(TrackedTopicORM, topic_id)
        if topic is not None:
            topic.is_paused = is_paused
            await self._session.flush()


class PlayerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self, *, dota_account_id: int, display_name: str, profile_url: str | None
    ) -> PlayerORM:
        player = await self._session.scalar(
            select(PlayerORM).where(PlayerORM.dota_account_id == dota_account_id)
        )
        if player is not None:
            player.display_name = display_name
            player.profile_url = profile_url
            return player
        player = PlayerORM(
            dota_account_id=dota_account_id,
            display_name=display_name,
            profile_url=profile_url,
        )
        self._session.add(player)
        await self._session.flush()
        return player

    async def get_by_account_id(self, dota_account_id: int) -> PlayerORM | None:
        return await self._session.scalar(
            select(PlayerORM).where(PlayerORM.dota_account_id == dota_account_id)
        )


class TopicPlayerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_player(
        self,
        *,
        topic_id: int,
        player_id: int,
        alias: str | None,
        added_by_telegram_user_id: int | None,
    ) -> TopicPlayerORM | None:
        existing = await self._session.scalar(
            select(TopicPlayerORM).where(
                TopicPlayerORM.topic_id == topic_id,
                TopicPlayerORM.player_id == player_id,
            )
        )
        if existing is not None:
            return None
        relation = TopicPlayerORM(
            topic_id=topic_id,
            player_id=player_id,
            alias=alias,
            added_by_telegram_user_id=added_by_telegram_user_id,
        )
        self._session.add(relation)
        await self._session.flush()
        return relation

    async def remove_player(self, topic_id: int, account_or_alias: str) -> bool:
        filters = [TopicPlayerORM.alias == account_or_alias]
        if account_or_alias.isdigit():
            filters.append(PlayerORM.dota_account_id == int(account_or_alias))
        stmt: Select[tuple[TopicPlayerORM]] = (
            select(TopicPlayerORM)
            .join(PlayerORM, TopicPlayerORM.player_id == PlayerORM.id)
            .where(
                TopicPlayerORM.topic_id == topic_id,
                or_(*filters),
            )
        )
        relation = await self._session.scalar(stmt)
        if relation is None:
            return False
        await self._session.delete(relation)
        return True

    async def list_topic_players(self, topic_id: int) -> list[TrackedPlayerRef]:
        rows = await self._session.scalars(
            select(TopicPlayerORM)
            .options(selectinload(TopicPlayerORM.player))
            .where(TopicPlayerORM.topic_id == topic_id)
        )
        refs: list[TrackedPlayerRef] = []
        for row in rows:
            refs.append(
                TrackedPlayerRef(
                    player_id=row.player.id,
                    dota_account_id=row.player.dota_account_id,
                    display_name=row.player.display_name,
                    profile_url=row.player.profile_url,
                    alias=row.alias,
                    last_seen_match_id=row.last_seen_match_id,
                )
            )
        return refs

    async def set_last_seen_match_id(self, topic_id: int, player_id: int, match_id: int) -> None:
        relation = await self._session.scalar(
            select(TopicPlayerORM).where(
                TopicPlayerORM.topic_id == topic_id,
                TopicPlayerORM.player_id == player_id,
            )
        )
        if relation is not None:
            relation.last_seen_match_id = match_id


class MatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_new_matches(self, matches: Sequence[MatchSnapshot]) -> list[MatchSnapshot]:
        if not matches:
            return []
        player_id = matches[0].player_id
        match_ids = [match.match_id for match in matches]
        existing_ids = set(
            await self._session.scalars(
                select(PlayerMatchORM.match_id).where(
                    PlayerMatchORM.player_id == player_id,
                    PlayerMatchORM.match_id.in_(match_ids),
                )
            )
        )
        inserted: list[MatchSnapshot] = []
        for match in matches:
            if match.match_id in existing_ids:
                continue
            self._session.add(
                PlayerMatchORM(
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
            )
            inserted.append(match)
        await self._session.flush()
        return inserted

    async def list_matches_for_players(
        self, player_ids: Sequence[int], period_start: datetime, period_end: datetime
    ) -> list[PlayerMatchORM]:
        result = await self._session.scalars(
            select(PlayerMatchORM).where(
                PlayerMatchORM.player_id.in_(player_ids),
                PlayerMatchORM.end_time >= period_start,
                PlayerMatchORM.end_time < period_end,
            )
        )
        return list(result)

    async def list_recent_matches_for_players(
        self,
        player_ids: Sequence[int],
        *,
        limit: int,
    ) -> list[PlayerMatchORM]:
        result = await self._session.scalars(
            select(PlayerMatchORM)
            .where(PlayerMatchORM.player_id.in_(player_ids))
            .order_by(PlayerMatchORM.end_time.desc())
            .limit(limit)
        )
        return list(result)


class ReportRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def has_run(
        self, topic_id: int, period_type: str, period_start: datetime, period_end: datetime
    ) -> bool:
        count = await self._session.scalar(
            select(func.count(ReportRunORM.id)).where(
                ReportRunORM.topic_id == topic_id,
                ReportRunORM.period_type == period_type,
                ReportRunORM.period_start == period_start,
                ReportRunORM.period_end == period_end,
            )
        )
        return bool(count)

    async def create(
        self,
        *,
        topic_id: int,
        period_type: str,
        period_start: datetime,
        period_end: datetime,
        trigger_source: str,
        telegram_message_id: int | None,
    ) -> ReportRunORM:
        report = ReportRunORM(
            topic_id=topic_id,
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
            trigger_source=trigger_source,
            telegram_message_id=telegram_message_id,
        )
        self._session.add(report)
        await self._session.flush()
        return report


class TopicRuntimeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_status(self, topic_id: int) -> TopicRuntimeStatus | None:
        state = await self._session.scalar(
            select(TopicRuntimeStateORM).where(TopicRuntimeStateORM.topic_id == topic_id)
        )
        if state is None:
            return None
        return TopicRuntimeStatus(
            topic_id=state.topic_id,
            last_poll_started_at=_ensure_utc(state.last_poll_started_at),
            last_poll_finished_at=_ensure_utc(state.last_poll_finished_at),
            last_poll_succeeded_at=_ensure_utc(state.last_poll_succeeded_at),
            last_poll_error=state.last_poll_error,
        )

    async def mark_started(self, topic_id: int, started_at: datetime) -> None:
        state = await self._get_or_create(topic_id)
        state.last_poll_started_at = started_at
        state.last_poll_error = None
        await self._session.flush()

    async def mark_succeeded(
        self,
        topic_id: int,
        *,
        started_at: datetime,
        finished_at: datetime,
    ) -> None:
        state = await self._get_or_create(topic_id)
        state.last_poll_started_at = started_at
        state.last_poll_finished_at = finished_at
        state.last_poll_succeeded_at = finished_at
        state.last_poll_error = None
        await self._session.flush()

    async def mark_failed(
        self,
        topic_id: int,
        *,
        started_at: datetime,
        finished_at: datetime,
        error: str,
    ) -> None:
        state = await self._get_or_create(topic_id)
        state.last_poll_started_at = started_at
        state.last_poll_finished_at = finished_at
        state.last_poll_error = error
        await self._session.flush()

    async def _get_or_create(self, topic_id: int) -> TopicRuntimeStateORM:
        state = await self._session.scalar(
            select(TopicRuntimeStateORM).where(TopicRuntimeStateORM.topic_id == topic_id)
        )
        if state is not None:
            return state
        state = TopicRuntimeStateORM(topic_id=topic_id)
        self._session.add(state)
        await self._session.flush()
        return state


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ConstantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_entries(self, entries: Sequence[ConstantEntry]) -> None:
        if not entries:
            return
        resource = entries[0].resource.value
        existing = {
            row.code: row
            for row in await self._session.scalars(
                select(ConstantEntryORM).where(ConstantEntryORM.resource == resource)
            )
        }
        for entry in entries:
            row = existing.get(entry.code)
            if row is None:
                self._session.add(
                    ConstantEntryORM(
                        resource=entry.resource.value,
                        code=entry.code,
                        name=entry.name,
                        raw_payload=entry.raw_payload,
                    )
                )
                continue
            row.name = entry.name
            row.raw_payload = entry.raw_payload
        await self._session.flush()

    async def get_snapshot(self) -> ConstantSnapshot:
        rows = list(await self._session.scalars(select(ConstantEntryORM)))
        snapshot = ConstantSnapshot()
        for row in rows:
            if row.resource == ConstantResource.HEROES.value:
                snapshot.heroes[row.code] = row.name
            elif row.resource == ConstantResource.GAME_MODE.value:
                snapshot.game_modes[row.code] = row.name
            elif row.resource == ConstantResource.LOBBY_TYPE.value:
                snapshot.lobby_types[row.code] = row.name
        return snapshot

    async def get_last_updated_at(self, resource: ConstantResource) -> datetime | None:
        return await self._session.scalar(
            select(func.max(ConstantEntryORM.updated_at)).where(
                ConstantEntryORM.resource == resource.value
            )
        )
