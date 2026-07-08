from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
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

    @model_validator(mode="after")
    def derive_storage_paths_from_data_dir(self) -> Self:
        if "database_path" not in self.model_fields_set:
            self.database_path = self.data_dir / "portfolio.sqlite"
        if "backup_dir" not in self.model_fields_set:
            self.backup_dir = self.data_dir / "backups"
        return self


def get_settings() -> Settings:
    return Settings()
