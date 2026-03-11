from __future__ import annotations

import asyncio

from aiogram import Bot

from dota_dog.bootstrap import build_container
from dota_dog.domain.enums import PeriodType
from dota_dog.infra.db.runtime import check_database_connection
from dota_dog.infra.telegram.sender import TelegramSender
from dota_dog.jobs.poll_matches import PollMatchesJob
from dota_dog.jobs.send_reports import SendReportsJob
from dota_dog.logging import configure_logging
from dota_dog.settings import load_settings


async def _run_forever() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    container = build_container(settings)
    bot = Bot(token=settings.bot_token)
    sender = TelegramSender(
        bot,
        max_retries=settings.telegram_send_max_retries,
        backoff_seconds=settings.retry_backoff_seconds,
    )
    poll_job = PollMatchesJob(
        session_factory=container.session_factory,
        opendota_client=container.opendota_client,
        constants_service=container.constants_service,
        tracking_service=container.tracking_service,
        formatter=container.formatter,
        sender=sender,
    )
    report_jobs = {
        period_type: SendReportsJob(
            session_factory=container.session_factory,
            constants_service=container.constants_service,
            reporting_service=container.reporting_service,
            formatter=container.formatter,
            sender=sender,
        )
        for period_type in PeriodType
    }
    try:
        await check_database_connection(container.engine)
        while True:
            await poll_job.run_once()
            for period_type, job in report_jobs.items():
                await job.run_once(period_type)
            await asyncio.sleep(settings.poll_interval_minutes * 60)
    finally:
        await container.aclose()
        await bot.session.close()


def main() -> None:
    asyncio.run(_run_forever())


if __name__ == "__main__":
    main()
