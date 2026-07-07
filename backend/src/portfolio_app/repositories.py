import sqlite3

from portfolio_app.services.toss_portfolio import TossOrder


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


def fetch_growth_month_history_row(
    db: sqlite3.Connection,
    *,
    account_seq: str,
    year: int,
    month: int,
) -> sqlite3.Row | None:
    return db.execute(
        """
        select *
        from growth_month_history
        where account_seq = ?
          and year = ?
          and month = ?
        """,
        (account_seq, year, month),
    ).fetchone()


def fetch_growth_month_history_rows(
    db: sqlite3.Connection,
    *,
    account_seq: str,
) -> list[sqlite3.Row]:
    return db.execute(
        """
        select *
        from growth_month_history
        where account_seq = ?
        order by year, month
        """,
        (account_seq,),
    ).fetchall()


def upsert_growth_month_history(
    db: sqlite3.Connection,
    *,
    account_seq: str,
    year: int,
    month: int,
    net_worth_krw: float,
    monthly_dividend_krw: float,
    commit: bool = True,
) -> sqlite3.Row:
    db.execute(
        """
        insert into growth_month_history(
          account_seq, year, month, net_worth_krw, monthly_dividend_krw
        )
        values (?, ?, ?, ?, ?)
        on conflict(account_seq, year, month)
        do update set net_worth_krw = excluded.net_worth_krw,
                      monthly_dividend_krw = excluded.monthly_dividend_krw,
                      updated_at = current_timestamp
        """,
        (account_seq, year, month, net_worth_krw, monthly_dividend_krw),
    )
    if commit:
        db.commit()
    row = fetch_growth_month_history_row(
        db,
        account_seq=account_seq,
        year=year,
        month=month,
    )
    if row is None:
        raise RuntimeError("저장된 월간 성장 기록을 찾을 수 없습니다.")
    return row


def delete_growth_month_history(
    db: sqlite3.Connection,
    *,
    account_seq: str,
    year: int,
    month: int,
) -> bool:
    cursor = db.execute(
        """
        delete from growth_month_history
        where account_seq = ?
          and year = ?
          and month = ?
        """,
        (account_seq, year, month),
    )
    db.commit()
    return cursor.rowcount > 0


def fetch_sp500_proxy_price(
    db: sqlite3.Connection,
    *,
    year: int,
    proxy_symbol: str = "VOO",
) -> sqlite3.Row | None:
    return db.execute(
        """
        select *
        from sp500_proxy_prices
        where proxy_symbol = ?
          and year = ?
        """,
        (proxy_symbol, year),
    ).fetchone()


def fetch_sp500_proxy_prices(
    db: sqlite3.Connection,
    *,
    proxy_symbol: str = "VOO",
) -> list[sqlite3.Row]:
    return db.execute(
        """
        select *
        from sp500_proxy_prices
        where proxy_symbol = ?
        order by year
        """,
        (proxy_symbol,),
    ).fetchall()


def upsert_sp500_proxy_price(
    db: sqlite3.Connection,
    *,
    year: int,
    price: float,
    proxy_symbol: str = "VOO",
    commit: bool = True,
) -> sqlite3.Row:
    db.execute(
        """
        insert into sp500_proxy_prices(year, proxy_symbol, price)
        values (?, ?, ?)
        on conflict(proxy_symbol, year)
        do update set price = excluded.price,
                      updated_at = current_timestamp
        """,
        (year, proxy_symbol, price),
    )
    if commit:
        db.commit()
    row = fetch_sp500_proxy_price(db, year=year, proxy_symbol=proxy_symbol)
    if row is None:
        raise RuntimeError("저장된 S&P 500 프록시 가격을 찾을 수 없습니다.")
    return row


def fetch_sp500_proxy_annual_return_ratios(
    db: sqlite3.Connection,
    *,
    years: list[int],
    current_year: int,
    proxy_symbol: str = "VOO",
) -> dict[int, float]:
    prices = {
        int(row["year"]): float(row["price"])
        for row in fetch_sp500_proxy_prices(db, proxy_symbol=proxy_symbol)
    }
    ratios: dict[int, float] = {}
    for year in sorted(set(years)):
        if year >= current_year:
            continue
        start_price = prices.get(year - 1)
        end_price = prices.get(year)
        if start_price is None or end_price is None or start_price <= 0:
            continue
        ratios[year] = end_price / start_price
    return ratios


def create_toss_order_import_run(
    db: sqlite3.Connection,
    *,
    account_seq: str,
    status_filter: str,
    symbol_filter: str | None,
    from_date: str | None,
    to_date: str | None,
) -> int:
    cursor = db.execute(
        """
        insert into toss_order_import_runs(
          account_seq, status_filter, symbol_filter, from_date, to_date, run_status
        )
        values (?, ?, ?, ?, ?, 'running')
        """,
        (account_seq, status_filter, symbol_filter, from_date, to_date),
    )
    db.commit()
    return int(cursor.lastrowid)


def finish_toss_order_import_run(
    db: sqlite3.Connection,
    *,
    run_id: int,
    run_status: str,
    imported_count: int,
    error_message: str = "",
) -> None:
    db.execute(
        """
        update toss_order_import_runs
        set run_status = ?,
            imported_count = ?,
            error_message = ?,
            completed_at = current_timestamp
        where id = ?
        """,
        (run_status, imported_count, error_message, run_id),
    )


