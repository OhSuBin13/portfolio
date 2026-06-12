import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from portfolio_app.api import get_db, row_to_dict
from portfolio_app.services.backups import create_recorded_backup, list_backup_records

router = APIRouter(prefix="/api/backups", tags=["backups"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_backup_endpoint(request: Request, db: Db) -> dict[str, object]:
    settings = request.app.state.settings

    try:
        row = create_recorded_backup(
            db,
            db_path=settings.database_path,
            backup_dir=settings.backup_dir,
            reason="manual",
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"백업을 생성할 수 없습니다. {exc}",
        ) from exc
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="백업 정보를 저장할 수 없습니다.",
        ) from exc

    return row_to_dict(row)


@router.get("")
def list_backups(request: Request, db: Db) -> list[dict[str, object]]:
    settings = request.app.state.settings

    try:
        rows = list_backup_records(db, backup_dir=settings.backup_dir)
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="백업 목록을 불러올 수 없습니다.",
        ) from exc

    return [row_to_dict(row) for row in rows]
