import sqlite3
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SummaryHoldingRow:
    quantity: float
    average_cost: float | None
    asset_id: int
    asset_symbol: str | None
    asset_name: str
    asset_type: str
    asset_currency: str
    manual_price_krw: float | None
    transaction_fx_rate_to_krw: float | None
    latest_fx_rate_to_krw: float | None
    latest_price_krw: float | None


@dataclass(frozen=True)
class SummaryIncomeRow:
    amount: float
    currency: str
    fx_rate_to_krw: float | None


@dataclass(frozen=True)
class GrowthSnapshotRow:
    id: int
    snapshot_date: date
    net_worth_krw: float
    gross_assets_krw: float
    debt_krw: float
    monthly_income_krw: float
    asset_mix_json: str
    source: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class GrowthCashflowRow:
    occurred_on: date
    type: str
    amount: float
    currency: str
    fx_rate_to_krw: float | None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _growth_snapshot_from_row(row: sqlite3.Row) -> GrowthSnapshotRow:
    return GrowthSnapshotRow(
        id=int(row["id"]),
        snapshot_date=date.fromisoformat(str(row["snapshot_date"])),
        net_worth_krw=float(row["net_worth_krw"]),
        gross_assets_krw=float(row["gross_assets_krw"]),
        debt_krw=float(row["debt_krw"]),
        monthly_income_krw=float(row["monthly_income_krw"]),
        asset_mix_json=str(row["asset_mix_json"]),
        source=str(row["source"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def create_account(db: sqlite3.Connection, *, name: str, type: str) -> int:
    cursor = db.execute(
        "insert into accounts(name, type) values (?, ?)",
        (name, type),
    )
    db.commit()
    return int(cursor.lastrowid)


def create_account_record(db: sqlite3.Connection, *, name: str, type: str) -> sqlite3.Row:
    account_id = create_account(db, name=name, type=type)
    row = fetch_account(db, account_id=account_id)
    if row is None:
        raise RuntimeError("생성된 계좌를 찾을 수 없습니다.")
    return row


def fetch_accounts(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute("select * from accounts order by id").fetchall()


def fetch_account(db: sqlite3.Connection, *, account_id: int) -> sqlite3.Row | None:
    return db.execute("select * from accounts where id = ?", (account_id,)).fetchone()


def create_goal(
    db: sqlite3.Connection,
    *,
    name: str,
    type: str,
    target_amount_krw: float,
) -> int:
    cursor = db.execute(
        "insert into goals(name, type, target_amount_krw) values (?, ?, ?)",
        (name, type, target_amount_krw),
    )
    db.commit()
    return int(cursor.lastrowid)


def fetch_goals(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute("select * from goals order by id").fetchall()


def fetch_goal(db: sqlite3.Connection, *, goal_id: int) -> sqlite3.Row | None:
    return db.execute("select * from goals where id = ?", (goal_id,)).fetchone()


def create_goal_record(
    db: sqlite3.Connection,
    *,
    name: str,
    type: str,
    target_amount_krw: float,
) -> sqlite3.Row:
    goal_id = create_goal(db, name=name, type=type, target_amount_krw=target_amount_krw)
    row = fetch_goal(db, goal_id=goal_id)
    if row is None:
        raise RuntimeError("생성된 목표를 찾을 수 없습니다.")
    return row


def update_account(
    db: sqlite3.Connection,
    *,
    account_id: int,
    name: str,
    type: str,
) -> bool:
    cursor = db.execute(
        """update accounts set name = ?, type = ?,
        updated_at = current_timestamp where id = ?""",
        (name, type, account_id),
    )
    db.commit()
    return cursor.rowcount > 0


def update_account_record(
    db: sqlite3.Connection,
    *,
    account_id: int,
    name: str,
    type: str,
) -> sqlite3.Row | None:
    if not update_account(db, account_id=account_id, name=name, type=type):
        return None
    return fetch_account(db, account_id=account_id)


def delete_account(db: sqlite3.Connection, *, account_id: int) -> bool:
    cursor = db.execute("delete from accounts where id = ?", (account_id,))
    db.commit()
    return cursor.rowcount > 0


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


def fetch_assets(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute("select * from assets order by id").fetchall()


def fetch_asset(db: sqlite3.Connection, *, asset_id: int) -> sqlite3.Row | None:
    return db.execute("select * from assets where id = ?", (asset_id,)).fetchone()


def create_asset_record(
    db: sqlite3.Connection,
    *,
    symbol: str | None,
    name: str,
    type: str,
    currency: str,
    market: str | None,
) -> sqlite3.Row:
    asset_id = create_asset(
        db,
        symbol=symbol,
        name=name,
        type=type,
        currency=currency,
        market=market,
    )
    row = fetch_asset(db, asset_id=asset_id)
    if row is None:
        raise RuntimeError("생성된 자산을 찾을 수 없습니다.")
    return row


def get_holding(db: sqlite3.Connection, *, account_id: int, asset_id: int) -> sqlite3.Row:
    row = db.execute(
        "select * from holdings where account_id = ? and asset_id = ?",
        (account_id, asset_id),
    ).fetchone()
    if row is None:
        raise ValueError("보유자산을 찾을 수 없습니다.")
    return row


def get_current_holding(
    db: sqlite3.Connection,
    *,
    account_id: int,
    asset_id: int,
) -> tuple[float, float | None]:
    row = db.execute(
        "select quantity, average_cost from holdings where account_id = ? and asset_id = ?",
        (account_id, asset_id),
    ).fetchone()
    if row is None:
        return 0.0, None
    return float(row["quantity"]), row["average_cost"]


def get_asset_currency(db: sqlite3.Connection, *, asset_id: int) -> str:
    row = db.execute("select currency from assets where id = ?", (asset_id,)).fetchone()
    if row is None:
        return "KRW"
    return str(row["currency"])


def get_asset_type(db: sqlite3.Connection, *, asset_id: int) -> str:
    row = db.execute("select type from assets where id = ?", (asset_id,)).fetchone()
    if row is None:
        raise ValueError("자산을 찾을 수 없습니다.")
    return str(row["type"])


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


def insert_transaction(
    db: sqlite3.Connection,
    *,
    occurred_on: str,
    type: str,
    account_id: int,
    asset_id: int,
    quantity: float | None,
    amount: float,
    currency: str,
    fx_rate_to_krw: float | None,
    memo: str,
    commit: bool = True,
) -> int:
    cursor = db.execute(
        """
        insert into transactions(
          occurred_on, type, account_id, asset_id, quantity, amount, currency,
          fx_rate_to_krw, memo
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            occurred_on,
            type,
            account_id,
            asset_id,
            quantity,
            amount,
            currency,
            fx_rate_to_krw,
            memo,
        ),
    )
    if commit:
        db.commit()
    return int(cursor.lastrowid)


def fetch_transactions(
    db: sqlite3.Connection,
    *,
    account_id: int | None = None,
    asset_id: int | None = None,
    transaction_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[object] = []
    if account_id is not None:
        clauses.append("account_id = ?")
        params.append(account_id)
    if asset_id is not None:
        clauses.append("asset_id = ?")
        params.append(asset_id)
    if transaction_type is not None:
        clauses.append("type = ?")
        params.append(transaction_type)
    if from_date is not None:
        clauses.append("occurred_on >= ?")
        params.append(from_date.isoformat())
    if to_date is not None:
        clauses.append("occurred_on <= ?")
        params.append(to_date.isoformat())

    where = f"where {' and '.join(clauses)}" if clauses else ""
    return db.execute(
        f"select * from transactions {where} order by occurred_on desc, id desc",
        params,
    ).fetchall()


def fetch_growth_snapshot_by_date(
    db: sqlite3.Connection,
    *,
    snapshot_date: date,
) -> GrowthSnapshotRow | None:
    row = db.execute(
        "select * from portfolio_snapshots where snapshot_date = ?",
        (snapshot_date.isoformat(),),
    ).fetchone()
    if row is None:
        return None
    return _growth_snapshot_from_row(row)


def upsert_portfolio_snapshot(
    db: sqlite3.Connection,
    *,
    snapshot_date: date,
    net_worth_krw: float,
    gross_assets_krw: float,
    debt_krw: float,
    monthly_income_krw: float,
    asset_mix_json: str,
    source: str,
) -> None:
    db.execute(
        """
        insert into portfolio_snapshots(
          snapshot_date, net_worth_krw, gross_assets_krw, debt_krw,
          monthly_income_krw, asset_mix_json, source
        )
        values (?, ?, ?, ?, ?, ?, ?)
        on conflict(snapshot_date)
        do update set net_worth_krw = excluded.net_worth_krw,
                      gross_assets_krw = excluded.gross_assets_krw,
                      debt_krw = excluded.debt_krw,
                      monthly_income_krw = excluded.monthly_income_krw,
                      asset_mix_json = excluded.asset_mix_json,
                      source = excluded.source,
                      updated_at = current_timestamp
        """,
        (
            snapshot_date.isoformat(),
            net_worth_krw,
            gross_assets_krw,
            debt_krw,
            monthly_income_krw,
            asset_mix_json,
            source,
        ),
    )


def fetch_growth_snapshots(
    db: sqlite3.Connection,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[GrowthSnapshotRow]:
    clauses: list[str] = []
    params: list[str] = []
    if from_date is not None:
        clauses.append("snapshot_date >= ?")
        params.append(from_date.isoformat())
    if to_date is not None:
        clauses.append("snapshot_date <= ?")
        params.append(to_date.isoformat())

    where = f"where {' and '.join(clauses)}" if clauses else ""
    rows = db.execute(
        f"select * from portfolio_snapshots {where} order by snapshot_date, id",
        params,
    ).fetchall()
    return [_growth_snapshot_from_row(row) for row in rows]


def fetch_growth_cashflow_rows(
    db: sqlite3.Connection,
    *,
    start: date,
    end_exclusive: date,
) -> list[GrowthCashflowRow]:
    rows = db.execute(
        """
        select occurred_on, type, amount, currency, fx_rate_to_krw
        from transactions
        where occurred_on > ?
          and occurred_on < ?
          and type in ('deposit', 'withdrawal', 'debt_payment', 'dividend', 'interest')
        order by occurred_on, id
        """,
        (start.isoformat(), end_exclusive.isoformat()),
    ).fetchall()
    return [
        GrowthCashflowRow(
            occurred_on=date.fromisoformat(str(row["occurred_on"])),
            type=str(row["type"]),
            amount=float(row["amount"] or 0),
            currency=str(row["currency"]),
            fx_rate_to_krw=_optional_float(row["fx_rate_to_krw"]),
        )
        for row in rows
    ]


def fetch_summary_holding_rows(db: sqlite3.Connection) -> list[SummaryHoldingRow]:
    rows = db.execute(
        """
        select h.quantity,
               h.average_cost,
               a.id as asset_id,
               a.symbol as asset_symbol,
               a.name as asset_name,
               a.type as asset_type,
               a.currency as asset_currency,
               a.manual_price_krw,
               (
                 select t.fx_rate_to_krw
                 from transactions t
                 where t.account_id = h.account_id
                   and t.asset_id = h.asset_id
                   and t.fx_rate_to_krw is not null
                 order by t.occurred_on desc, t.id desc
                 limit 1
               ) as transaction_fx_rate_to_krw,
               (
                 select fx.rate
                 from fx_rates fx
                 where fx.base_currency = a.currency
                   and fx.quote_currency = 'KRW'
                 order by fx.fetched_at desc, fx.id desc
                 limit 1
               ) as latest_fx_rate_to_krw,
               (
                 select ps.price_krw
                 from price_snapshots ps
                 where ps.asset_id = a.id
                   and ps.status in ('ok', 'manual', 'stale')
                 order by ps.fetched_at desc, ps.id desc
                 limit 1
               ) as latest_price_krw
        from holdings h
        join assets a on a.id = h.asset_id
        order by h.id
        """
    ).fetchall()
    return [
        SummaryHoldingRow(
            quantity=float(row["quantity"] or 0),
            average_cost=_optional_float(row["average_cost"]),
            asset_id=int(row["asset_id"]),
            asset_symbol=str(row["asset_symbol"]) if row["asset_symbol"] else None,
            asset_name=str(row["asset_name"]),
            asset_type=str(row["asset_type"]),
            asset_currency=str(row["asset_currency"]),
            manual_price_krw=_optional_float(row["manual_price_krw"]),
            transaction_fx_rate_to_krw=_optional_float(row["transaction_fx_rate_to_krw"]),
            latest_fx_rate_to_krw=_optional_float(row["latest_fx_rate_to_krw"]),
            latest_price_krw=_optional_float(row["latest_price_krw"]),
        )
        for row in rows
    ]


def fetch_summary_income_rows(
    db: sqlite3.Connection,
    *,
    month_start: str,
    next_month_start: str,
) -> list[SummaryIncomeRow]:
    rows = db.execute(
        """
        select amount, currency, fx_rate_to_krw
        from transactions
        where type in ('dividend', 'interest')
          and occurred_on >= ?
          and occurred_on < ?
        order by id
        """,
        (month_start, next_month_start),
    ).fetchall()
    return [
        SummaryIncomeRow(
            amount=float(row["amount"] or 0),
            currency=str(row["currency"]),
            fx_rate_to_krw=_optional_float(row["fx_rate_to_krw"]),
        )
        for row in rows
    ]


def fetch_latest_transaction_fx_rate_to_krw(
    db: sqlite3.Connection,
    *,
    currency: str,
) -> float | None:
    row = db.execute(
        """
        select fx_rate_to_krw
        from transactions
        where currency = ?
          and fx_rate_to_krw is not null
          and fx_rate_to_krw > 0
        order by occurred_on desc, id desc
        limit 1
        """,
        (currency.upper(),),
    ).fetchone()
    if row is None:
        return None
    return float(row["fx_rate_to_krw"])
