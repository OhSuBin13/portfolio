from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_dir: Path = Path("data")
    database_path: Path = Path("data/portfolio.sqlite")
    backup_dir: Path = Path("data/backups")
    alpha_vantage_api_key: str = ""

    model_config = SettingsConfigDict(env_prefix="PORTFOLIO_", env_file=".env")


def get_settings() -> Settings:
    return Settings()
