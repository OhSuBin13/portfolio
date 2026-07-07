from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_dir: Path = Path("data")
    database_path: Path = Path("data/portfolio.sqlite")
    backup_dir: Path = Path("data/backups")
    toss_api_key: str = ""
    toss_secret_key: str = ""
    backup_enabled: bool = True
    backup_interval_seconds: int = Field(default=3600, gt=0)

    model_config = SettingsConfigDict(env_prefix="PORTFOLIO_", env_file=".env", extra="ignore")


def get_settings() -> Settings:
    return Settings()
