from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from dota_dog.bootstrap import build_container
from dota_dog.logging import configure_logging
from dota_dog.services.legacy_import import LegacyImportService
from dota_dog.settings import load_settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import legacy old_code/players.json into the new DB."
    )
    parser.add_argument("--path", default="old_code/players.json")
    parser.add_argument("--chat-id", required=True, type=int)
    parser.add_argument("--thread-id", type=int)
    parser.add_argument("--title")
    return parser


async def _run() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    args = _build_parser().parse_args()
    container = build_container(settings)
    try:
        async with container.session_factory() as session:
            imported = await LegacyImportService(session).import_players_json(
                path=Path(args.path),
                telegram_chat_id=args.chat_id,
                telegram_thread_id=args.thread_id,
                title=args.title,
                timezone=settings.default_timezone,
            )
        print(f"Imported {imported} players.")
    finally:
        await container.aclose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
