from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx

from dota_dog.infra.opendota.schemas import (
    OpenDotaPlayerMatch,
    OpenDotaProfileResponse,
    OpenDotaRecentMatch,
)


class OpenDotaClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=20.0)
        self._next_request_at_monotonic = 0.0

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_profile(self, account_id: int) -> OpenDotaProfileResponse:
        response = await self._request(
            f"/players/{account_id}",
        )
        return OpenDotaProfileResponse.model_validate(response.json())

    async def get_recent_matches(self, account_id: int) -> Sequence[OpenDotaRecentMatch]:
        response = await self._request(f"/players/{account_id}/recentMatches")
        payload = response.json()
        return [OpenDotaRecentMatch.model_validate(item) for item in payload]

    async def get_constants_resource(self, resource: str) -> dict[str, object]:
        response = await self._request(f"/constants/{resource}")
        payload = response.json()
        if not isinstance(payload, dict):
            msg = f"Unexpected constants payload for {resource}"
            raise TypeError(msg)
        return {str(key): value for key, value in payload.items()}

    async def get_player_matches(
        self,
        account_id: int,
        *,
        days: int,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[OpenDotaPlayerMatch]:
        response = await self._request(
            f"/players/{account_id}/matches",
            params={
                **self._request_params(),
                "date": str(days),
                "limit": str(limit),
                "offset": str(offset),
            },
        )
        payload = response.json()
        return [OpenDotaPlayerMatch.model_validate(item) for item in payload]

    async def get_match_players(self, match_id: int) -> Sequence[OpenDotaPlayerMatch]:
        response = await self._request(f"/matches/{match_id}")
        payload = response.json()
        if not isinstance(payload, dict):
            msg = f"Unexpected match payload for match {match_id}"
            raise TypeError(msg)
        players = payload.get("players")
        if not isinstance(players, list):
            msg = f"Unexpected players payload for match {match_id}"
            raise TypeError(msg)
        resolved_match_id = payload.get("match_id")
        if not isinstance(resolved_match_id, int):
            resolved_match_id = match_id
        return [
            OpenDotaPlayerMatch.model_validate(
                {
                    "match_id": resolved_match_id,
                    **item,
                }
            )
            for item in players
            if isinstance(item, dict)
        ]

    def _request_params(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {"api_key": self._api_key}

    async def _request(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        for attempt in range(1, self._max_retries + 1):
            await self._wait_for_rate_limit_window()
            try:
                response = await self._client.get(path, params=params or self._request_params())
                self._schedule_rate_limit_pause(self._rate_limit_delay_seconds(response.headers))
                response.raise_for_status()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                header_delay = 0.0
                if isinstance(exc, httpx.HTTPStatusError):
                    header_delay = self._rate_limit_delay_seconds(exc.response.headers)
                    self._schedule_rate_limit_pause(header_delay)
                if not self._should_retry(exc) or attempt == self._max_retries:
                    raise
                await asyncio.sleep(max(self._backoff_seconds * attempt, header_delay))
        msg = "OpenDota request retry loop exhausted"
        raise RuntimeError(msg)

    @staticmethod
    def _should_retry(exc: httpx.RequestError | httpx.HTTPStatusError) -> bool:
        if isinstance(exc, httpx.RequestError):
            return True
        status_code = exc.response.status_code
        return status_code == 429 or status_code >= 500

    async def _wait_for_rate_limit_window(self) -> None:
        delay = self._next_request_at_monotonic - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)

    def _schedule_rate_limit_pause(self, delay_seconds: float) -> None:
        if delay_seconds <= 0:
            return
        self._next_request_at_monotonic = max(
            self._next_request_at_monotonic,
            time.monotonic() + delay_seconds,
        )

    @classmethod
    def _rate_limit_delay_seconds(cls, headers: httpx.Headers) -> float:
        server_time = cls._parse_server_time(headers)
        if server_time is None:
            return 0.0
        remaining_minute = cls._parse_int_header(headers, "x-rate-limit-remaining-minute")
        remaining_day = cls._parse_int_header(headers, "x-rate-limit-remaining-day")
        delay = 0.0
        if remaining_minute is not None:
            next_minute = server_time.replace(second=0, microsecond=0) + timedelta(minutes=1)
            seconds_to_next_minute = max((next_minute - server_time).total_seconds(), 1.0)
            if remaining_minute <= 0:
                delay = max(delay, seconds_to_next_minute)
            elif remaining_minute < 10:
                delay = max(delay, seconds_to_next_minute / remaining_minute)
        if remaining_day is not None and remaining_day < 100:
            utc_time = server_time.astimezone(UTC)
            next_day = utc_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                days=1
            )
            seconds_to_next_day = max((next_day - utc_time).total_seconds(), 1.0)
            if remaining_day <= 0:
                delay = max(delay, seconds_to_next_day)
            else:
                delay = max(delay, seconds_to_next_day / remaining_day)
        return delay

    @staticmethod
    def _parse_int_header(headers: httpx.Headers, name: str) -> int | None:
        raw_value = headers.get(name)
        if raw_value is None:
            return None
        try:
            return int(raw_value)
        except ValueError:
            return None

    @staticmethod
    def _parse_server_time(headers: httpx.Headers) -> datetime | None:
        raw_value = headers.get("date")
        if raw_value is None:
            return None
        try:
            parsed = parsedate_to_datetime(raw_value)
        except (TypeError, ValueError, IndexError):
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
