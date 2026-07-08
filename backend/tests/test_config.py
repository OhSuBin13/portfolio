from portfolio_app.config import Settings


def test_settings_derive_storage_paths_from_custom_data_dir(tmp_path, monkeypatch):
    custom_data_dir = tmp_path / "custom-data"
    monkeypatch.delenv("PORTFOLIO_DATABASE_PATH", raising=False)
    monkeypatch.delenv("PORTFOLIO_BACKUP_DIR", raising=False)

    settings = Settings(data_dir=custom_data_dir, toss_api_key="", toss_secret_key="")

    assert settings.database_path == custom_data_dir / "portfolio.sqlite"
    assert settings.backup_dir == custom_data_dir / "backups"


def test_settings_preserve_explicit_storage_paths(tmp_path):
    custom_data_dir = tmp_path / "custom-data"
    database_path = tmp_path / "db" / "portfolio.sqlite"
    backup_dir = tmp_path / "backup-files"

    settings = Settings(
        data_dir=custom_data_dir,
        database_path=database_path,
        backup_dir=backup_dir,
        toss_api_key="",
        toss_secret_key="",
    )

    assert settings.database_path == database_path
    assert settings.backup_dir == backup_dir
