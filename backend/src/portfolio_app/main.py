from fastapi import FastAPI

from portfolio_app.api import accounts, assets, goals, summary, transactions
from portfolio_app.config import Settings, get_settings
from portfolio_app.db import connect
from portfolio_app.migrations import migrate


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app_settings.data_dir.mkdir(parents=True, exist_ok=True)
    app_settings.backup_dir.mkdir(parents=True, exist_ok=True)

    db = connect(app_settings.database_path)
    migrate(db)
    db.close()

    app = FastAPI(title="Personal Finance Portfolio", version="0.1.0")
    app.state.settings = app_settings
    app.state.db_path = app_settings.database_path

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(summary.router)
    app.include_router(accounts.router)
    app.include_router(assets.router)
    app.include_router(transactions.router)
    app.include_router(goals.router)

    return app


app = create_app()
