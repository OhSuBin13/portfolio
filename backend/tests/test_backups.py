import importlib
import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.services.backups import (
    create_backup,
    create_recorded_backup,
    list_backup_records,
    prune_backups,
    reconcile_backup_records,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def create_test_app(tmp_path, **overrides: object):
    from portfolio_app.main import create_app

    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        **overrides,
    )
    return create_app(settings=settings), settings


def list_backups_via_route(settings: Settings) -> list[dict[str, object]]:
    from portfolio_app.api.backups import list_backups

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    db = connect(settings.database_path)
    try:
        return list_backups(request, db)
    finally:
        db.close()


def test_create_backup_copies_sqlite_file(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    backup_dir = tmp_path / "backups"
    db = connect(db_path)
    migrate(db)
    db.close()

    backup_path = create_backup(db_path=db_path, backup_dir=backup_dir, reason="manual")

    assert backup_path.exists()
    assert backup_path.name.endswith(".sqlite")


def test_create_backup_rejects_unknown_reason(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    backup_dir = tmp_path / "backups"
    db = connect(db_path)
    migrate(db)
    db.close()

    with pytest.raises(ValueError, match="지원하지 않는 백업 사유입니다"):
        create_backup(db_path=db_path, backup_dir=backup_dir, reason="test")


def test_create_backup_uses_consistent_sqlite_snapshot_with_open_wal_connection(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    backup_dir = tmp_path / "backups"
    db = connect(db_path)
    db.execute("pragma journal_mode = wal")
    db.execute("pragma wal_autocheckpoint = 0")
    migrate(db)
    db.execute(
        """
        insert into backups(path, reason, created_at)
        values (?, ?, ?)
        """,
        ("source-row.sqlite", "test", "2026-06-12T00:00:00"),
    )
    db.commit()

    backup_path = create_backup(db_path=db_path, backup_dir=backup_dir, reason="manual")

    backup = sqlite3.connect(backup_path)
    row = backup.execute("select path, reason from backups").fetchone()
    backup.close()
    db.close()

    assert row == ("source-row.sqlite", "test")


def test_prune_backups_keeps_newest_files(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for index in range(35):
        path = backup_dir / f"portfolio-20260612-120000-{index + 1:06d}-manual.sqlite"
        path.write_text(str(index), encoding="utf-8")

    prune_backups(backup_dir=backup_dir, keep=30)

    assert len(list(backup_dir.glob("*.sqlite"))) == 30
    assert (backup_dir / "portfolio-20260612-120000-000035-manual.sqlite").exists()


def test_prune_backups_only_deletes_service_owned_files(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    unrelated = backup_dir / "unrelated.sqlite"
    unrelated.write_text("do not delete", encoding="utf-8")
    os.utime(unrelated, (1, 1))

    for index in range(2):
        path = backup_dir / f"portfolio-20260612-120000-{index + 1:06d}-manual.sqlite"
        path.write_text(str(index), encoding="utf-8")

    prune_backups(backup_dir=backup_dir, keep=1)

    assert unrelated.exists()
    assert len(list(backup_dir.glob("portfolio-*.sqlite"))) == 1


def test_prune_backups_ignores_portfolio_prefixed_non_backup_files(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    unrelated = backup_dir / "portfolio-not-a-backup.sqlite"
    unrelated.write_text("do not delete", encoding="utf-8")
    os.utime(unrelated, (1, 1))

    for index in range(2):
        path = backup_dir / f"portfolio-20260612-120000-{index + 1:06d}-manual.sqlite"
        path.write_text(str(index), encoding="utf-8")

    prune_backups(backup_dir=backup_dir, keep=1)

    assert unrelated.exists()
    assert len(list(backup_dir.glob("portfolio-*.sqlite"))) == 2


def test_prune_backups_ignores_backup_like_file_with_invalid_timestamp(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    invalid = backup_dir / "portfolio-20269999-999999-000000-manual.sqlite"
    invalid.write_text("do not delete", encoding="utf-8")
    os.utime(invalid, (1, 1))

    for index in range(2):
        path = backup_dir / f"portfolio-20260612-120000-{index + 1:06d}-manual.sqlite"
        path.write_text(str(index), encoding="utf-8")

    prune_backups(backup_dir=backup_dir, keep=1)

    assert invalid.exists()
    assert len(list(backup_dir.glob("portfolio-*.sqlite"))) == 2


def test_create_app_creates_startup_backup_after_migration(tmp_path):
    from portfolio_app.main import create_app

    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )

    create_app(settings=settings)

    backups = list(settings.backup_dir.glob("*.sqlite"))
    assert len(backups) == 1
    assert backups[0].name.endswith("-startup.sqlite")


def test_create_app_records_startup_backup_metadata(tmp_path):
    _, settings = create_test_app(tmp_path)
    db = connect(settings.database_path)
    try:
        backups = [dict(row) for row in list_backup_records(db, backup_dir=settings.backup_dir)]
    finally:
        db.close()

    startup_backups = [backup for backup in backups if backup["reason"] == "startup"]
    assert len(startup_backups) == 1
    assert Path(startup_backups[0]["path"]).exists()


def test_backup_api_is_read_only_in_openapi(tmp_path):
    app, _settings = create_test_app(tmp_path)

    backup_methods = app.openapi()["paths"]["/api/backups"]

    assert set(backup_methods) == {"get"}


def test_backup_api_uses_typed_response_schema(tmp_path):
    app, _settings = create_test_app(tmp_path)

    get_schema = app.openapi()["paths"]["/api/backups"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    backup_record_schema = app.openapi()["components"]["schemas"]["BackupRecord"]

    assert get_schema == {
        "items": {"$ref": "#/components/schemas/BackupRecord"},
        "type": "array",
        "title": "Response List Backups Api Backups Get",
    }
    assert backup_record_schema["properties"]["reason"]["enum"] == [
        "startup",
        "automatic",
        "manual",
    ]


def test_backup_status_api_returns_runtime_settings(tmp_path):
    app, _settings = create_test_app(
        tmp_path,
        backup_enabled=False,
        backup_interval_seconds=7200,
    )

    response = TestClient(app, raise_server_exceptions=False).get("/api/backups/status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "interval_seconds": 7200,
    }


def test_backup_api_lists_service_created_backup(tmp_path):
    _app, settings = create_test_app(tmp_path)
    db = connect(settings.database_path)
    try:
        created = dict(
            create_recorded_backup(
                db,
                db_path=settings.database_path,
                backup_dir=settings.backup_dir,
                reason="automatic",
            )
        )
    finally:
        db.close()

    backups = list_backups_via_route(settings)

    assert backups[0]["path"] == created["path"]
    assert backups[0]["reason"] == "automatic"
    assert backups[0]["created_at"]


def test_backup_api_hides_stale_metadata_for_missing_files(tmp_path):
    _app, settings = create_test_app(tmp_path)
    db = connect(settings.database_path)
    db.execute(
        """
        insert into backups(path, reason, created_at)
        values (?, ?, ?)
        """,
        (str(tmp_path / "backups" / "missing.sqlite"), "manual", "2026-06-12T00:00:00"),
    )
    db.commit()
    db.close()

    backups = list_backups_via_route(settings)

    assert all(backup["path"].endswith("missing.sqlite") is False for backup in backups)


def test_create_recorded_backup_prunes_files_and_metadata_together(tmp_path):
    _app, settings = create_test_app(tmp_path)
    for _ in range(35):
        db = connect(settings.database_path)
        try:
            create_recorded_backup(
                db,
                db_path=settings.database_path,
                backup_dir=settings.backup_dir,
                reason="automatic",
            )
        finally:
            db.close()

    backups = list_backups_via_route(settings)

    assert len(backups) == 30
    assert all(Path(backup["path"]).exists() for backup in backups)


def test_backup_api_backfills_orphan_service_owned_files_only(tmp_path):
    _app, settings = create_test_app(tmp_path)
    orphan_path = create_backup(
        db_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        reason="manual",
    )
    ignored_path = tmp_path / "backups" / "portfolio-not-a-backup.sqlite"
    ignored_path.write_text("not a backup", encoding="utf-8")

    backups = list_backups_via_route(settings)

    paths = {backup["path"] for backup in backups}
    assert str(orphan_path) in paths
    assert str(ignored_path) not in paths


def test_backup_api_ignores_backup_like_file_with_invalid_timestamp(tmp_path):
    _app, settings = create_test_app(tmp_path)
    invalid_path = tmp_path / "backups" / "portfolio-20269999-999999-000000-manual.sqlite"
    invalid_path.write_text("not a backup", encoding="utf-8")

    backups = list_backups_via_route(settings)

    paths = {backup["path"] for backup in backups}
    assert str(invalid_path) not in paths


def test_backup_api_ignores_unknown_reason_file_over_http(tmp_path):
    app, settings = create_test_app(tmp_path, backup_enabled=False)
    unknown_reason_path = (
        settings.backup_dir / "portfolio-20260612-120000-000000-test.sqlite"
    )
    unknown_reason_path.write_text("not a service backup", encoding="utf-8")

    response = TestClient(app, raise_server_exceptions=False).get("/api/backups")

    assert response.status_code == 200
    paths = {backup["path"] for backup in response.json()}
    assert str(unknown_reason_path) not in paths


def test_list_backup_records_does_not_reconcile_filesystem_metadata(tmp_path):
    _app, settings = create_test_app(tmp_path)
    orphan_path = create_backup(
        db_path=settings.database_path,
        backup_dir=settings.backup_dir,
        reason="manual",
    )
    missing_path = settings.backup_dir / "missing.sqlite"
    db = connect(settings.database_path)
    try:
        db.execute(
            """
            insert into backups(path, reason, created_at)
            values (?, ?, ?)
            """,
            (str(missing_path), "manual", "2026-06-12T00:00:00"),
        )
        db.commit()

        rows = [dict(row) for row in list_backup_records(db, backup_dir=settings.backup_dir)]
    finally:
        db.close()

    paths = {row["path"] for row in rows}
    assert str(missing_path) in paths
    assert str(orphan_path) not in paths


def test_reconcile_backup_records_hides_stale_metadata_and_backfills_orphans(tmp_path):
    _app, settings = create_test_app(tmp_path)
    orphan_path = create_backup(
        db_path=settings.database_path,
        backup_dir=settings.backup_dir,
        reason="manual",
    )
    missing_path = settings.backup_dir / "missing.sqlite"
    db = connect(settings.database_path)
    try:
        db.execute(
            """
            insert into backups(path, reason, created_at)
            values (?, ?, ?)
            """,
            (str(missing_path), "manual", "2026-06-12T00:00:00"),
        )
        db.commit()

        reconcile_backup_records(db, backup_dir=settings.backup_dir)
        rows = [dict(row) for row in list_backup_records(db, backup_dir=settings.backup_dir)]
    finally:
        db.close()

    paths = {row["path"] for row in rows}
    assert str(missing_path) not in paths
    assert str(orphan_path) in paths


def test_reconcile_backup_records_deletes_unknown_reason_metadata(tmp_path):
    _app, settings = create_test_app(tmp_path)
    legacy_path = settings.backup_dir / "legacy.sqlite"
    legacy_path.write_text("legacy", encoding="utf-8")
    db = connect(settings.database_path)
    try:
        db.execute(
            """
            insert into backups(path, reason, created_at)
            values (?, ?, ?)
            """,
            (str(legacy_path), "legacy", "2026-06-12T00:00:00"),
        )
        db.commit()

        reconcile_backup_records(db, backup_dir=settings.backup_dir)
        rows = [dict(row) for row in list_backup_records(db, backup_dir=settings.backup_dir)]
    finally:
        db.close()

    paths = {row["path"] for row in rows}
    assert str(legacy_path) not in paths


def test_create_app_throttles_recent_startup_backup(tmp_path):
    from portfolio_app.main import create_app

    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )

    create_app(settings=settings)
    create_app(settings=settings)

    assert len(list(settings.backup_dir.glob("*-startup.sqlite"))) == 1


def test_readme_runtime_command_uses_importable_asgi_app(tmp_path, monkeypatch):
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "portfolio_app.asgi:app" in readme
    assert "portfolio_app.main:app" not in readme

    monkeypatch.chdir(tmp_path)
    sys.modules.pop("portfolio_app.asgi", None)
    sys.modules.pop("portfolio_app.main", None)

    module = importlib.import_module("portfolio_app.asgi")

    assert any(route.path == "/health" for route in module.app.routes)


def test_backend_dev_dependencies_do_not_install_httpx2():
    pyproject = (REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")

    assert "httpx2" not in pyproject


def test_importing_main_does_not_create_default_backup_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("portfolio_app.main", None)

    module = importlib.import_module("portfolio_app.main")

    assert hasattr(module, "create_app")
    assert not (tmp_path / "data" / "backups").exists()
