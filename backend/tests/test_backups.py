from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.main import create_app
from portfolio_app.migrations import migrate
from portfolio_app.services.backups import create_backup, prune_backups


def test_create_backup_copies_sqlite_file(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    backup_dir = tmp_path / "backups"
    db = connect(db_path)
    migrate(db)
    db.close()

    backup_path = create_backup(db_path=db_path, backup_dir=backup_dir, reason="test")

    assert backup_path.exists()
    assert backup_path.name.endswith(".sqlite")


def test_prune_backups_keeps_newest_files(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for index in range(35):
        path = backup_dir / f"portfolio-2026-06-{index + 1:02d}-test.sqlite"
        path.write_text(str(index), encoding="utf-8")

    prune_backups(backup_dir=backup_dir, keep=30)

    assert len(list(backup_dir.glob("*.sqlite"))) == 30
    assert (backup_dir / "portfolio-2026-06-35-test.sqlite").exists()


def test_create_app_creates_startup_backup_after_migration(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )

    create_app(settings=settings)

    backups = list(settings.backup_dir.glob("*.sqlite"))
    assert len(backups) == 1
    assert backups[0].name.endswith("-startup.sqlite")


def test_backup_api_creates_and_lists_manual_backup(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )
    client = TestClient(create_app(settings=settings))

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
