from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter

from dota_dog.domain.models import TrackedTopicRef


class TelegramSender:
    def __init__(
        self,
        bot: Bot,
        *,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self._bot = bot
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    async def send_to_topic(self, topic: TrackedTopicRef, text: str) -> None:
        for attempt in range(1, self._max_retries + 1):
            try:
                await self._bot.send_message(
                    chat_id=topic.telegram_chat_id,
                    message_thread_id=topic.telegram_thread_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                return
            except TelegramRetryAfter as exc:
                if attempt == self._max_retries:
                    raise
                await asyncio.sleep(float(exc.retry_after))
            except TelegramNetworkError:
                if attempt == self._max_retries:
                    raise
                await asyncio.sleep(self._backoff_seconds * attempt)
