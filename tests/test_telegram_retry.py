from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe

from dota_dog.infra.telegram import retry


@pytest.mark.asyncio
async def test_retry_telegram_network_errors_uses_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr(retry.asyncio, "sleep", sleep)
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise TelegramNetworkError(method=GetMe(), message="Telegram unavailable")
        return "ok"

    result = await retry.retry_telegram_network_errors(
        operation,
        initial_backoff_seconds=2.0,
        max_backoff_seconds=5.0,
    )

    assert result == "ok"
    assert attempts == 4
    assert [call.args[0] for call in sleep.await_args_list] == [2.0, 4.0, 5.0]


@pytest.mark.asyncio
async def test_retry_telegram_network_errors_does_not_hide_other_failures() -> None:
    async def operation() -> None:
        msg = "programming error"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="programming error"):
        await retry.retry_telegram_network_errors(
            operation,
            initial_backoff_seconds=1.0,
        )
