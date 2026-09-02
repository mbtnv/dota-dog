from __future__ import annotations

import logging
import sys

from dota_dog.logging import RedactingFormatter, redact_sensitive_text


def test_redact_sensitive_text_masks_telegram_token_and_explicit_secret() -> None:
    token = "5486341211:abcdefghijklmnopqrstuvwxyz123456789"
    proxy_password = "proxy-secret"
    text = f"https://api.telegram.org/bot{token}/getMe password={proxy_password}"

    redacted = redact_sensitive_text(text, secrets=(proxy_password,))

    assert token not in redacted
    assert proxy_password not in redacted
    assert redacted.count("<redacted>") == 2


def test_redacting_formatter_masks_token_in_traceback() -> None:
    token = "5486341211:abcdefghijklmnopqrstuvwxyz123456789"
    try:
        msg = f"Connection timeout to https://api.telegram.org/bot{token}/getMe"
        raise RuntimeError(msg)
    except RuntimeError:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="Telegram request failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    rendered = RedactingFormatter("%(message)s").format(record)

    assert token not in rendered
    assert "<redacted>" in rendered
    assert "RuntimeError" in rendered
