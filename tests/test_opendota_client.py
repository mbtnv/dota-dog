from __future__ import annotations

import httpx
import pytest

from dota_dog.infra.opendota.client import OpenDotaClient


def test_rate_limit_delay_uses_remaining_minute_header() -> None:
    headers = httpx.Headers(
        {
            "date": "Wed, 11 Mar 2026 08:01:54 GMT",
            "x-rate-limit-remaining-minute": "2",
            "x-rate-limit-remaining-day": "2744",
        }
    )

    delay = OpenDotaClient._rate_limit_delay_seconds(headers)

    assert delay == pytest.approx(3.0)


def test_rate_limit_delay_waits_until_next_minute_when_bucket_empty() -> None:
    headers = httpx.Headers(
        {
            "date": "Wed, 11 Mar 2026 08:01:54 GMT",
            "x-rate-limit-remaining-minute": "0",
            "x-rate-limit-remaining-day": "2744",
        }
    )

    delay = OpenDotaClient._rate_limit_delay_seconds(headers)

    assert delay == pytest.approx(6.0)


def test_rate_limit_delay_uses_remaining_day_when_quota_is_low() -> None:
    headers = httpx.Headers(
        {
            "date": "Wed, 11 Mar 2026 08:01:54 GMT",
            "x-rate-limit-remaining-minute": "54",
            "x-rate-limit-remaining-day": "2",
        }
    )

    delay = OpenDotaClient._rate_limit_delay_seconds(headers)

    assert delay == pytest.approx(28_743.0)


def test_rate_limit_delay_is_zero_without_server_date() -> None:
    headers = httpx.Headers({"x-rate-limit-remaining-minute": "1"})

    delay = OpenDotaClient._rate_limit_delay_seconds(headers)

    assert delay == 0.0
