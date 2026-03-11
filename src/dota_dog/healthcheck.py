from __future__ import annotations

import asyncio

from dota_dog.bootstrap import build_container
from dota_dog.infra.db.runtime import check_database_connection
from dota_dog.settings import load_settings


async def _run() -> None:
    settings = load_settings()
    container = build_container(settings)
    try:
        await check_database_connection(container.engine)
    finally:
        await container.aclose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
