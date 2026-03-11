from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from dota_dog.infra.db.session import create_engine, create_session_factory
from dota_dog.infra.opendota.client import OpenDotaClient
from dota_dog.services.backfill import BackfillService
from dota_dog.services.constants import ConstantsService
from dota_dog.services.formatter import MessageFormatter
from dota_dog.services.permissions import PermissionService
from dota_dog.services.reporting import ReportingService
from dota_dog.services.tracking import TrackingService
from dota_dog.settings import Settings


@dataclass(slots=True)
class AppContainer:
    engine: AsyncEngine
    session_factory: async_sessionmaker
    opendota_client: OpenDotaClient
    formatter: MessageFormatter
    constants_service: ConstantsService
    backfill_service: BackfillService
    tracking_service: TrackingService
    reporting_service: ReportingService
    permission_service: PermissionService

    async def aclose(self) -> None:
        await self.opendota_client.aclose()
        await self.engine.dispose()


def build_container(settings: Settings) -> AppContainer:
    engine = create_engine(settings.database_url)
    tracking_service = TrackingService()
    return AppContainer(
        engine=engine,
        session_factory=create_session_factory(engine),
        opendota_client=OpenDotaClient(
            base_url=settings.opendota_base_url,
            api_key=settings.opendota_api_key,
            max_retries=settings.opendota_max_retries,
            backoff_seconds=settings.retry_backoff_seconds,
        ),
        formatter=MessageFormatter(),
        constants_service=ConstantsService(
            sync_interval_hours=settings.constants_sync_interval_hours
        ),
        tracking_service=tracking_service,
        backfill_service=BackfillService(tracking_service),
        reporting_service=ReportingService(),
        permission_service=PermissionService(
            allowed_user_ids=settings.allowed_user_ids,
            telegram_admin_check_enabled=settings.telegram_admin_check_enabled,
        ),
    )
