from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from aiogram.exceptions import TelegramNetworkError

logger = logging.getLogger(__name__)


async def retry_telegram_network_errors[T](
    operation: Callable[[], Awaitable[T]],
    *,
    initial_backoff_seconds: float,
    max_backoff_seconds: float = 60.0,
) -> T:
    """Retry an operation indefinitely while Telegram is temporarily unreachable."""
    failure_count = 0
    delay = min(max(initial_backoff_seconds, 0.1), max_backoff_seconds)
    while True:
        try:
            return await operation()
        except TelegramNetworkError:
            failure_count += 1
            logger.warning(
                "Telegram is unavailable; retrying in %.1f seconds (failure %d)",
                delay,
                failure_count,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_backoff_seconds)
