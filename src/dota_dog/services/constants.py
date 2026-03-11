from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from dota_dog.domain.enums import ConstantResource
from dota_dog.domain.models import ConstantEntry, ConstantSnapshot
from dota_dog.infra.db.repositories.core import ConstantRepository


class ConstantsClient(Protocol):
    async def get_constants_resource(self, resource: str) -> dict[str, object]: ...


class ConstantsService:
    def __init__(self, *, sync_interval_hours: int = 24) -> None:
        self._sync_interval = timedelta(hours=sync_interval_hours)

    async def sync_if_stale(self, session: AsyncSession, client: ConstantsClient) -> None:
        repository = ConstantRepository(session)
        for resource in ConstantResource:
            last_updated_at = await repository.get_last_updated_at(resource)
            if last_updated_at is not None and self._is_fresh(last_updated_at):
                continue
            payload = await client.get_constants_resource(resource.value)
            entries = self._parse_resource(resource, payload)
            await repository.upsert_entries(entries)
        await session.flush()

    async def get_snapshot(self, session: AsyncSession) -> ConstantSnapshot:
        return await ConstantRepository(session).get_snapshot()

    def _is_fresh(self, last_updated_at: datetime) -> bool:
        normalized = last_updated_at
        if normalized.tzinfo is None:
            normalized = normalized.replace(tzinfo=UTC)
        else:
            normalized = normalized.astimezone(UTC)
        return datetime.now(UTC) - normalized < self._sync_interval

    def _parse_resource(
        self,
        resource: ConstantResource,
        payload: dict[str, object],
    ) -> list[ConstantEntry]:
        entries: list[ConstantEntry] = []
        for raw_code, raw_value in payload.items():
            if not raw_code.isdigit() or not isinstance(raw_value, dict):
                continue
            code = int(raw_code)
            normalized_payload = {str(key): value for key, value in raw_value.items()}
            name = self._extract_name(resource, normalized_payload)
            entries.append(
                ConstantEntry(
                    resource=resource,
                    code=code,
                    name=name,
                    raw_payload=normalized_payload,
                )
            )
        return entries

    def _extract_name(self, resource: ConstantResource, payload: dict[str, object]) -> str:
        if resource == ConstantResource.HEROES:
            localized = payload.get("localized_name")
            if isinstance(localized, str) and localized:
                return localized
        for candidate_key in ("name", "localized_name"):
            candidate = payload.get(candidate_key)
            if isinstance(candidate, str) and candidate:
                return self._humanize_name(candidate)
        return "Unknown"

    @staticmethod
    def _humanize_name(value: str) -> str:
        prefixes = ("game_mode_", "lobby_type_")
        cleaned = value
        for prefix in prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned.removeprefix(prefix)
                break
        cleaned = cleaned.replace("_", " ").strip()
        return cleaned.title() if cleaned else value
