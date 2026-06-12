import math
import sqlite3
from collections.abc import Generator

from fastapi import HTTPException, Request, status

from portfolio_app.db import connect


def get_db(request: Request) -> Generator[sqlite3.Connection]:
    db = connect(request.app.state.settings.database_path)
    try:
        yield db
    finally:
        db.close()


def row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return dict(row)


def require_non_empty(value: str, message: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return normalized


def require_allowed(value: str, allowed: set[str], message: str) -> str:
    normalized = require_non_empty(value, message)
    if normalized not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return normalized


def require_positive_number(value: float, message: str) -> float:
    if not math.isfinite(value) or value <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return value


def created_row(db: sqlite3.Connection, table: str, row_id: int) -> dict[str, object]:
    row = db.execute(f"select * from {table} where id = ?", (row_id,)).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="생성된 데이터를 찾을 수 없습니다.",
        )
    return row_to_dict(row)
