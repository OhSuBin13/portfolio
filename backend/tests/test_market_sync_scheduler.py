import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from portfolio_app.config import Settings
from portfolio_app.services.market_sync_scheduler import (
    run_periodic_market_sync,
    start_market_sync_task,
)


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        **overrides,
    )


def test_market_sync_scheduler_imports_service_not_api():
    backend_dir = Path(__file__).parents[1]
    source = (backend_dir / "src/portfolio_app/services/market_sync_scheduler.py").read_text()

    assert "portfolio_app.api.market_data" not in source
    assert "portfolio_app.services.market_data" in source


def test_market_sync_interval_defaults_to_five_minutes(tmp_path, monkeypatch):
    monkeypatch.delenv("PORTFOLIO_MARKET_SYNC_INTERVAL_SECONDS", raising=False)

    settings = make_settings(tmp_path)

    assert settings.market_sync_interval_seconds == 300


@pytest.mark.asyncio
async def test_periodic_market_sync_runs_immediately_then_waits_for_interval(tmp_path):
    settings = make_settings(tmp_path)
    calls: list[tuple[Settings, Path]] = []
    intervals: list[float] = []

    async def sync_once(*, settings: Settings, db_path: Path) -> None:
        calls.append((settings, db_path))

    async def sleep(seconds: float) -> None:
        intervals.append(seconds)
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_periodic_market_sync(
            settings=settings,
            db_path=settings.database_path,
            sleep=sleep,
            sync_once=sync_once,
        )

    assert calls == [(settings, settings.database_path)]
    assert intervals == [300]


@pytest.mark.asyncio
async def test_periodic_market_sync_continues_after_sync_failure(tmp_path):
    settings = make_settings(tmp_path)
    call_count = 0
    intervals: list[float] = []

    async def sync_once(*, settings: Settings, db_path: Path) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("provider failed")

    async def sleep(seconds: float) -> None:
        intervals.append(seconds)
        if len(intervals) == 2:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_periodic_market_sync(
            settings=settings,
            db_path=settings.database_path,
            sleep=sleep,
            sync_once=sync_once,
        )

    assert call_count == 2
    assert intervals == [300, 300]


@pytest.mark.asyncio
async def test_start_market_sync_task_skips_when_disabled(tmp_path):
    settings = make_settings(tmp_path, market_sync_enabled=False)
    app = SimpleNamespace(state=SimpleNamespace(settings=settings, db_path=settings.database_path))

    task = start_market_sync_task(app)

    assert task is None
