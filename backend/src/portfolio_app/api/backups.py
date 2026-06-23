import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from portfolio_app.api import get_db, row_to_dict
from portfolio_app.models import BackupRecord
from portfolio_app.services.backups import list_backup_records, reconcile_backup_records

router = APIRouter(prefix="/api/backups", tags=["backups"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("", response_model=list[BackupRecord])
def list_backups(request: Request, db: Db) -> list[dict[str, object]]:
    settings = request.app.state.settings

    try:
        reconcile_backup_records(db, backup_dir=settings.backup_dir)
        rows = list_backup_records(db, backup_dir=settings.backup_dir)
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="백업 목록을 불러올 수 없습니다.",
        ) from exc

    return [row_to_dict(row) for row in rows]
