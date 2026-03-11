from __future__ import annotations

import asyncio
from collections.abc import Sequence

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

    def _request_params(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {"api_key": self._api_key}

    async def _request(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.get(path, params=params or self._request_params())
                response.raise_for_status()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                if not self._should_retry(exc) or attempt == self._max_retries:
                    raise
                await asyncio.sleep(self._backoff_seconds * attempt)
        msg = "OpenDota request retry loop exhausted"
        raise RuntimeError(msg)

    @staticmethod
    def _should_retry(exc: httpx.RequestError | httpx.HTTPStatusError) -> bool:
        if isinstance(exc, httpx.RequestError):
            return True
        status_code = exc.response.status_code
        return status_code == 429 or status_code >= 500
