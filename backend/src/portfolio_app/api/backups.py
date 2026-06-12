import sqlite3
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from portfolio_app.api import get_db, row_to_dict
from portfolio_app.services.backups import create_backup, prune_backups

router = APIRouter(prefix="/api/backups", tags=["backups"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_backup_endpoint(request: Request, db: Db) -> dict[str, object]:
    settings = request.app.state.settings
    created_at = datetime.now().isoformat(timespec="seconds")

    try:
        backup_path = create_backup(
            db_path=settings.database_path,
            backup_dir=settings.backup_dir,
            reason="manual",
        )
        prune_backups(backup_dir=settings.backup_dir)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"백업을 생성할 수 없습니다. {exc}",
        ) from exc

    try:
        cursor = db.execute(
            """
            insert into backups(path, reason, created_at)
            values (?, ?, ?)
            """,
            (str(backup_path), "manual", created_at),
        )
        db.commit()
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="백업 정보를 저장할 수 없습니다.",
        ) from exc

    row = db.execute("select * from backups where id = ?", (cursor.lastrowid,)).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="생성된 백업 정보를 찾을 수 없습니다.",
        )
    return row_to_dict(row)


@router.get("")
def list_backups(db: Db) -> list[dict[str, object]]:
    try:
        rows = db.execute(
            """
            select path, reason, created_at
            from backups
            order by created_at desc, id desc
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="백업 목록을 불러올 수 없습니다.",
        ) from exc

    return [row_to_dict(row) for row in rows]
