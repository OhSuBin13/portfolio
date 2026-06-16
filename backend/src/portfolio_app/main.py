from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from portfolio_app.api import (
    accounts,
    assets,
    backups,
    goals,
    market_data,
    summary,
    transactions,
)
from portfolio_app.config import Settings, get_settings
from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.services.backups import create_recorded_backup
from portfolio_app.services.market_sync_scheduler import (
    start_market_sync_task,
    stop_market_sync_task,
)

LOCAL_FRONTEND_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]


def _validation_error_message(error: dict[str, object]) -> str:
    location = error.get("loc", ())
    field = str(location[-1]) if isinstance(location, tuple | list) and location else "요청"
    error_type = str(error.get("type", ""))

    if error_type == "missing":
        return f"{field}: 필수 입력값이 누락되었습니다."
    if error_type == "extra_forbidden":
        return f"{field}: 허용되지 않는 입력값입니다."
    if "parsing" in error_type or "type" in error_type:
        return f"{field}: 입력값 형식이 올바르지 않습니다."
    return f"{field}: 입력값이 올바르지 않습니다."


@asynccontextmanager
async def _lifespan(app: FastAPI):
    market_sync_task = start_market_sync_task(app)
    try:
        yield
    finally:
        await stop_market_sync_task(market_sync_task)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app_settings.data_dir.mkdir(parents=True, exist_ok=True)
    app_settings.backup_dir.mkdir(parents=True, exist_ok=True)

    db = connect(app_settings.database_path)
    try:
        migrate(db)
    finally:
        db.close()

    if app_settings.database_path.exists():
        db = connect(app_settings.database_path)
        try:
            create_recorded_backup(
                db,
                db_path=app_settings.database_path,
                backup_dir=app_settings.backup_dir,
                reason="startup",
            )
        finally:
            db.close()

    app = FastAPI(title="Personal Finance Portfolio", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=LOCAL_FRONTEND_ORIGINS,
        allow_methods=["GET", "POST", "OPTIONS", "DELETE", "PUT"],
        allow_headers=["*"],
    )
    app.state.settings = app_settings
    app.state.db_path = app_settings.database_path

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(RequestValidationError)
    def validation_exception_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": [_validation_error_message(error) for error in exc.errors()]},
        )

    app.include_router(summary.router)
    app.include_router(accounts.router)
    app.include_router(assets.router)
    app.include_router(transactions.router)
    app.include_router(goals.router)
    app.include_router(backups.router)
    app.include_router(market_data.router)

    return app
