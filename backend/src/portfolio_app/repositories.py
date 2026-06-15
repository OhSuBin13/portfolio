import sqlite3


def create_account(db: sqlite3.Connection, *, name: str, type: str, currency: str) -> int:
    cursor = db.execute(
        "insert into accounts(name, type, currency) values (?, ?, ?)",
        (name, type, currency),
    )
    db.commit()
    return int(cursor.lastrowid)


def create_asset(
    db: sqlite3.Connection,
    *,
    symbol: str | None,
    name: str,
    type: str,
    currency: str,
    market: str | None,
) -> int:
    cursor = db.execute(
        "insert into assets(symbol, name, type, currency, market) values (?, ?, ?, ?, ?)",
        (symbol, name, type, currency, market),
    )
    db.commit()
    return int(cursor.lastrowid)


def get_holding(db: sqlite3.Connection, *, account_id: int, asset_id: int) -> sqlite3.Row:
    row = db.execute(
        "select * from holdings where account_id = ? and asset_id = ?",
        (account_id, asset_id),
    ).fetchone()
    if row is None:
        raise ValueError("보유자산을 찾을 수 없습니다.")
    return row


def upsert_holding(
    db: sqlite3.Connection,
    *,
    account_id: int,
    asset_id: int,
    quantity: float,
    average_cost: float | None,
    commit: bool = True,
) -> None:
    db.execute(
        """
        insert into holdings(account_id, asset_id, quantity, average_cost)
        values (?, ?, ?, ?)
        on conflict(account_id, asset_id)
        do update set quantity = excluded.quantity,
                      average_cost = excluded.average_cost,
                      updated_at = current_timestamp
        """,
        (account_id, asset_id, quantity, average_cost),
    )
    if commit:
        db.commit()
