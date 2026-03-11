from __future__ import annotations

from typing import Protocol


class AdminLookupBot(Protocol):
    async def get_chat_administrators(self, chat_id: int): ...


class PermissionService:
    def __init__(
        self,
        *,
        allowed_user_ids: set[int],
        telegram_admin_check_enabled: bool,
    ) -> None:
        self._allowed_user_ids = allowed_user_ids
        self._telegram_admin_check_enabled = telegram_admin_check_enabled

    async def can_manage_topic(
        self,
        *,
        bot: AdminLookupBot,
        chat_id: int,
        user_id: int | None,
    ) -> bool:
        if user_id is None:
            return False
        if user_id in self._allowed_user_ids:
            return True
        if not self._telegram_admin_check_enabled:
            return True
        administrators = await bot.get_chat_administrators(chat_id)
        return any(admin.user.id == user_id for admin in administrators)
