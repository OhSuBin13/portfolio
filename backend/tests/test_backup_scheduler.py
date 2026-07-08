import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.services.backup_scheduler import (
    run_backup_once,
    run_periodic_backups,
    start_backup_task,
    stop_backup_task,
)


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
async def test_run_backup_once_creates_recorded_automatic_backup(tmp_path):
    settings = make_settings(tmp_path)
    db = connect(settings.database_path)
    try:
        migrate(db)
    finally:
        db.close()

    row = await run_backup_once(settings=settings, db_path=settings.database_path)

    assert row["reason"] == "automatic"
    assert Path(row["path"]).exists()
    assert Path(row["path"]).parent == settings.backup_dir


@pytest.mark.asyncio
async def test_run_backup_once_does_not_create_missing_database(tmp_path):
    settings = make_settings(tmp_path)

    with pytest.raises(FileNotFoundError, match="데이터베이스 파일"):
        await run_backup_once(settings=settings, db_path=settings.database_path)

    assert not settings.database_path.exists()
    assert not settings.backup_dir.exists()


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


@pytest.mark.asyncio
async def test_start_backup_task_creates_named_task_until_stopped(tmp_path):
    settings = make_settings(tmp_path)
    app = SimpleNamespace(state=SimpleNamespace(settings=settings, db_path=settings.database_path))

    task = start_backup_task(app)
    try:
        assert task is not None
        assert task.get_name() == "automatic-backup"
        assert not task.done()
    finally:
        await stop_backup_task(task)

    assert task.done()
