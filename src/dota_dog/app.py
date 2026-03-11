from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher

from dota_dog.bootstrap import build_container
from dota_dog.bot.handlers.common import HandlerDependencies, router
from dota_dog.infra.db.runtime import check_database_connection
from dota_dog.logging import configure_logging
from dota_dog.settings import load_settings


async def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    container = build_container(settings)
    await check_database_connection(container.engine)
    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    dispatcher["deps"] = HandlerDependencies(
        session_factory=container.session_factory,
        opendota_client=container.opendota_client,
        reporting_service=container.reporting_service,
        formatter=container.formatter,
        constants_service=container.constants_service,
        backfill_service=container.backfill_service,
        permission_service=container.permission_service,
        poll_interval_minutes=settings.poll_interval_minutes,
        default_timezone=settings.default_timezone,
    )
    try:
        await dispatcher.start_polling(bot, deps=dispatcher["deps"])
    finally:
        await container.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
