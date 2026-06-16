import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from portfolio_app.config import Settings
from portfolio_app.db import connect

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]
SyncOnce = Callable[..., Awaitable[object]]


async def run_market_sync_once(*, settings: Settings, db_path: Path) -> object:
    from portfolio_app.api.market_data import sync_market_data_for_settings

    db = connect(db_path)
    try:
        return await sync_market_data_for_settings(settings, db)
    finally:
        db.close()


async def run_periodic_market_sync(
    *,
    settings: Settings,
    db_path: Path,
    sleep: Sleep = asyncio.sleep,
    sync_once: SyncOnce = run_market_sync_once,
) -> None:
    while True:
        try:
            await sync_once(settings=settings, db_path=db_path)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Automatic market data sync failed")

        await sleep(float(settings.market_sync_interval_seconds))


def start_market_sync_task(app: Any) -> asyncio.Task[None] | None:
    settings = app.state.settings
    if not settings.market_sync_enabled:
        return None

    return asyncio.create_task(
        run_periodic_market_sync(settings=settings, db_path=app.state.db_path),
        name="market-sync",
    )


async def stop_market_sync_task(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
