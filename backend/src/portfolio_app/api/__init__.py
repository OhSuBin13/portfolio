import sqlite3
from collections.abc import Generator

from fastapi import Request

from portfolio_app.db import connect


def get_db(request: Request) -> Generator[sqlite3.Connection]:
    db = connect(request.app.state.settings.database_path)
    try:
        yield db
    finally:
        db.close()


def row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return dict(row)
