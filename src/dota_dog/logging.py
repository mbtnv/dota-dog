from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable

import structlog

_TELEGRAM_BOT_TOKEN_PATTERN = re.compile(r"\d{6,}:[A-Za-z0-9_-]{20,}\b")


def redact_sensitive_text(text: str, *, secrets: Iterable[str] = ()) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return _TELEGRAM_BOT_TOKEN_PATTERN.sub("<redacted>", redacted)


class RedactingFormatter(logging.Formatter):
    def __init__(self, fmt: str, *, secrets: Iterable[str] = ()) -> None:
        super().__init__(fmt)
        self._secrets = tuple(secret for secret in secrets if secret)

    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive_text(super().format(record), secrets=self._secrets)


def configure_logging(level: str, *, secrets: Iterable[str] = ()) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingFormatter("%(message)s", secrets=secrets))
    logging.basicConfig(
        level=numeric_level,
        handlers=[handler],
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=True,
    )
