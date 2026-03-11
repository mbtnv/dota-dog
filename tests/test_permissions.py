from __future__ import annotations

from types import SimpleNamespace

import pytest

from dota_dog.services.permissions import PermissionService


class FakeBot:
    def __init__(self, admin_ids: list[int]) -> None:
        self._admin_ids = admin_ids

    async def get_chat_administrators(self, chat_id: int) -> list[SimpleNamespace]:
        return [SimpleNamespace(user=SimpleNamespace(id=admin_id)) for admin_id in self._admin_ids]


@pytest.mark.asyncio
async def test_permission_service_allows_allowlisted_user() -> None:
    service = PermissionService(
        allowed_user_ids={10},
        telegram_admin_check_enabled=True,
    )

    allowed = await service.can_manage_topic(bot=FakeBot([]), chat_id=1, user_id=10)

    assert allowed is True


@pytest.mark.asyncio
async def test_permission_service_checks_chat_admins() -> None:
    service = PermissionService(
        allowed_user_ids=set(),
        telegram_admin_check_enabled=True,
    )

    allowed = await service.can_manage_topic(bot=FakeBot([20]), chat_id=1, user_id=20)
    denied = await service.can_manage_topic(bot=FakeBot([20]), chat_id=1, user_id=30)

    assert allowed is True
    assert denied is False
