from __future__ import annotations

from dota_dog.bot.handlers.common import _parse_account_id


def test_parse_account_id_from_plain_number() -> None:
    assert _parse_account_id("123456") == 123456


def test_parse_account_id_from_profile_url() -> None:
    assert _parse_account_id("https://www.dotabuff.com/players/123456") == 123456
