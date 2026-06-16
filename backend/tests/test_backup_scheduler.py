import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from portfolio_app.config import Settings
from portfolio_app.services.backup_scheduler import run_periodic_backups, start_backup_task


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        **overrides,
    )


def test_backup_interval_defaults_to_one_hour(tmp_path, monkeypatch):
    monkeypatch.delenv("PORTFOLIO_BACKUP_INTERVAL_SECONDS", raising=False)

    settings = make_settings(tmp_path)

    assert settings.backup_interval_seconds == 3600


@pytest.mark.asyncio
async def test_periodic_backups_wait_before_first_automatic_backup(tmp_path):
    settings = make_settings(tmp_path)
    calls: list[tuple[Settings, Path]] = []
    intervals: list[float] = []

    async def backup_once(*, settings: Settings, db_path: Path) -> None:
        calls.append((settings, db_path))

    async def sleep(seconds: float) -> None:
        intervals.append(seconds)
        if len(intervals) == 2:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_periodic_backups(
            settings=settings,
            db_path=settings.database_path,
            sleep=sleep,
            backup_once=backup_once,
        )

    assert calls == [(settings, settings.database_path)]
    assert intervals == [3600, 3600]


@pytest.mark.asyncio
async def test_periodic_backups_continue_after_failure(tmp_path):
    settings = make_settings(tmp_path)
    call_count = 0
    intervals: list[float] = []

    async def backup_once(*, settings: Settings, db_path: Path) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("backup failed")

    async def sleep(seconds: float) -> None:
        intervals.append(seconds)
        if len(intervals) == 3:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_periodic_backups(
            settings=settings,
            db_path=settings.database_path,
            sleep=sleep,
            backup_once=backup_once,
        )

    assert call_count == 2
    assert intervals == [3600, 3600, 3600]


@pytest.mark.asyncio
async def test_start_backup_task_skips_when_disabled(tmp_path):
    settings = make_settings(tmp_path, backup_enabled=False)
    app = SimpleNamespace(state=SimpleNamespace(settings=settings, db_path=settings.database_path))

    task = start_backup_task(app)

    assert task is None
