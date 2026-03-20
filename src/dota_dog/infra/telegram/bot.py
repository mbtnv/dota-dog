from __future__ import annotations

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from dota_dog.settings import Settings


def create_bot(settings: Settings) -> Bot:
    if settings.telegram_proxy_url is None:
        return Bot(token=settings.bot_token)

    session = AiohttpSession(proxy=settings.telegram_proxy_url)
    return Bot(token=settings.bot_token, session=session)
