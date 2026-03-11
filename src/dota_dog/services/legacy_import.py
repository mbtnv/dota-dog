from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from dota_dog.infra.db.repositories.core import (
    PlayerRepository,
    TopicPlayerRepository,
    TopicRepository,
)


class LegacyImportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._topics = TopicRepository(session)
        self._players = PlayerRepository(session)
        self._topic_players = TopicPlayerRepository(session)

    async def import_players_json(
        self,
        *,
        path: Path,
        telegram_chat_id: int,
        telegram_thread_id: int | None,
        title: str | None,
        timezone: str,
    ) -> int:
        payload_text = await asyncio.to_thread(path.read_text, encoding="utf-8")
        payload = json.loads(payload_text)
        topic = await self._topics.get_or_create(
            telegram_chat_id=telegram_chat_id,
            telegram_thread_id=telegram_thread_id,
            title=title,
            timezone=timezone,
        )
        inserted = 0
        for item in payload:
            player = await self._players.get_or_create(
                dota_account_id=int(item["id"]),
                display_name=str(item["name"]),
                profile_url=f"https://www.dotabuff.com/players/{int(item['id'])}",
            )
            relation = await self._topic_players.add_player(
                topic_id=topic.id,
                player_id=player.id,
                alias=None,
                added_by_telegram_user_id=None,
            )
            if relation is not None:
                relation.last_seen_match_id = int(item["last_match_id"])
                inserted += 1
        await self._session.commit()
        return inserted
