import importlib
import os
import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.services.backups import create_backup, prune_backups

REPO_ROOT = Path(__file__).resolve().parents[2]


def create_test_client(tmp_path):
    from portfolio_app.main import create_app

    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )
    return TestClient(create_app(settings=settings))


def test_create_backup_copies_sqlite_file(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    backup_dir = tmp_path / "backups"
    db = connect(db_path)
    migrate(db)
    db.close()

    backup_path = create_backup(db_path=db_path, backup_dir=backup_dir, reason="test")

    assert backup_path.exists()
    assert backup_path.name.endswith(".sqlite")


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

    backup_path = create_backup(db_path=db_path, backup_dir=backup_dir, reason="test")

    backup = sqlite3.connect(backup_path)
    row = backup.execute("select path, reason from backups").fetchone()
    backup.close()
    db.close()

    assert row == ("source-row.sqlite", "test")


def test_prune_backups_keeps_newest_files(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for index in range(35):
        path = backup_dir / f"portfolio-20260612-120000-{index + 1:06d}-test.sqlite"
        path.write_text(str(index), encoding="utf-8")

    prune_backups(backup_dir=backup_dir, keep=30)

    assert len(list(backup_dir.glob("*.sqlite"))) == 30
    assert (backup_dir / "portfolio-20260612-120000-000035-test.sqlite").exists()


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
    client = create_test_client(tmp_path)

    response = client.get("/api/backups")

    assert response.status_code == 200
    backups = response.json()
    startup_backups = [backup for backup in backups if backup["reason"] == "startup"]
    assert len(startup_backups) == 1
    assert Path(startup_backups[0]["path"]).exists()


def test_backup_api_creates_and_lists_manual_backup(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post("/api/backups")

    assert response.status_code == 201
    created = response.json()
    assert created["reason"] == "manual"
    assert created["path"].endswith(".sqlite")

    response = client.get("/api/backups")

    assert response.status_code == 200
    backups = response.json()
    assert backups[0]["path"] == created["path"]
    assert backups[0]["reason"] == "manual"
    assert backups[0]["created_at"]


def test_backup_api_hides_stale_metadata_for_missing_files(tmp_path):
    client = create_test_client(tmp_path)
    db = connect(tmp_path / "portfolio.sqlite")
    db.execute(
        """
        insert into backups(path, reason, created_at)
        values (?, ?, ?)
        """,
        (str(tmp_path / "backups" / "missing.sqlite"), "manual", "2026-06-12T00:00:00"),
    )
    db.commit()
    db.close()

    response = client.get("/api/backups")

    assert response.status_code == 200
    assert all(backup["path"].endswith("missing.sqlite") is False for backup in response.json())


def test_backup_api_prunes_files_and_metadata_together(tmp_path):
    client = create_test_client(tmp_path)
    for _ in range(35):
        response = client.post("/api/backups")
        assert response.status_code == 201

    response = client.get("/api/backups")

    assert response.status_code == 200
    backups = response.json()
    assert len(backups) == 30
    assert all(Path(backup["path"]).exists() for backup in backups)


def test_backup_api_backfills_orphan_service_owned_files_only(tmp_path):
    client = create_test_client(tmp_path)
    orphan_path = create_backup(
        db_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        reason="manual",
    )
    ignored_path = tmp_path / "backups" / "portfolio-not-a-backup.sqlite"
    ignored_path.write_text("not a backup", encoding="utf-8")

    response = client.get("/api/backups")

    assert response.status_code == 200
    paths = {backup["path"] for backup in response.json()}
    assert str(orphan_path) in paths
    assert str(ignored_path) not in paths


def test_readme_runtime_command_uses_importable_asgi_app(tmp_path, monkeypatch):
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "portfolio_app.asgi:app" in readme
    assert "portfolio_app.main:app" not in readme

    monkeypatch.chdir(tmp_path)
    sys.modules.pop("portfolio_app.asgi", None)
    sys.modules.pop("portfolio_app.main", None)

    module = importlib.import_module("portfolio_app.asgi")
    response = TestClient(module.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_importing_main_does_not_create_default_backup_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("portfolio_app.main", None)

    module = importlib.import_module("portfolio_app.main")

    assert hasattr(module, "create_app")
    assert not (tmp_path / "data" / "backups").exists()