def fetch_toss_order_import_run(
    db: sqlite3.Connection,
    *,
    run_id: int,
) -> sqlite3.Row | None:
    return db.execute(
        "select * from toss_order_import_runs where id = ?",
        (run_id,),
    ).fetchone()


def fetch_toss_order_import_runs(
    db: sqlite3.Connection,
    *,
    account_seq: str | None = None,
) -> list[sqlite3.Row]:
    conditions: list[str] = []
    params: list[object] = []
    if account_seq is not None:
        conditions.append("account_seq = ?")
        params.append(account_seq)
    where = f"where {' and '.join(conditions)}" if conditions else ""
    return db.execute(
        f"select * from toss_order_import_runs {where} order by id desc",
        params,
    ).fetchall()


def upsert_toss_order(
    db: sqlite3.Connection,
    *,
    account_seq: str,
    order: TossOrder,
    raw_json: str,
    import_run_id: int,
) -> None:
    execution = order.execution
    db.execute(
        """
        insert into toss_orders(
          account_seq,
          order_id,
          symbol,
          side,
          order_type,
          time_in_force,
          order_status,
          price,
          quantity,
          order_amount,
          currency,
          ordered_at,
          canceled_at,
          filled_quantity,
          average_filled_price,
          filled_amount,
          commission,
          tax,
          filled_at,
          settlement_date,
          raw_json,
          import_run_id
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(account_seq, order_id) do update set
          symbol = excluded.symbol,
          side = excluded.side,
          order_type = excluded.order_type,
          time_in_force = excluded.time_in_force,
          order_status = excluded.order_status,
          price = excluded.price,
          quantity = excluded.quantity,
          order_amount = excluded.order_amount,
          currency = excluded.currency,
          ordered_at = excluded.ordered_at,
          canceled_at = excluded.canceled_at,
          filled_quantity = excluded.filled_quantity,
          average_filled_price = excluded.average_filled_price,
          filled_amount = excluded.filled_amount,
          commission = excluded.commission,
          tax = excluded.tax,
          filled_at = excluded.filled_at,
          settlement_date = excluded.settlement_date,
          raw_json = excluded.raw_json,
          import_run_id = excluded.import_run_id,
          updated_at = current_timestamp
        """,
        (
            account_seq,
            order.order_id,
            order.symbol,
            order.side,
            order.order_type,
            order.time_in_force,
            order.status,
            order.price,
            order.quantity,
            order.order_amount,
            order.currency,
            order.ordered_at,
            order.canceled_at,
            execution.filled_quantity,
            execution.average_filled_price,
            execution.filled_amount,
            execution.commission,
            execution.tax,
            execution.filled_at,
            execution.settlement_date,
            raw_json,
            import_run_id,
        ),
    )


def fetch_toss_orders(
    db: sqlite3.Connection,
    *,
    account_seq: str,
    symbol: str | None = None,
    order_status: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[sqlite3.Row]:
    conditions = ["account_seq = ?"]
    params: list[object] = [account_seq]
    if symbol is not None:
        conditions.append("symbol = ?")
        params.append(symbol.upper())
    if order_status is not None:
        conditions.append("order_status = ?")
        params.append(order_status)
    if from_date is not None:
        conditions.append("substr(ordered_at, 1, 10) >= ?")
        params.append(from_date)
    if to_date is not None:
        conditions.append("substr(ordered_at, 1, 10) <= ?")
        params.append(to_date)

    return db.execute(
        f"""
        select
          id,
          account_seq,
          order_id,
          symbol,
          side,
          order_type,
          time_in_force,
          order_status,
          price,
          quantity,
          order_amount,
          currency,
          ordered_at,
          canceled_at,
          filled_quantity,
          average_filled_price,
          filled_amount,
          commission,
          tax,
          filled_at,
          settlement_date,
          imported_at,
          updated_at
        from toss_orders
        where {' and '.join(conditions)}
        order by ordered_at desc, id desc
        """,
        params,
    ).fetchall()


def upsert_chart_marker_memo(
    db: sqlite3.Connection,
    *,
    account_seq: str,
    symbol: str,
    marker_key: str,
    memo: str,
) -> sqlite3.Row:
    db.execute(
        """
        insert into chart_marker_memos(account_seq, symbol, marker_key, memo)
        values (?, ?, ?, ?)
        on conflict(account_seq, symbol, marker_key) do update set
          memo = excluded.memo,
          updated_at = current_timestamp
        """,
        (account_seq, symbol, marker_key, memo),
    )
    db.commit()
    row = db.execute(
        """
        select *
        from chart_marker_memos
        where account_seq = ? and symbol = ? and marker_key = ?
        """,
        (account_seq, symbol, marker_key),
    ).fetchone()
    if row is None:
        raise RuntimeError("차트 마커 메모를 찾을 수 없습니다.")
    return row


def fetch_chart_marker_memos(
    db: sqlite3.Connection,
    *,
    account_seq: str,
    symbol: str,
) -> list[sqlite3.Row]:
    return db.execute(
        """
        select *
        from chart_marker_memos
        where account_seq = ? and symbol = ?
        order by marker_key
        """,
        (account_seq, symbol),
    ).fetchall()


def delete_chart_marker_memo(
    db: sqlite3.Connection,
    *,
    account_seq: str,
    symbol: str,
    marker_key: str,
) -> None:
    db.execute(
        """
        delete from chart_marker_memos
        where account_seq = ? and symbol = ? and marker_key = ?
        """,
        (account_seq, symbol, marker_key),
    )
    db.commit()
