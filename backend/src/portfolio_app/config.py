from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_dir: Path = Path("data")
    database_path: Path = Path("data/portfolio.sqlite")
    backup_dir: Path = Path("data/backups")
    alpha_vantage_api_key: str = ""
    market_sync_enabled: bool = True
    market_sync_interval_seconds: int = Field(default=300, gt=0)
    toss_api_key: str = ""
    toss_secret_key: str = ""
    backup_enabled: bool = True
    backup_interval_seconds: int = Field(default=3600, gt=0)

    model_config = SettingsConfigDict(env_prefix="PORTFOLIO_", env_file=".env")


def get_settings() -> Settings:
    return Settings()
