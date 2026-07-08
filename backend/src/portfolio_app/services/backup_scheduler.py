import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.services.backups import create_recorded_backup

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]
BackupOnce = Callable[..., Awaitable[object]]


async def run_backup_once(*, settings: Settings, db_path: Path) -> object:
    if not db_path.exists():
        raise FileNotFoundError("데이터베이스 파일을 찾을 수 없습니다.")

    db = connect(db_path)
    try:
        return create_recorded_backup(
            db,
            db_path=db_path,
            backup_dir=settings.backup_dir,
            reason="automatic",
        )
    finally:
        db.close()


async def run_periodic_backups(
    *,
    settings: Settings,
    db_path: Path,
    sleep: Sleep = asyncio.sleep,
    backup_once: BackupOnce = run_backup_once,
) -> None:
    while True:
        await sleep(float(settings.backup_interval_seconds))
        try:
            await backup_once(settings=settings, db_path=db_path)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Automatic backup failed")


def start_backup_task(app: Any) -> asyncio.Task[None] | None:
    settings = app.state.settings
    if not settings.backup_enabled:
        return None

    return asyncio.create_task(
        run_periodic_backups(settings=settings, db_path=app.state.db_path),
        name="automatic-backup",
    )


async def stop_backup_task(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
