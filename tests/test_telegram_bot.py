from __future__ import annotations

import pytest
from aiogram.client.session.aiohttp import AiohttpSession

from dota_dog.infra.telegram.bot import create_bot
from dota_dog.settings import Settings


def _make_settings(*, telegram_proxy_url: str | None = None) -> Settings:
    return Settings.model_validate(
        {
            "BOT_TOKEN": "123456:TEST_TOKEN",
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "TELEGRAM_PROXY_URL": telegram_proxy_url,
        }
    )


def test_settings_normalize_blank_proxy_url() -> None:
    settings = _make_settings(telegram_proxy_url="   ")

    assert settings.telegram_proxy_url is None


@pytest.mark.asyncio
async def test_create_bot_uses_proxy_url() -> None:
    proxy_url = "http://user:pass@127.0.0.1:8080"
    bot = create_bot(_make_settings(telegram_proxy_url=proxy_url))

    assert isinstance(bot.session, AiohttpSession)
    assert bot.session.proxy == proxy_url

    await bot.session.close()


@pytest.mark.asyncio
async def test_create_bot_without_proxy() -> None:
    bot = create_bot(_make_settings())

    assert isinstance(bot.session, AiohttpSession)
    assert bot.session.proxy is None

    await bot.session.close()
